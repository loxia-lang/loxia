/* Aritmética com borda definida, `math.*` e parse (ADR-0006, ADR-0028, ADR-0029). */
#include "lox_runtime.h"


int64_t lox_math_abs_int(int64_t value) {
    return value < 0 ? (int64_t)(0u - (uint64_t)value) : value;
}

double lox_math_abs_float(double value) {
    return fabs(value);
}

double lox_math_sqrt(double value) {
    return sqrt(value);
}

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

int64_t lox_float_to_int(double value, int32_t line, int32_t column) {
    if (isnan(value) || isinf(value) || value < -9223372036854775808.0 ||
        value >= 9223372036854775808.0) {
        lox_panic(line, column, "R1011", "Can't cast value to Int.");
    }
    return (int64_t)value;
}



/*
 * `//`: divisão inteira truncada em direção a zero, com wrapping de i64 em release
 * (ADR-0028). O interpretador devolve INT_MIN para INT_MIN // -1; em C e em LLVM isso
 * é UB, então o caso é resolvido explicitamente.
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

/* `/`: sempre Float. Divisão por zero é erro fatal, como no interpretador. */
double lox_float_div(double left, double right, int32_t line,
                     int32_t column) {
    if (right == 0.0) {
        lox_panic(line, column, "R1002", "Division by zero not allowed");
    }
    return left / right;
}

/* `%` com Float: `fmod`, sinal do dividendo, e zero é erro (como no interpretador). */
double lox_float_mod(double left, double right, int32_t line,
                     int32_t column) {
    if (right == 0.0) {
        lox_panic(line, column, "R1002", "Modulo by zero not allowed");
    }
    return fmod(left, right);
}

/* `%`: resto truncado (sinal do dividendo), como `srem`. INT_MIN % -1 é 0. */
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
