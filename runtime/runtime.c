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

/*
 * String imutável: bytes UTF-8 + contagem de code points (ADR-0031, decisão 6).
 * O IR usa `i8*` para o ponteiro; o layout é este struct.
 */
typedef struct {
    int64_t byte_len;
    int64_t cp_len;
    const char *data;
} LoxStr;

static LoxStr *string_from_ascii(const char *data, size_t length);
void lox_panic(int32_t line, const char *message);

/* Arena: um bloco, sem free, com teto determinístico (decisão 7). */
#define LOX_HEAP_BYTES (64ull * 1024ull * 1024ull)

static unsigned char *lox_heap = NULL;
static size_t lox_heap_used = 0;

static void *lox_alloc(size_t size) {
    if (lox_heap == NULL) {
        lox_heap = malloc(LOX_HEAP_BYTES);
        if (lox_heap == NULL) {
            lox_panic(0, "Out of memory.");
        }
    }
    size = (size + 7u) & ~(size_t)7u;
    if (lox_heap_used + size > LOX_HEAP_BYTES) {
        lox_panic(0, "Out of memory.");
    }
    void *pointer = lox_heap + lox_heap_used;
    lox_heap_used += size;
    return pointer;
}

/*
 * Closure do L4 (ADR-0046): `{ fnptr, env, display }`. O IR aloca via estes wrappers;
 * `display` é uma string C determinística (`<fn f>`/`<lambda>`), nunca um endereço.
 */
typedef struct {
    void *fn;
    void *env;
    const char *display;
} LoxClosure;

void *lox_alloc_cell(void) {
    /* Cabe o maior valor escalar: `{i1, i64}`/`{i1, double}` (16 bytes). */
    return lox_alloc(2 * sizeof(int64_t));
}

void *lox_alloc_env(int64_t count) {
    size_t entries = count > 0 ? (size_t)count : 1u;
    return lox_alloc(entries * sizeof(void *));
}

void *lox_alloc_closure(void) {
    return lox_alloc(sizeof(LoxClosure));
}

void *lox_alloc_bytes(int64_t size) {
    return lox_alloc(size > 0 ? (size_t)size : 1u);
}

int lox_is_instance(void *descriptor, void *target) {
    while (descriptor != NULL) {
        if (descriptor == target) {
            return 1;
        }
        descriptor = *(void **)descriptor;
    }
    return 0;
}

void lox_print_function(const void *pointer) {
    const LoxClosure *closure = pointer;
    fputs(closure->display, stdout);
    fputc('\n', stdout);
}

void *lox_str_from_function(const void *pointer) {
    const LoxClosure *closure = pointer;
    const char *display = closure->display;
    size_t length = strlen(display);

    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *data = (char *)(result + 1);
    memcpy(data, display, length + 1);

    result->byte_len = (int64_t)length;
    result->cp_len = (int64_t)length;
    result->data = data;
    return result;
}

void lox_print_str(const void *pointer) {
    const LoxStr *string = pointer;
    fwrite(string->data, 1, (size_t)string->byte_len, stdout);
    fputc('\n', stdout);
}

int64_t lox_str_len(const void *pointer) {
    return ((const LoxStr *)pointer)->cp_len;
}

int32_t lox_str_compare(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    size_t shared = (size_t)(left->byte_len < right->byte_len ? left->byte_len
                                                               : right->byte_len);
    int result = memcmp(left->data, right->data, shared);
    if (result != 0) {
        return result < 0 ? -1 : 1;
    }
    if (left->byte_len == right->byte_len) {
        return 0;
    }
    return left->byte_len < right->byte_len ? -1 : 1;
}

int32_t lox_str_equal(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    if (left->byte_len != right->byte_len) {
        return 0;
    }
    return memcmp(left->data, right->data, (size_t)left->byte_len) == 0;
}

