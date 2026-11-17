/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * numeric.c — defined-edge arithmetic, `math.*`, numeric parsing and
 * `Int`/`Float` conversions.
 *
 * Who calls it: the expression lowering (lower.py, lower_math.py,
 * lower_optionals.py) and the stdlib/`Int.parse`/`Float.parse`. Every operation
 * that can fail receives a call site (`line, column`) and calls `lox_panic`, to
 * reproduce the tree-walk diagnostic.
 *
 * Invariants:
 *  - `//` truncates toward zero; `INT64_MIN // -1` returns `INT64_MIN`;
 *  - `%` follows the dividend sign; division/modulo by zero is R1002;
 *  - `**` with a negative exponent is R1006; the result wraps as i64;
 *  - `math.*` consults neither locale nor global state;
 *  - `Int.parse`/`Float.parse` return `nil` (tag 0) for invalid input.
 *
 * ADRs: 0006 (Int/Float), 0028 (overflow/wrapping), 0029 (conversions/math).
 */
#include "lox_runtime.h"


/* ---------------------------------------------------------------------------
 * math.* (ADR-0029)
 * --------------------------------------------------------------------------- */

/* `abs(Int)`: INT64_MIN returns INT64_MIN (wrapping), with no UB. */
int64_t lox_math_abs_int(int64_t value) {
    return value < 0 ? (int64_t)(0u - (uint64_t)value) : value;
}

/* `abs(Float)`; NaN keeps its input bit pattern. */
double lox_math_abs_float(double value) {
    return fabs(value);
}

/* `sqrt`; domain/NaN follow C semantics (the checker does not reject them). */
double lox_math_sqrt(double value) {
    return sqrt(value);
}

/* `floor`/`ceil`/`round`/`trunc` return Int through `lox_float_to_int`, with
 * R1011 for NaN, infinity or values outside the i64 range. */
int64_t lox_math_floor(double value, int32_t line, int32_t column) {
    return lox_float_to_int(floor(value), line, column);
}

int64_t lox_math_ceil(double value, int32_t line, int32_t column) {
    return lox_float_to_int(ceil(value), line, column);
}

int64_t lox_math_round(double value, int32_t line, int32_t column) {
    return lox_float_to_int(round(value), line, column);
}

int64_t lox_math_trunc(double value, int32_t line, int32_t column) {
    return lox_float_to_int(trunc(value), line, column);
}

/* ---------------------------------------------------------------------------
 * Numeric parsing (ADR-0029)
 * --------------------------------------------------------------------------- */

/* `Int.parse`: optional sign and digits only; returns `nil` (tag 0) for empty
 * input, an invalid character or i64 overflow. */
LoxValue lox_parse_int(const void *pointer) {
    const LoxStr *string = pointer;
    const char *data = string->data;
    size_t size = (size_t)string->byte_len;
    LoxValue nil = {0, 0};
    if (size == 0) {
        return nil;
    }
    size_t index = 0;
    int negative = 0;
    if (data[index] == '+' || data[index] == '-') {
        negative = data[index] == '-';
        index += 1;
    }
    if (index == size) {
        return nil;
    }
    uint64_t value = 0;
    for (; index < size; index++) {
        char byte = data[index];
        if (byte < '0' || byte > '9') {
            return nil;
        }
        unsigned digit = (unsigned)(byte - '0');
        if (value > (UINT64_MAX - digit) / 10u) {
            return nil;
        }
        value = value * 10u + digit;
    }
    if ((!negative && value > (uint64_t)INT64_MAX) ||
        (negative && value > (uint64_t)INT64_MAX + 1u)) {
        return nil;
    }
    int64_t result = negative ? (int64_t)(0u - value) : (int64_t)value;
    LoxValue some = {1, result};
    return some;
}

/* `Float.parse`: `strtod` with full consumption; rejects trailing garbage, NaN
 * and inf. Returns a boxed `{tag 2, bit pattern}`. */
