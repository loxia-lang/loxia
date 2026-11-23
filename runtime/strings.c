/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * strings.c — `String` representation, UTF-8, `print`/`str`/`repr` and the
 * boxed-value formatting used by `Any` and containers.
 *
 * Who calls it: the string/interpolation lowering (lower_strings.py), the
 * `format_value` from containers.c and `lox_print_any` on the dynamic path. The
 * `LoxStr` layout lives in lox_runtime.h.
 *
 * Invariants:
 *  - `LoxStr` content is immutable; `cp_offsets` is a lazy cache;
 *  - public indices and lengths count code points, not bytes;
 *  - `format_double` must reproduce Python `repr` bit for bit (I1);
 *  - list/map formatting is deterministic and cuts cycles with `{...}`.
 *
 * ADRs: 0031 (IR/str), 0035 (strings), 0041 (enums), 0049 (Any).
 */
#include "lox_runtime.h"

/* ---------------------------------------------------------------------------
 * Functions and closures
 * --------------------------------------------------------------------------- */

/* `print(f)`: writes the closure's deterministic display + newline. */
void lox_print_function(const void *pointer) {
    const LoxClosure *closure = pointer;
    fputs(closure->display, stdout);
    fputc('\n', stdout);
}

/* `str(f)`/interpolation: materializes the display as an ASCII LoxStr. */
void *lox_str_from_function(const void *pointer) {
    const LoxClosure *closure = pointer;
    const char *display = closure->display;
    size_t length = strlen(display);

    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *data = (char *)(result + 1);
    memcpy(data, display, length + 1);

    result->byte_len = (int64_t)length;
    result->cp_len = (int64_t)length;
    result->flat = data;
    result->cp_offsets = NULL;
    result->hash = 0;
    result->left = NULL;
    result->right = NULL;
    return result;
}

/* ---------------------------------------------------------------------------
 * LoxStr: length, ordering, equality and concatenation
 * --------------------------------------------------------------------------- */

/* `print(s)`: raw UTF-8 bytes + newline (no quotes). */
void lox_print_str(const void *pointer) {
    const LoxStr *string = pointer;
    fwrite(lox_str_bytes(string), 1, (size_t)string->byte_len, stdout);
    fputc('\n', stdout);
}

/* `len(s)`: number of code points. */
int64_t lox_str_len(const void *pointer) {
    return ((const LoxStr *)pointer)->cp_len;
}

/* Lexicographic order by UTF-8 bytes; equivalent to code-point order. */
int32_t lox_str_compare(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    const char *left_bytes = lox_str_bytes(left);
    const char *right_bytes = lox_str_bytes(right);
    size_t shared = (size_t)(left->byte_len < right->byte_len ? left->byte_len
                                                               : right->byte_len);
    int result = memcmp(left_bytes, right_bytes, shared);
    if (result != 0) {
        return result < 0 ? -1 : 1;
    }
    if (left->byte_len == right->byte_len) {
        return 0;
    }
    return left->byte_len < right->byte_len ? -1 : 1;
}

/* Equality by content (`memcmp`), not by identity. */
int32_t lox_str_equal(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    if (left->byte_len != right->byte_len) {
        return 0;
    }
    const char *left_bytes = lox_str_bytes(left);
    const char *right_bytes = lox_str_bytes(right);
    return memcmp(left_bytes, right_bytes, (size_t)left->byte_len) == 0;
}

/* FNV-1a over the bytes, cached in the LoxStr (0 means "not computed").
 * Content-based, so it agrees with `lox_str_equal`; deterministic (I3). */
uint64_t lox_str_hash(const void *pointer) {
    LoxStr *string = (LoxStr *)pointer;
    if (string->hash != 0) {
        return string->hash;
    }
    const unsigned char *data = (const unsigned char *)lox_str_bytes(string);
    uint64_t hash = 14695981039346656037ULL;
    for (int64_t index = 0; index < string->byte_len; index++) {
        hash ^= (uint64_t)data[index];
        hash *= 1099511628211ULL;
    }
    if (hash == 0) {
        hash = 1;
    }
    string->hash = hash;
    return hash;
}