void *lox_str_concat(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    size_t bytes = (size_t)left->byte_len + (size_t)right->byte_len;

    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes + 1);
    char *data = (char *)(result + 1);
    memcpy(data, left->data, (size_t)left->byte_len);
    memcpy(data + left->byte_len, right->data, (size_t)right->byte_len);
    data[bytes] = '\0';

    result->byte_len = (int64_t)bytes;
    result->cp_len = left->cp_len + right->cp_len;
    result->data = data;
    return result;
}


/* Range do L6: valor imutável, ponteiro para `{start, end, step}`. */
typedef struct {
    int64_t start;
    int64_t end;
    int64_t step;
} LoxRange;

void *lox_range_new(int64_t start, int64_t end, int64_t step) {
    if (step == 0) {
        lox_panic(0, "range() step can't be zero.");
    }
    LoxRange *range = lox_alloc(sizeof(LoxRange));
    range->start = start;
    range->end = end;
    range->step = step;
    return range;
}

int64_t lox_range_start(const void *pointer) {
    return ((const LoxRange *)pointer)->start;
}

int64_t lox_range_end(const void *pointer) {
    return ((const LoxRange *)pointer)->end;
}

int64_t lox_range_step(const void *pointer) {
    return ((const LoxRange *)pointer)->step;
}

int32_t lox_range_equal(const void *left_pointer, const void *right_pointer) {
    const LoxRange *left = left_pointer;
    const LoxRange *right = right_pointer;
    return left->start == right->start && left->end == right->end &&
           left->step == right->step;
}

void lox_print_range(const void *pointer) {
    const LoxRange *range = pointer;
    if (range->step == 1) {
        printf("<range %" PRId64 "..%" PRId64 ">\n", range->start,
               range->end);
    } else {
        printf("<range %" PRId64 "..%" PRId64 " step %" PRId64 ">\n",
               range->start, range->end, range->step);
    }
}

void *lox_str_from_range(const void *pointer) {
    const LoxRange *range = pointer;
    char buffer[128];
    int length;
    if (range->step == 1) {
        length = snprintf(buffer, sizeof buffer, "<range %" PRId64 "..%" PRId64 ">",
                          range->start, range->end);
    } else {
        length = snprintf(buffer, sizeof buffer,
                          "<range %" PRId64 "..%" PRId64 " step %" PRId64 ">",
                          range->start, range->end, range->step);
    }
    return string_from_ascii(buffer, (size_t)length);
}

/* `chars(s)[i]`: i é índice em code points, não em bytes. */
void *lox_str_char_at(const void *pointer, int64_t index) {
    const LoxStr *string = pointer;
    if (index < 0 || index >= string->cp_len) {
        lox_panic(0, "String index out of bounds.");
    }
    const unsigned char *data = (const unsigned char *)string->data;
    size_t offset = 0;
    for (int64_t position = 0; position < index; position++) {
        unsigned char byte = data[offset];
        if (byte < 0x80) {
            offset += 1;
        } else if ((byte & 0xE0) == 0xC0) {
            offset += 2;
        } else if ((byte & 0xF0) == 0xE0) {
            offset += 3;
        } else {
            offset += 4;
        }
    }
    unsigned char byte = data[offset];
    size_t length = byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                     : (byte & 0xF0) == 0xE0 ? 3
                                             : 4;
    return string_from_ascii((const char *)data + offset, length);
}


