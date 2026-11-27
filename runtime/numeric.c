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

/* `math.min/max`: NaN propaga; empate devolve o primeiro (como Python/tree-walk). */
double lox_math_min(double left, double right) {
    if (isnan(left) || isnan(right)) {
        return NAN;
    }
    return right < left ? right : left;
}

double lox_math_max(double left, double right) {
    if (isnan(left) || isnan(right)) {
        return NAN;
    }
    return right > left ? right : left;
}

/* `math.clamp`: NaN propaga antes da checagem low <= high, como no tree-walk. */
double lox_math_clamp(double value, double low, double high, int32_t line,
                      int32_t column) {
    if (isnan(value) || isnan(low) || isnan(high)) {
        return NAN;
    }
    if (low > high) {
        lox_panic(line, column, "R1000", "math.clamp() requires low <= high.");
    }
    double lower = low > value ? low : value;
    return high < lower ? high : lower;
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
    const char *data = lox_str_bytes(string);
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
    const char *data = lox_str_bytes(string);
    size_t index = 0;
    if (data[index] == '+' || data[index] == '-') {
        index += 1;
    }
    size_t integer_start = index;
    while (index < size && data[index] >= '0' && data[index] <= '9') {
        index += 1;
    }
    if (index == integer_start) {
        return nil;
    }
    if (index < size && data[index] == '.') {
        index += 1;
        size_t fraction_start = index;
        while (index < size && data[index] >= '0' && data[index] <= '9') {
            index += 1;
        }
        if (index == fraction_start) {
            return nil;
        }
    }
    if (index < size && (data[index] == 'e' || data[index] == 'E')) {
        index += 1;
        if (index < size && (data[index] == '+' || data[index] == '-')) {
            index += 1;
        }
        size_t exponent_start = index;
        while (index < size && data[index] >= '0' && data[index] <= '9') {
            index += 1;
        }
        if (index == exponent_start) {
            return nil;
        }
    }
    if (index != size) {
        return nil;
    }

    char *copy = lox_alloc_atomic(size + 1);
    memcpy(copy, lox_str_bytes(string), size);
    copy[size] = '\0';
    char *parse_end = NULL;
    double value = strtod(copy, &parse_end);
    if (parse_end != copy + size || !isfinite(value)) {
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
        lox_panic(line, column, "R1011", "Can't cast this Float to Int.");
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

/* ---------------------------------------------------------------------------
 * `--debug` checked arithmetic (ADR-0028)
 * --------------------------------------------------------------------------- */

static int64_t checked_result(__int128 value, int32_t line, int32_t column) {
    if (value < INT64_MIN || value > INT64_MAX) {
        lox_panic(line, column, "R1014", "Integer overflow.");
    }
    return (int64_t)value;
}

int64_t lox_int_add_checked(int64_t left, int64_t right, int32_t line,
                            int32_t column) {
    return checked_result((__int128)left + (__int128)right, line, column);
}

int64_t lox_int_sub_checked(int64_t left, int64_t right, int32_t line,
                            int32_t column) {
    return checked_result((__int128)left - (__int128)right, line, column);
}

int64_t lox_int_mul_checked(int64_t left, int64_t right, int32_t line,
                            int32_t column) {
    return checked_result((__int128)left * (__int128)right, line, column);
}

int64_t lox_int_neg_checked(int64_t value, int32_t line, int32_t column) {
    if (value == INT64_MIN) {
        lox_panic(line, column, "R1014", "Integer overflow.");
    }
    return -value;
}

int64_t lox_int_pow_checked(int64_t base, int64_t exponent, int32_t line,
                            int32_t column) {
    if (exponent < 0) {
        lox_panic(line, column, "R1006",
                  "Negative exponent not allowed for integer power.");
    }
    int64_t result = 1;
    int64_t factor = base;
    while (exponent != 0) {
        if (exponent & 1) {
            result = lox_int_mul_checked(result, factor, line, column);
        }
        exponent >>= 1;
        if (exponent != 0) {
            factor = lox_int_mul_checked(factor, factor, line, column);
        }
    }
    return result;
}

int64_t lox_int_div_checked(int64_t left, int64_t right, int32_t line,
                            int32_t column) {
    if (right == 0) {
        lox_panic(line, column, "R1002", "Division by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        lox_panic(line, column, "R1014", "Integer overflow.");
    }
    return left / right;
}

int64_t lox_int_mod_checked(int64_t left, int64_t right, int32_t line,
                            int32_t column) {
    if (right == 0) {
        lox_panic(line, column, "R1002", "Modulo by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        lox_panic(line, column, "R1014", "Integer overflow.");
    }
    return left % right;
}

int64_t lox_math_abs_int_checked(int64_t value, int32_t line, int32_t column) {
    if (value == INT64_MIN) {
        lox_panic(line, column, "R1014", "Integer overflow.");
    }
    return value < 0 ? -value : value;
}

/* Float `**` with the tree-walk's domain/overflow contract (ADR-0029):
 * `0.0 ** negativo` e base negativa com expoente fracionário são R1006;
 * overflow de `pow` é R1014. Resultados NaN/inf legítimos (inputs NaN/inf)
 * continuam valendo. */
double lox_float_pow(double base, double exponent, int32_t line,
                     int32_t column) {
    if (base == 0.0 && exponent < 0.0) {
        lox_panic(line, column, "R1006", "Invalid exponentiation.");
    }
    if (base < 0.0 && isfinite(exponent) && trunc(exponent) != exponent) {
        lox_panic(line, column, "R1006", "Invalid exponentiation.");
    }
    double result = pow(base, exponent);
    if (isnan(result) && !isnan(base) && !isnan(exponent)) {
        lox_panic(line, column, "R1006", "Invalid exponentiation.");
    }
    if (isinf(result) && isfinite(base) && isfinite(exponent)) {
        lox_panic(line, column, "R1014", "Exponentiation overflow.");
    }
    return result;
}

/* ---------------------------------------------------------------------------
 * Dynamic operators (`Any`, L6)
 *
 * The checker keeps `Any` as the explicit dynamic escape hatch. The tree-walk
 * dispatches on the runtime value; these helpers do the same in the binary so
 * the two engines agree without an unchecked payload reinterpretation.
 * --------------------------------------------------------------------------- */

static LoxValue box_int(int64_t value) {
    LoxValue result;
    result.tag = 1;
    result.payload = value;
    return result;
}

static LoxValue box_float(double value) {
    LoxValue result;
    result.tag = 2;
    memcpy(&result.payload, &value, sizeof(value));
    return result;
}

static double unbox_float(int64_t payload) {
    double value;
    memcpy(&value, &payload, sizeof(value));
    return value;
}

static int any_number(LoxValue value, int *is_float, int64_t *integer,
                      double *real) {
    if (value.tag == 1) {
        *is_float = 0;
        *integer = value.payload;
        *real = (double)value.payload;
        return 1;
    }
    if (value.tag == 2) {
        *is_float = 1;
        *integer = 0;
        *real = unbox_float(value.payload);
        return 1;
    }
    return 0;
}

static int any_integer(LoxValue value, int64_t *integer) {
    if (value.tag != 1) {
        return 0;
    }
    *integer = value.payload;
    return 1;
}

LoxValue lox_any_binary(int32_t op, int64_t left_tag, int64_t left_payload,
                        int64_t right_tag, int64_t right_payload,
                        int32_t line, int32_t column) {
    LoxValue left = {left_tag, left_payload};
    LoxValue right = {right_tag, right_payload};
    int left_float = 0;
    int right_float = 0;
    int64_t left_int = 0;
    int64_t right_int = 0;
    double left_real = 0.0;
    double right_real = 0.0;

    /* +, -, *, /, %, //, ** */
    if (op <= 6) {
        if (op == 0 && left.tag == 4 && right.tag == 4) {
            return (LoxValue){4, (int64_t)(intptr_t)lox_str_concat(
                                      (const void *)left.payload,
                                      (const void *)right.payload)};
        }
        if (!any_number(left, &left_float, &left_int, &left_real) ||
            !any_number(right, &right_float, &right_int, &right_real)) {
            if (op == 0) {
                lox_panic(line, column, "R1006",
                          "Operands must be two numbers or two strings.");
            }
            lox_panic(line, column, "R1006", "Operands must be numbers.");
        }
        switch (op) {
            case 0:
                if (!left_float && !right_float) {
                    return box_int((int64_t)((uint64_t)left_int +
                                             (uint64_t)right_int));
                }
                return box_float(left_real + right_real);
            case 1:
                if (!left_float && !right_float) {
                    return box_int((int64_t)((uint64_t)left_int -
                                             (uint64_t)right_int));
                }
                return box_float(left_real - right_real);
            case 2:
                if (!left_float && !right_float) {
                    return box_int((int64_t)((uint64_t)left_int *
                                             (uint64_t)right_int));
                }
                return box_float(left_real * right_real);
            case 3:
                return box_float(lox_float_div(left_real, right_real, line,
                                               column));
            case 4: {
                int64_t a = 0;
                int64_t b = 0;
                if (!any_integer(left, &a) || !any_integer(right, &b)) {
                    lox_panic(line, column, "R1006",
                              "Operands must be integers.");
                }
                return box_int(lox_int_div(a, b, line, column));
            }
            case 5:
                if (!left_float && !right_float) {
                    return box_int(lox_int_mod(left_int, right_int, line,
                                               column));
                }
                return box_float(lox_float_mod(left_real, right_real, line,
                                               column));
            default: {
                int64_t a = 0;
                int64_t b = 0;
                if (any_integer(left, &a) && any_integer(right, &b)) {
                    return box_int(lox_int_pow(a, b, line, column));
                }
                return box_float(lox_float_pow(left_real, right_real, line,
                                               column));
            }
        }
    }

    /* &, |, ^, <<, >>, >>> */
    {
        int64_t a = 0;
        int64_t b = 0;
        if (!any_integer(left, &a) || !any_integer(right, &b)) {
            lox_panic(line, column, "R1006", "Operands must be integers.");
        }
        switch (op) {
            case 7:
                return box_int(a & b);
            case 8:
                return box_int(a | b);
            case 9:
                return box_int(a ^ b);
            case 10:
                return box_int(lox_shift(a, b, 0, line, column));
            case 11:
                return box_int(lox_shift(a, b, 1, line, column));
            case 12:
                return box_int(lox_shift(a, b, 2, line, column));
            default:
                lox_panic(line, column, "R1006", "Operands must be integers.");
        }
    }
    lox_panic(line, column, "R1006", "Operands must be numbers.");
    return box_int(0);
}

LoxValue lox_any_neg(int64_t tag, int64_t payload, int32_t line,
                     int32_t column) {
    LoxValue value = {tag, payload};
    int is_float = 0;
    int64_t integer = 0;
    double real = 0.0;
    if (!any_number(value, &is_float, &integer, &real)) {
        lox_panic(line, column, "R1006", "Operand must be a number.");
    }
    if (is_float) {
        return box_float(-real);
    }
    return box_int((int64_t)(0u - (uint64_t)integer));
}

LoxValue lox_any_bit_not(int64_t tag, int64_t payload, int32_t line,
                         int32_t column) {
    LoxValue value = {tag, payload};
    int64_t integer = 0;
    if (!any_integer(value, &integer)) {
        lox_panic(line, column, "R1006", "Operand must be an integer.");
    }
    return box_int(~integer);
}

int32_t lox_any_compare(int32_t op, int64_t left_tag, int64_t left_payload,
                        int64_t right_tag, int64_t right_payload,
                        int32_t line, int32_t column) {
    LoxValue left = {left_tag, left_payload};
    LoxValue right = {right_tag, right_payload};
    if (left.tag == 4 && right.tag == 4) {
        int32_t comparison = lox_str_compare((const void *)left.payload,
                                             (const void *)right.payload);
        switch (op) {
            case 0:
                return comparison < 0;
            case 1:
                return comparison <= 0;
            case 2:
                return comparison > 0;
            default:
                return comparison >= 0;
        }
    }

    int left_float = 0;
    int right_float = 0;
    int64_t left_int = 0;
    int64_t right_int = 0;
    double left_real = 0.0;
    double right_real = 0.0;
    if (!any_number(left, &left_float, &left_int, &left_real) ||
        !any_number(right, &right_float, &right_int, &right_real)) {
        lox_panic(line, column, "R1006", "Operands must be numbers.");
    }
    if (!left_float && !right_float) {
        left_real = (double)left_int;
        right_real = (double)right_int;
    }
    if (isnan(left_real) || isnan(right_real)) {
        return 0;
    }
    switch (op) {
        case 0:
            return left_real < right_real;
        case 1:
            return left_real <= right_real;
        case 2:
            return left_real > right_real;
        default:
            return left_real >= right_real;
    }
}