/* String `+`: concatenates without copying. An empty side returns the other
 * operand (strings are immutable); otherwise the result is a rope node that
 * `lox_str_bytes` flattens on first observation. */
void *lox_str_concat(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    if (left->byte_len == 0) {
        return (void *)right;
    }
    if (right->byte_len == 0) {
        return (void *)left;
    }
    LoxStr *result = lox_alloc(sizeof(LoxStr));
    result->byte_len = left->byte_len + right->byte_len;
    result->cp_len = left->cp_len + right->cp_len;
    result->flat = NULL;
    result->cp_offsets = NULL;
    result->hash = 0;
    result->left = (LoxStr *)left;
    result->right = (LoxStr *)right;
    return result;
}


/* ---------------------------------------------------------------------------
 * Code points and UTF-8
 * --------------------------------------------------------------------------- */

/* `chars(s)`: list of one-code-point strings, in text order. */
void *lox_chars(const void *pointer) {
    const LoxStr *string = pointer;
    void *list = lox_list_new();
    for (int64_t index = 0; index < string->cp_len; index++) {
        void *character = lox_str_char_at(string, index);
        lox_list_push(list, 4, (int64_t)character);
    }
    return list;
}



/* Converts a code-point index to the corresponding byte offset.
 *
 * Strings with >= 64 code points materialize `cp_offsets` on the first random
 * access; below that, it scans linearly. `index` outside 0..cp_len is R1007. */
int64_t utf8_cp_offset(const LoxStr *string, int64_t index) {
    if (index < 0 || index > string->cp_len) {
        lox_panic(0, 0, "R1007", "String index out of bounds.");
    }
    if (string->cp_offsets == NULL && string->cp_len >= 64) {
        int32_t *offsets = lox_alloc_atomic(
            (size_t)(string->cp_len + 1) * sizeof(int32_t));
        const unsigned char *data = (const unsigned char *)lox_str_bytes(string);
        size_t offset = 0;
        int64_t position = 0;
        offsets[0] = 0;
        while (position < string->cp_len) {
            unsigned char byte = data[offset];
            offset += byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                       : (byte & 0xF0) == 0xE0 ? 3 : 4;
            position += 1;
            offsets[position] = (int32_t)offset;
        }
        ((LoxStr *)string)->cp_offsets = offsets;
    }
    if (string->cp_offsets != NULL) {
        return string->cp_offsets[index];
    }
    const unsigned char *data = (const unsigned char *)lox_str_bytes(string);
    size_t offset = 0;
    for (int64_t position = 0; position < index; position++) {
        unsigned char byte = data[offset];
        offset += byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                   : (byte & 0xF0) == 0xE0 ? 3 : 4;
    }
    return (int64_t)offset;
}

/* Returns code point `index` as a one-character LoxStr. */
void *lox_str_char_at(const void *pointer, int64_t index) {
    const LoxStr *string = pointer;
    int64_t offset = utf8_cp_offset(string, index);
    const unsigned char *data = (const unsigned char *)lox_str_bytes(string);
    unsigned char byte = data[offset];
    size_t length = byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                     : (byte & 0xF0) == 0xE0 ? 3 : 4;
    return string_from_bytes((const char *)data + offset, length, 1);
}


/* Decodes the first code point of `data` and stores its byte length (1..4) in
 * `length`. Assumes a valid UTF-8 sequence (the caller has validated it). */
int64_t utf8_decode(const unsigned char *data, size_t *length) {
    unsigned char byte = data[0];
    if (byte < 0x80) {
        *length = 1;
        return byte;
    }
    if ((byte & 0xE0) == 0xC0) {
        *length = 2;
        return ((int64_t)(byte & 0x1F) << 6) | (data[1] & 0x3F);
    }
    if ((byte & 0xF0) == 0xE0) {
        *length = 3;
        return ((int64_t)(byte & 0x0F) << 12) |
               ((int64_t)(data[1] & 0x3F) << 6) | (data[2] & 0x3F);
    }
    *length = 4;
    return ((int64_t)(byte & 0x07) << 18) |
           ((int64_t)(data[1] & 0x3F) << 12) |
           ((int64_t)(data[2] & 0x3F) << 6) | (data[3] & 0x3F);
}


