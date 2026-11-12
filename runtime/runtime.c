/*
 * Runtime do backend nativo do Lox.
 *
 * Só entra aqui o que o IR gerado não deve carregar: I/O, formatação e os casos de
 * borda da aritmética (divisão por zero e o INT_MIN / -1, que é UB em C e em LLVM).
 *
 * Contrato: `lox_panic` reproduz o diagnóstico do interpretador (stderr e exit 70),
 * `lox_print_*` reproduzem `stringify` + `print` (valor e '\n').
 */

#include <inttypes.h>
#include <locale.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * I3: a conversão de/para texto de `double` não pode depender do locale do processo.
 * `snprintf`/`strtod` usam LC_NUMERIC; o binário fixa em "C" no início.
 */
void lox_init(void) {
    setlocale(LC_NUMERIC, "C");
}

void lox_panic(int32_t line, const char *message) {
    fflush(stdout);
    fprintf(stderr, "%s\n[line %" PRId32 "]\n", message, line);
    fflush(stderr);
    exit(70);
}

void lox_print_int(int64_t value) {
    printf("%" PRId64 "\n", value);
}

void lox_print_bool(int32_t value) {
    fputs(value ? "true\n" : "false\n", stdout);
}

void lox_print_nil(void) {
    fputs("nil\n", stdout);
}

/*
 * Formata `double` como o `repr` do Python: menor quantidade de dígitos que reconstrói
 * o mesmo bit pattern, com as convenções do CPython (`1.0`, `-0.0`, `1e-05`, `1e+16`).
 *
 * Estratégia: tenta `%.{p}e` para p = 1..17 e usa o primeiro que `strtod` reconstrói.
 * É O(17) conversões, não um algoritmo de shortest-repr dedicado (Ryu); para o L1 a
 * diferença é de microssegundos por print impresso. O contrato é validado por fuzz
 * contra `repr` em `tests/test_backend.py`.
 */
static void format_double(double value, char *out, size_t size) {
    if (value == 0.0) {
        snprintf(out, size, "%s0.0", signbit(value) ? "-" : "");
        return;
    }

    char scientific[64];
    int precision;
    for (precision = 1; precision <= 17; precision++) {
        snprintf(scientific, sizeof scientific, "%.*e", precision - 1, value);
        if (strtod(scientific, NULL) == value) {
            break;
        }
    }

    const char *cursor = scientific;
    int negative = 0;
    if (*cursor == '-') {
        negative = 1;
        cursor++;
    }

    char digits[32];
    size_t count = 0;
    digits[count++] = *cursor++;
    if (*cursor == '.') {
        cursor++;
        while (*cursor >= '0' && *cursor <= '9' && count < sizeof digits - 1) {
            digits[count++] = *cursor++;
        }
    }
    while (count > 1 && digits[count - 1] == '0') {
        count--;
    }
    digits[count] = '\0';

    int exponent = 0;
    if (*cursor == 'e' || *cursor == 'E') {
        exponent = atoi(cursor + 1);
    }

    int decpt = exponent + 1;
    char *write = out;
    size_t remaining = size;
    if (negative) {
        *write++ = '-';
        remaining--;
    }

    if (decpt <= -4 || decpt > 16) {
        snprintf(write, remaining, "%c%s%s%c%+03d", digits[0], count > 1 ? "." : "",
                 count > 1 ? digits + 1 : "", 'e', decpt - 1);
        return;
    }

    size_t used = 0;
    if (decpt <= 0) {
        /* 0.000ddd: `decpt` zeros antes dos dígitos. */
        if (used + 2 < remaining) {
            write[used++] = '0';
            write[used++] = '.';
        }
        for (int index = 0; index < -decpt && used + 1 < remaining; index++) {
            write[used++] = '0';
        }
        for (size_t index = 0; index < count && used + 1 < remaining; index++) {
            write[used++] = digits[index];
        }
    } else if ((size_t)decpt >= count) {
        /* ddd000.0: dígitos e zeros até a casa decimal. */
        size_t index;
        for (index = 0; index < count && used + 1 < remaining; index++) {
            write[used++] = digits[index];
        }
        for (; index < (size_t)decpt && used + 1 < remaining; index++) {
            write[used++] = '0';
        }
        if (used + 2 < remaining) {
            write[used++] = '.';
            write[used++] = '0';
        }
    } else {
        /* dd.ddd: ponto decimal no meio dos dígitos. */
        for (size_t index = 0; index < (size_t)decpt && used + 1 < remaining;
             index++) {
            write[used++] = digits[index];
        }
        if (used + 1 < remaining) {
            write[used++] = '.';
        }
        for (size_t index = (size_t)decpt; index < count && used + 1 < remaining;
             index++) {
            write[used++] = digits[index];
        }
    }
    write[used] = '\0';
}

void lox_print_float(double value) {
    if (isnan(value)) {
        fputs("NaN\n", stdout);
        return;
    }
    if (isinf(value)) {
        fputs(value < 0 ? "-inf\n" : "inf\n", stdout);
        return;
    }

    char buffer[64];
    format_double(value, buffer, sizeof buffer);
    fputs(buffer, stdout);
    fputc('\n', stdout);
}

/*
 * `//`: divisão inteira truncada em direção a zero, com wrapping de i64 em release
 * (ADR-0028). O interpretador devolve INT_MIN para INT_MIN // -1; em C e em LLVM isso
 * é UB, então o caso é resolvido explicitamente.
 */
int64_t lox_int_div(int64_t left, int64_t right, int32_t line) {
    if (right == 0) {
        lox_panic(line, "Division by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        return INT64_MIN;
    }
    return left / right;
}

/* `/`: sempre Float. Divisão por zero é erro fatal, como no interpretador. */
double lox_float_div(double left, double right, int32_t line) {
    if (right == 0.0) {
        lox_panic(line, "Division by zero not allowed");
    }
    return left / right;
}

/* `%` com Float: `fmod`, sinal do dividendo, e zero é erro (como no interpretador). */
double lox_float_mod(double left, double right, int32_t line) {
    if (right == 0.0) {
        lox_panic(line, "Modulo by zero not allowed");
    }
    return fmod(left, right);
}

/* `%`: resto truncado (sinal do dividendo), como `srem`. INT_MIN % -1 é 0. */
int64_t lox_int_mod(int64_t left, int64_t right, int32_t line) {
    if (right == 0) {
        lox_panic(line, "Modulo by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        return 0;
    }
    return left % right;
}