LoxValue lox_parse_float(const void *pointer) {
    const LoxStr *string = pointer;
    LoxValue nil = {0, 0};
    size_t size = (size_t)string->byte_len;
    if (size == 0) {
        return nil;
    }
    char *copy = lox_alloc_atomic(size + 1);
    memcpy(copy, string->data, size);
    copy[size] = '\0';
    char *end = NULL;
    double value = strtod(copy, &end);
    if (end != copy + size || !isfinite(value)) {
        return nil;
    }
    LoxValue some;
    some.tag = 2;
    memcpy(&some.payload, &value, sizeof(value));
    return some;
}



/* ---------------------------------------------------------------------------
 * Power, shifts and cast
 * --------------------------------------------------------------------------- */

/* Int `**` by squaring, with i64 wrapping; a negative exponent is R1006. */
int64_t lox_int_pow(int64_t base, int64_t exponent, int32_t line,
                    int32_t column) {
    if (exponent < 0) {
        lox_panic(line, column, "R1006",
                  "Negative exponent not allowed for integer power.");
    }
    uint64_t power = (uint64_t)exponent;
    uint64_t result = 1;
    uint64_t factor = (uint64_t)base;
    while (power != 0) {
        if (power & 1u) {
            result *= factor;
        }
        power >>= 1u;
        if (power != 0) {
            factor *= factor;
        }
    }
    return (int64_t)result;
}

/* Int shifts: kind 0 = `<<`, 1 = arithmetic `>>`, 2 = logical `>>>`.
 * A count outside 0..63 is R1006. */
int64_t lox_shift(int64_t value, int64_t count, int32_t kind, int32_t line,
                  int32_t column) {
    if (count < 0 || count > 63) {
        lox_panic(line, column, "R1006",
                  "Shift count must be between 0 and 63.");
    }
    if (kind == 0) {
        return (int64_t)((uint64_t)value << (uint64_t)count);
    }
    if (kind == 1) {
        return value >> (uint64_t)count;
    }
    return (int64_t)((uint64_t)value >> (uint64_t)count);
}

/* `Float -> Int` cast: truncates toward zero; NaN, infinity or values outside
 * the i64 range are R1011. */
int64_t lox_float_to_int(double value, int32_t line, int32_t column) {
    if (isnan(value) || isinf(value) || value < -9223372036854775808.0 ||
        value >= 9223372036854775808.0) {
        lox_panic(line, column, "R1011", "Can't cast value to Int.");
    }
    return (int64_t)value;
}



/* ---------------------------------------------------------------------------
 * Division and remainder
 * --------------------------------------------------------------------------- */

/*
 * `//`: integer division truncated toward zero, with i64 wrapping in release
 * (ADR-0028). The interpreter returns INT_MIN for INT_MIN // -1; in C and LLVM
 * that is UB, so the case is handled explicitly.
 */
int64_t lox_int_div(int64_t left, int64_t right, int32_t line,
                    int32_t column) {
    if (right == 0) {
        lox_panic(line, column, "R1002", "Division by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        return INT64_MIN;
    }
    return left / right;
}

/* `/`: always Float. Division by zero is a fatal error, as in the interpreter. */
double lox_float_div(double left, double right, int32_t line,
                     int32_t column) {
    if (right == 0.0) {
        lox_panic(line, column, "R1002", "Division by zero not allowed");
    }
    return left / right;
}

/* Float `%`: `fmod`, dividend sign, and zero is an error (as in the interpreter). */
double lox_float_mod(double left, double right, int32_t line,
                     int32_t column) {
    if (right == 0.0) {
        lox_panic(line, column, "R1002", "Modulo by zero not allowed");
    }
    return fmod(left, right);
}

/* `%`: truncated remainder (dividend sign), like `srem`. INT_MIN % -1 is 0. */
int64_t lox_int_mod(int64_t left, int64_t right, int32_t line,
                    int32_t column) {
    if (right == 0) {
        lox_panic(line, column, "R1002", "Modulo by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        return 0;
    }
    return left % right;
}