/* ---------------------------------------------------------------------------
 * Scalar printing
 * --------------------------------------------------------------------------- */

/* `print(Int)`: decimal + newline. */
void lox_print_int(int64_t value) {
    printf("%" PRId64 "\n", value);
}

/* `print(Bool)`: `true`/`false` + newline. */
void lox_print_bool(int32_t value) {
    fputs(value ? "true\n" : "false\n", stdout);
}

/* `print(nil)`: `nil` + newline. */
void lox_print_nil(void) {
    fputs("nil\n", stdout);
}

/* ---------------------------------------------------------------------------
 * Float formatting (repr parity)
 * --------------------------------------------------------------------------- */

/*
 * Formats a `double` like Python `repr`: the fewest digits that reconstruct the
 * same bit pattern, with CPython conventions (`1.0`, `-0.0`, `1e-05`, `1e+16`).
 *
 * Strategy: try `%.{p}e` for p = 1..17 and use the first one that `strtod`
 * reconstructs. It is O(17) conversions, not a dedicated shortest-repr algorithm
 * (Ryu); for L1 the cost is microseconds per printed value. The contract is
 * fuzz-tested against `repr` in `tests/test_backend.py`.
 */
void format_double(double value, char *out, size_t size) {
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
        /* 0.000ddd: `decpt` zeros before the digits. */
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
        /* ddd000.0: digits and zeros up to the decimal point. */
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
        /* dd.ddd: decimal point in the middle of the digits. */
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

/* Renders NaN/inf and delegates finite values to `format_double`. */
void format_float_value(double value, char *out, size_t size) {
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

/* `print(Float)`: canonical representation + newline. */
void lox_print_float(double value) {
    char buffer[64];
    format_float_value(value, buffer, sizeof buffer);
    fputs(buffer, stdout);
    fputc('\n', stdout);
}

/* ---------------------------------------------------------------------------
 * Building LoxStr
 * --------------------------------------------------------------------------- */

/* Allocates an ASCII LoxStr (numbers, booleans, "nil") on the collected heap. */
LoxStr *string_from_ascii(const char *data, size_t length) {
    return string_from_bytes(data, length, (int64_t)length);
}

/* Copies `length` bytes and stores `code_points` as `cp_len`. The caller ensures
 * the count is correct; the copy is NUL-terminated for internal C use. */
LoxStr *string_from_bytes(const char *data, size_t length,
                                 int64_t code_points) {
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *copy = (char *)(result + 1);
    memcpy(copy, data, length);
    copy[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = code_points;
    result->flat = copy;
    result->cp_offsets = NULL;
    result->hash = 0;
    result->left = NULL;
    result->right = NULL;
    return result;
}

/* Materializes the bytes of a rope into `flat` (iteratively, so a 50k-deep
 * left spine does not touch the C stack) and returns them. Leaves already have
 * `flat`; the temporary stack holds LoxStr pointers, not language values. */
const char *lox_str_bytes(const LoxStr *string) {
    if (string->flat != NULL) {
        return string->flat;
    }
    size_t capacity = 64;
    size_t depth = 0;
    LoxStr **stack = malloc(sizeof(LoxStr *) * capacity);
    if (stack == NULL) {
        lox_oom_exit();
    }
    stack[depth++] = (LoxStr *)string;
    char *buffer = lox_alloc_atomic((size_t)string->byte_len + 1);
    size_t used = 0;
    while (depth > 0) {
        LoxStr *node = stack[--depth];
        if (node->flat != NULL) {
            memcpy(buffer + used, node->flat, (size_t)node->byte_len);
            used += (size_t)node->byte_len;
            continue;
        }
        if (depth + 2 > capacity) {
            capacity *= 2;
            LoxStr **grown = realloc(stack, sizeof(LoxStr *) * capacity);
            if (grown == NULL) {
                free(stack);
                lox_oom_exit();
            }
            stack = grown;
        }
        stack[depth++] = node->right;
        stack[depth++] = node->left;
    }
    free(stack);
    buffer[used] = '\0';
    ((LoxStr *)string)->flat = buffer;
    return buffer;
}

/* Pointer to the bytes (valid while the LoxStr lives; the GC keeps it alive). */
const char *lox_str_data(const void *pointer) {
    return lox_str_bytes((const LoxStr *)pointer);
}

/* `str(Int)`/Int interpolation. */
void *lox_str_from_int(int64_t value) {
    char buffer[32];
    int length = snprintf(buffer, sizeof buffer, "%" PRId64, value);
    return string_from_ascii(buffer, (size_t)length);
}

/* `str(Float)`/Float interpolation. */
void *lox_str_from_double(double value) {
    char buffer[64];
    format_float_value(value, buffer, sizeof buffer);
    return string_from_ascii(buffer, strlen(buffer));
}

/* `str(Bool)`/Bool interpolation. */
void *lox_str_from_bool(int32_t value) {
    return value ? string_from_ascii("true", 4)
                 : string_from_ascii("false", 5);
}

/* `str(nil)`/nil interpolation. */
void *lox_str_nil(void) {
    return string_from_ascii("nil", 3);
}

/* Materializes a panic C message as a LoxStr for `except ... as e`. */
void *lox_str_from_cstr(const char *data) {
    if (data == NULL) {
        return lox_str_nil();
    }
    return string_from_ascii(data, strlen(data));
}

/* String `repr`: quotes + escapes for `\\`, `"`, LF, CR, TAB and NUL. */
void *lox_str_quote(const void *pointer) {
    const LoxStr *source = pointer;
    size_t bytes = (size_t)source->byte_len;

    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes * 2 + 3);
    char *data = (char *)(result + 1);
    size_t used = 0;
    data[used++] = '"';

    for (size_t index = 0; index < bytes; index++) {
        char byte = lox_str_bytes(source)[index];
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
    result->flat = data;
    result->cp_offsets = NULL;
    result->hash = 0;
    result->left = NULL;
    result->right = NULL;
    return result;
}



/* ---------------------------------------------------------------------------
 * LoxBuffer: dynamic formatting buffer (atomic GC)
 *
 * The buffer is NOT NUL-terminated: use `length` when consuming it. Bytes are
 * allocated with `lox_alloc_atomic` because they contain no pointers.
 * --------------------------------------------------------------------------- */

/* Initial capacity of 64 bytes. */
void buffer_init(LoxBuffer *buffer) {
    buffer->capacity = 64;
    buffer->data = lox_alloc_atomic(buffer->capacity);
    buffer->length = 0;
    buffer->active_depth = 0;
}

/* Ensures room for `extra` bytes, doubling capacity and copying the old data. */
void buffer_need(LoxBuffer *buffer, size_t extra) {
    if (buffer->length + extra <= buffer->capacity) {
        return;
    }
    size_t capacity = buffer->capacity;
    while (capacity < buffer->length + extra) {
        capacity *= 2;
    }
    char *data = lox_alloc_atomic(capacity);
    memcpy(data, buffer->data, buffer->length);
    buffer->data = data;
    buffer->capacity = capacity;
}

/* Appends one byte. */
void buffer_char(LoxBuffer *buffer, char byte) {
    buffer_need(buffer, 1);
    buffer->data[buffer->length++] = byte;
}

/* Appends a NUL-terminated C string. */
void buffer_text(LoxBuffer *buffer, const char *text) {
    size_t length = strlen(text);
    buffer_need(buffer, length);
    memcpy(buffer->data + buffer->length, text, length);
    buffer->length += length;
}

/* Appends `length` raw bytes. */
void buffer_bytes(LoxBuffer *buffer, const char *data, size_t length) {
    buffer_need(buffer, length);
    memcpy(buffer->data + buffer->length, data, length);
    buffer->length += length;
}


/* ---------------------------------------------------------------------------
 * Container and boxed-value formatting
 *
 * Lists and maps keep `active[]` to cut cycles (`[...]`/`{...}`) and cap depth at
 * 64. Output matches the tree-walk `stringify`/`repr` byte for byte (I1).
 * --------------------------------------------------------------------------- */

/* `Enum.Variant(payload...)`; without a payload, just `Enum.Variant`. */
void format_enum(LoxBuffer *buffer, const LoxEnumValue *value) {
    buffer_text(buffer, value->enum_name);
    buffer_char(buffer, '.');
    buffer_text(buffer, value->variant_name);
    if (value->count > 0) {
        buffer_char(buffer, '(');
        for (int64_t index = 0; index < value->count; index++) {
            if (index > 0) {
                buffer_text(buffer, ", ");
            }
            format_value(buffer, value->payload[index]);
        }
        buffer_char(buffer, ')');
    }
}

/* `(a, b, ...)`; tuples have fixed arity. */
void format_tuple(LoxBuffer *buffer, const LoxTuple *tuple) {
    buffer_char(buffer, '(');
    for (int64_t index = 0; index < tuple->count; index++) {
        if (index > 0) {
            buffer_text(buffer, ", ");
        }
        format_value(buffer, tuple->items[index]);
    }
    buffer_char(buffer, ')');
}

/* `{k: v, ...}` in insertion order, with a cycle guard. */
void format_map(LoxBuffer *buffer, const LoxMap *map) {
    for (int index = 0; index < buffer->active_depth; index++) {
        if (buffer->active[index] == map) {
            buffer_text(buffer, "{...}");
            return;
        }
    }
    if (buffer->active_depth >= 64) {
        buffer_text(buffer, "{...}");
        return;
    }
    buffer->active[buffer->active_depth++] = map;
    buffer_char(buffer, '{');
    for (int64_t index = 0; index < map->count; index++) {
        if (index > 0) {
            buffer_text(buffer, ", ");
        }
        format_value(buffer, map->entries[index].key);
        buffer_text(buffer, ": ");
        format_value(buffer, map->entries[index].value);
    }
    buffer_char(buffer, '}');
    buffer->active_depth -= 1;
}

/* `[a, b, ...]` in insertion order, with a cycle guard. */
void format_list(LoxBuffer *buffer, const LoxList *list) {
    for (int index = 0; index < buffer->active_depth; index++) {
        if (buffer->active[index] == list) {
            buffer_text(buffer, "[...]");
            return;
        }
    }
    if (buffer->active_depth >= 64) {
        buffer_text(buffer, "[...]");
        return;
    }
    buffer->active[buffer->active_depth++] = list;
    buffer_char(buffer, '[');
    for (int64_t index = 0; index < list->count; index++) {
        if (index > 0) {
            buffer_text(buffer, ", ");
        }
        format_value(buffer, list->items[index]);
    }
    buffer_char(buffer, ']');
    buffer->active_depth -= 1;
}

/* Dispatches formatting by `LoxValue` tag. Strings use `repr` (quoted); Float
 * goes through `memcpy` because the payload is the bit pattern. */
void format_value(LoxBuffer *buffer, LoxValue value) {
    switch (value.tag) {
        case 0:
            buffer_text(buffer, "nil");
            break;
        case 1: {
            char text[32];
            int length = snprintf(text, sizeof text, "%" PRId64, value.payload);
            buffer_bytes(buffer, text, (size_t)length);
            break;
        }
        case 2: {
            double number;
            memcpy(&number, &value.payload, sizeof(number));
            char text[64];
            format_float_value(number, text, sizeof text);
            buffer_text(buffer, text);
            break;
        }
        case 3:
            buffer_text(buffer, value.payload ? "true" : "false");
            break;
        case 4: {
            void *quoted = lox_str_quote((const void *)value.payload);
            const LoxStr *string = quoted;
            buffer_bytes(buffer, lox_str_bytes(string), (size_t)string->byte_len);
            break;
        }
        case 5: {
            void *descriptor = (void *)value.payload;
            const LoxStr *name = ((void **)descriptor)[2];
            buffer_bytes(buffer, lox_str_bytes(name), (size_t)name->byte_len);
            break;
        }
        case 6: {
            void *instance = (void *)value.payload;
            void *descriptor = ((void **)instance)[0];
            const LoxStr *name = ((void **)descriptor)[2];
            buffer_bytes(buffer, lox_str_bytes(name), (size_t)name->byte_len);
            buffer_text(buffer, " instance");
            break;
        }
        case 7: {
            const LoxClosure *closure = (const void *)value.payload;
            buffer_text(buffer, closure->display);
            break;
        }
        case 8: {
            const LoxRange *range = (const void *)value.payload;
            const char *operator = range->inclusive ? "..=" : "..";
            char text[128];
            int length;
            if (range->step == 1) {
                length = snprintf(text, sizeof text,
                                  "<range %" PRId64 "%s%" PRId64 ">",
                                  range->start, operator, range->end);
            } else {
                length = snprintf(
                    text, sizeof text,
                    "<range %" PRId64 "%s%" PRId64 " step %" PRId64 ">",
                    range->start, operator, range->end, range->step);
            }
            buffer_bytes(buffer, text, (size_t)length);
            break;
        }
        case 9:
            format_list(buffer, (const void *)value.payload);
            break;
        case 10:
            format_map(buffer, (const void *)value.payload);
            break;
        case 11:
            format_tuple(buffer, (const void *)value.payload);
            break;
        case 12:
            format_enum(buffer, (const void *)value.payload);
            break;
        case 13:
            format_bytes(buffer, (const LoxBytes *)value.payload);
            break;
        default:
            buffer_text(buffer, "<value>");
            break;
    }
}

/* `print(List)`: formats and writes + newline. */
void lox_print_list(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_list(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

/* `print(Map)`: formats and writes + newline. */
void lox_print_map(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_map(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

/* `print(Enum)`: formats and writes + newline. */
void lox_print_enum(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_enum(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

/* `str(Enum)`: formats without a newline. */
void *lox_str_from_enum(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_enum(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

/* `print(Tuple)`: formats and writes + newline. */
void lox_print_tuple(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_tuple(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

/* `str(Tuple)`: formats without a newline. */
void *lox_str_from_tuple(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_tuple(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

/* `str(Map)`: formats without a newline. */
void *lox_str_from_map(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_map(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

/* `str(List)`: formats without a newline. */
void *lox_str_from_list(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_list(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

/* ---------------------------------------------------------------------------
 * Dynamic path (`Any`, L6)
 * --------------------------------------------------------------------------- */

/* `str`/interpolation of a boxed `Any`: same formatting as dynamic `print`.
 * String is the only case that does not allocate (it returns the LoxStr itself). */
void *lox_str_from_any(int64_t tag, int64_t payload) {
    if (tag == 4) {
        return (void *)payload;
    }
    LoxBuffer buffer;
    buffer_init(&buffer);
    LoxValue value;
    value.tag = tag;
    value.payload = payload;
    format_value(&buffer, value);
    return string_from_ascii(buffer.data, buffer.length);
}

/* `repr(Any)`: strings precisam de aspas; `format_value` já as cita (case 4). */
void *lox_repr_from_any(int64_t tag, int64_t payload) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    LoxValue value;
    value.tag = tag;
    value.payload = payload;
    format_value(&buffer, value);
    return string_from_ascii(buffer.data, buffer.length);
}


/* `print` of a boxed value: `{tag, payload}` of 64 bits. Tags are the same as in
 * format_value/LoxValue; an unknown tag is R1000. */
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
            break;
        }
        case 6: {
            void *instance = (void *)payload;
            void *descriptor = ((void **)instance)[0];
            const LoxStr *name = ((void **)descriptor)[2];
            fwrite(lox_str_bytes(name), 1, (size_t)name->byte_len, stdout);
            fputs(" instance\n", stdout);
            break;
        }
        case 7:
            lox_print_function((const void *)payload);
            break;
        case 8:
            lox_print_range((const void *)payload);
            break;
        case 9:
            lox_print_list((const void *)payload);
            break;
        case 10:
            lox_print_map((const void *)payload);
            break;
        case 11:
            lox_print_tuple((const void *)payload);
            break;
        case 12:
            lox_print_enum((const void *)payload);
            break;
        case 13:
            lox_print_bytes((const void *)payload);
            break;
        default:
            lox_panic(0, 0, "R1000", "Unknown Any tag");
    }
}