int64_t lox_int_pow(int64_t base, int64_t exponent, int32_t line) {
    if (exponent < 0) {
        lox_panic(line, "Negative exponent not allowed for integer power.");
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

int64_t lox_shift(int64_t value, int64_t count, int32_t kind, int32_t line) {
    if (count < 0 || count > 63) {
        lox_panic(line, "Shift count must be between 0 and 63.");
    }
    if (kind == 0) {
        return (int64_t)((uint64_t)value << (uint64_t)count);
    }
    if (kind == 1) {
        return value >> (uint64_t)count;
    }
    return (int64_t)((uint64_t)value >> (uint64_t)count);
}

int64_t lox_float_to_int(double value, int32_t line) {
    if (isnan(value) || isinf(value) || value < -9223372036854775808.0 ||
        value >= 9223372036854775808.0) {
        lox_panic(line, "Can't cast value to Int.");
    }
    return (int64_t)value;
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

static void format_float_value(double value, char *out, size_t size) {
    if (isnan(value)) {
        snprintf(out, size, "NaN");
        return;
    }
    if (isinf(value)) {
        snprintf(out, size, value < 0 ? "-inf" : "inf");
        return;
    }
    format_double(value, out, size);
}

void lox_print_float(double value) {
    char buffer[64];
    format_float_value(value, buffer, sizeof buffer);
    fputs(buffer, stdout);
    fputc('\n', stdout);
}

/* Aloca uma LoxStr ASCII (números, booleanos, "nil") dentro da arena. */
static LoxStr *string_from_ascii(const char *data, size_t length) {
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *copy = (char *)(result + 1);
    memcpy(copy, data, length);
    copy[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = (int64_t)length;
    result->data = copy;
    return result;
}

void *lox_str_from_int(int64_t value) {
    char buffer[32];
    int length = snprintf(buffer, sizeof buffer, "%" PRId64, value);
    return string_from_ascii(buffer, (size_t)length);
}

void *lox_str_from_double(double value) {
    char buffer[64];
    format_float_value(value, buffer, sizeof buffer);
    return string_from_ascii(buffer, strlen(buffer));
}

void *lox_str_from_bool(int32_t value) {
    return value ? string_from_ascii("true", 4)
                 : string_from_ascii("false", 5);
}

void *lox_str_nil(void) {
    return string_from_ascii("nil", 3);
}

/* `repr` de string: aspas + escapes, como `values._quote` do interpretador. */
void *lox_str_quote(const void *pointer) {
    const LoxStr *source = pointer;
    size_t bytes = (size_t)source->byte_len;

    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes * 2 + 3);
    char *data = (char *)(result + 1);
    size_t used = 0;
    data[used++] = '"';

    for (size_t index = 0; index < bytes; index++) {
        char byte = source->data[index];
        switch (byte) {
            case '\\':
                data[used++] = '\\';
                data[used++] = '\\';
                break;
            case '"':
                data[used++] = '\\';
                data[used++] = '"';
                break;
            case '\n':
                data[used++] = '\\';
                data[used++] = 'n';
                break;
            case '\r':
                data[used++] = '\\';
                data[used++] = 'r';
                break;
            case '\t':
                data[used++] = '\\';
                data[used++] = 't';
                break;
            case '\0':
                data[used++] = '\\';
                data[used++] = '0';
                break;
            default:
                data[used++] = byte;
                break;
        }
    }

    data[used++] = '"';
    data[used] = '\0';

    result->byte_len = (int64_t)used;
    result->cp_len = source->cp_len + 2;
    result->data = data;
    return result;
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

/* Impressão de valor boxeado `Any` (spike L6): tag + payload de 64 bits. */
void lox_print_any(int64_t tag, int64_t payload) {
    switch (tag) {
        case 0:
            lox_print_nil();
            break;
        case 1:
            lox_print_int(payload);
            break;
        case 2: {
            double value;
            memcpy(&value, &payload, sizeof(value));
            lox_print_float(value);
            break;
        }
        case 3:
            lox_print_bool(payload != 0);
            break;
        case 4:
            lox_print_str((const void *)payload);
            break;
        case 5: {
            void *descriptor = (void *)payload;
            void *name = ((void **)descriptor)[2];
            lox_print_str(name);
            fputc('\n', stdout);
            break;
        }
        case 6: {
            void *instance = (void *)payload;
            void *descriptor = ((void **)instance)[0];
            void *name = ((void **)descriptor)[2];
            lox_print_str(name);
            fputs(" instance\n", stdout);
            break;
        }
        case 7:
            printf("%s\n", (const char *)payload);
            break;
        case 8:
            lox_print_range((const void *)payload);
            break;
        default:
            lox_panic(0, "Unknown Any tag");
    }
}
