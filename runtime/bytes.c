/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * bytes.c — the immutable `Bytes` value (ADR-0125), tag 13.
 *
 * `LoxBytes` is a contiguous 0..255 buffer allocated with `lox_alloc_atomic`;
 * `data` is NULL iff `len == 0`, so every memcpy/memcmp is guarded. Conversion
 * helpers return `Result`/`BytesError` enum values built with `lox_enum_new`,
 * matching the interpreter (enum id -1 for BytesError, 0 for Result).
 *
 * ADRs: 0125 (Bytes), 0031 (backend), 0041 (enums), 0123 (kernel).
 */
#include "lox_runtime.h"

static const char HEX_DIGITS[] = "0123456789abcdef";
static const char BASE64_DIGITS[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static int hex_digit(char value) {
    if (value >= '0' && value <= '9') {
        return value - '0';
    }
    if (value >= 'a' && value <= 'f') {
        return value - 'a' + 10;
    }
    if (value >= 'A' && value <= 'F') {
        return value - 'A' + 10;
    }
    return -1;
}

static int base64_digit(char value) {
    if (value >= 'A' && value <= 'Z') {
        return value - 'A';
    }
    if (value >= 'a' && value <= 'z') {
        return value - 'a' + 26;
    }
    if (value >= '0' && value <= '9') {
        return value - '0' + 52;
    }
    if (value == '+') {
        return 62;
    }
    if (value == '/') {
        return 63;
    }
    return -1;
}

static void *bytes_error(const char *variant, const char *message) {
    size_t length = strlen(message);
    void *text = string_from_bytes(message, length, (int64_t)length);
    void *error = lox_enum_new(-1, "BytesError", variant, 1);
    lox_enum_set(error, 0, 4, (int64_t)text);
    return error;
}

static void *result_ok(void *bytes) {
    void *result = lox_enum_new(0, "Result", "Ok", 1);
    lox_enum_set(result, 0, 13, (int64_t)bytes);
    return result;
}

static void *result_err(void *error) {
    void *result = lox_enum_new(0, "Result", "Err", 1);
    lox_enum_set(result, 0, 12, (int64_t)error);
    return result;
}

/* `Bytes.empty()` / the backing buffer for the constructors. */
void *lox_bytes_new(int64_t len) {
    if (len < 0) {
        lox_panic(0, 0, "R1000", "Bytes length must be non-negative.");
        return NULL;
    }
    LoxBytes *value = lox_alloc(sizeof(LoxBytes));
    value->len = len;
    value->data = len > 0 ? lox_alloc_atomic((size_t)len) : NULL;
    return value;
}

int64_t lox_bytes_len(const void *pointer) {
    return ((const LoxBytes *)pointer)->len;
}

int64_t lox_bytes_at(const void *pointer, int64_t index, int32_t line,
                     int32_t column) {
    const LoxBytes *value = pointer;
    if (index < 0 || index >= value->len) {
        /* `lox_panic` stores the message pointer in a catchable error, so a stack
         * buffer would dangle after unwinding; allocate the text on the GC heap. */
        char message[128];
        int length = snprintf(
            message, sizeof message,
            "Bytes index %" PRId64 " out of bounds for length %" PRId64 ".",
            index, value->len);
        LoxStr *text = string_from_bytes(message, (size_t)length, length);
        lox_panic(line, column, "R1007", lox_str_bytes(text));
        return 0;
    }
    return (int64_t)value->data[index];
}

int lox_bytes_equal(const void *left_pointer, const void *right_pointer) {
    if (left_pointer == right_pointer) {
        return 1;
    }
    const LoxBytes *left = left_pointer;
    const LoxBytes *right = right_pointer;
    if (left->len != right->len) {
        return 0;
    }
    if (left->len == 0) {
        return 1;
    }
    return memcmp(left->data, right->data, (size_t)left->len) == 0;
}

void *lox_bytes_slice(const void *pointer, int64_t start, int64_t end,
                      int32_t line, int32_t column) {
    const LoxBytes *value = pointer;
    if (start < 0 || end < start || end > value->len) {
        lox_panic(line, column, "R1007", "Bytes.slice() index out of bounds.");
        return NULL;
    }
    LoxBytes *result = lox_bytes_new(end - start);
    if (end > start) {
        memcpy(result->data, value->data + start, (size_t)(end - start));
    }
    return result;
}

void *lox_bytes_concat(const void *left_pointer, const void *right_pointer) {
    const LoxBytes *left = left_pointer;
    const LoxBytes *right = right_pointer;
    LoxBytes *result = lox_bytes_new(left->len + right->len);
    if (left->len > 0) {
        memcpy(result->data, left->data, (size_t)left->len);
    }
    if (right->len > 0) {
        memcpy(result->data + left->len, right->data, (size_t)right->len);
    }
    return result;
}

void *lox_bytes_from_text(const void *text_pointer) {
    const LoxStr *text = text_pointer;
    LoxBytes *result = lox_bytes_new(text->byte_len);
    if (text->byte_len > 0) {
        memcpy(result->data, lox_str_bytes(text), (size_t)text->byte_len);
    }
    return result;
}

void *lox_bytes_from_list(const void *list_pointer, int32_t line,
                          int32_t column) {
    int64_t count = lox_list_len(list_pointer);
    LoxBytes *result = lox_bytes_new(count);
    for (int64_t index = 0; index < count; index++) {
        LoxValue item = lox_list_get(list_pointer, index, line, column);
        if (item.tag != 1 || item.payload < 0 || item.payload > 255) {
            lox_panic(line, column, "R1000",
                      "Bytes.fromList() expects integers in 0..255.");
            return NULL;
        }
        result->data[index] = (unsigned char)item.payload;
    }
    return result;
}

void *lox_bytes_from_hex(const void *text_pointer) {
    const LoxStr *text = text_pointer;
    if (text->byte_len % 2 != 0) {
        return result_err(
            bytes_error("InvalidHex", "expected an even number of hex digits."));
    }
    const char *bytes = lox_str_bytes(text);
    LoxBytes *result = lox_bytes_new(text->byte_len / 2);
    for (int64_t index = 0; index < result->len; index++) {
        int high = hex_digit(bytes[index * 2]);
        int low = hex_digit(bytes[index * 2 + 1]);
        if (high < 0 || low < 0) {
            return result_err(
                bytes_error("InvalidHex", "expected hexadecimal digits."));
        }
        result->data[index] = (unsigned char)((high << 4) | low);
    }
    return result_ok(result);
}

void *lox_bytes_from_base64(const void *text_pointer) {
    const LoxStr *text = text_pointer;
    int64_t length = text->byte_len;
    if (length % 4 != 0) {
        return result_err(bytes_error("InvalidBase64", "expected canonical base64."));
    }
    if (length == 0) {
        return result_ok(lox_bytes_new(0));
    }

    const char *bytes = lox_str_bytes(text);
    int64_t padding = 0;
    if (bytes[length - 1] == '=') {
        padding += 1;
    }
    if (length > 1 && bytes[length - 2] == '=') {
        padding += 1;
    }
    for (int64_t index = 0; index < length; index++) {
        char value = bytes[index];
        if (value == '=') {
            if (index < length - 2) {
                return result_err(
                    bytes_error("InvalidBase64", "expected canonical base64."));
            }
        } else if (base64_digit(value) < 0) {
            return result_err(bytes_error("InvalidBase64", "expected canonical base64."));
        }
    }

    int64_t out_length = (length / 4) * 3 - padding;
    LoxBytes *result = lox_bytes_new(out_length);
    int64_t out = 0;
    for (int64_t index = 0; index < length; index += 4) {
        int v0 = base64_digit(bytes[index]);
        int v1 = base64_digit(bytes[index + 1]);
        int v2 = bytes[index + 2] == '=' ? 0 : base64_digit(bytes[index + 2]);
        int v3 = bytes[index + 3] == '=' ? 0 : base64_digit(bytes[index + 3]);
        if (v0 < 0 || v1 < 0 || (v2 < 0 && bytes[index + 2] != '=') ||
            (v3 < 0 && bytes[index + 3] != '=')) {
            return result_err(bytes_error("InvalidBase64", "expected canonical base64."));
        }
        result->data[out++] = (unsigned char)((v0 << 2) | (v1 >> 4));
        if (bytes[index + 2] != '=') {
            result->data[out++] = (unsigned char)(((v1 & 0x0f) << 4) | (v2 >> 2));
        }
        if (bytes[index + 3] != '=') {
            result->data[out++] = (unsigned char)(((v2 & 0x03) << 6) | v3);
        }
    }

    LoxStr *encoded = lox_bytes_to_base64(result);
    if (encoded->byte_len != length ||
        memcmp(lox_str_bytes(encoded), bytes, (size_t)length) != 0) {
        return result_err(bytes_error("InvalidBase64", "expected canonical base64."));
    }
    return result_ok(result);
}

void *lox_bytes_to_text(const void *pointer) {
    const LoxBytes *value = pointer;
    if (!utf8_valid(value->data, (size_t)value->len)) {
        return result_err(bytes_error("InvalidUtf8", "expected valid UTF-8."));
    }
    LoxStr *text = string_from_bytes((const char *)value->data, (size_t)value->len,
                                     utf8_code_points((const char *)value->data,
                                                      (size_t)value->len));
    return result_ok(text);
}

void *lox_bytes_to_list(const void *pointer) {
    const LoxBytes *value = pointer;
    void *list = lox_list_new();
    for (int64_t index = 0; index < value->len; index++) {
        lox_list_push(list, 1, (int64_t)value->data[index]);
    }
    return list;
}

void *lox_bytes_to_hex(const void *pointer) {
    const LoxBytes *value = pointer;
    if (value->len == 0) {
        return string_from_bytes("", 0, 0);
    }
    int64_t length = value->len * 2;
    char *text = lox_alloc_atomic((size_t)length);
    for (int64_t index = 0; index < value->len; index++) {
        text[index * 2] = HEX_DIGITS[value->data[index] >> 4];
        text[index * 2 + 1] = HEX_DIGITS[value->data[index] & 0x0f];
    }
    return string_from_bytes(text, (size_t)length, length);
}

void *lox_bytes_to_base64(const void *pointer) {
    const LoxBytes *value = pointer;
    int64_t length = ((value->len + 2) / 3) * 4;
    if (length == 0) {
        return string_from_bytes("", 0, 0);
    }
    char *text = lox_alloc_atomic((size_t)length);
    int64_t out = 0;
    int64_t index = 0;
    while (index + 2 < value->len) {
        int chunk = (value->data[index] << 16) | (value->data[index + 1] << 8) |
                    value->data[index + 2];
        text[out++] = BASE64_DIGITS[(chunk >> 18) & 0x3f];
        text[out++] = BASE64_DIGITS[(chunk >> 12) & 0x3f];
        text[out++] = BASE64_DIGITS[(chunk >> 6) & 0x3f];
        text[out++] = BASE64_DIGITS[chunk & 0x3f];
        index += 3;
    }
    if (index < value->len) {
        int chunk = value->data[index] << 16;
        text[out++] = BASE64_DIGITS[(chunk >> 18) & 0x3f];
        if (index + 1 < value->len) {
            chunk |= value->data[index + 1] << 8;
            text[out++] = BASE64_DIGITS[(chunk >> 12) & 0x3f];
            text[out++] = BASE64_DIGITS[(chunk >> 6) & 0x3f];
            text[out++] = '=';
        } else {
            text[out++] = BASE64_DIGITS[(chunk >> 12) & 0x3f];
            text[out++] = '=';
            text[out++] = '=';
        }
    }
    return string_from_bytes(text, (size_t)length, length);
}

void *lox_bytes_str(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_bytes(&buffer, pointer);
    return string_from_bytes(buffer.data, buffer.length, (int64_t)buffer.length);
}

void format_bytes(LoxBuffer *buffer, const LoxBytes *value) {
    buffer_text(buffer, "0x");
    for (int64_t index = 0; index < value->len; index++) {
        buffer_char(buffer, HEX_DIGITS[value->data[index] >> 4]);
        buffer_char(buffer, HEX_DIGITS[value->data[index] & 0x0f]);
    }
}

void lox_print_bytes(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_bytes(&buffer, pointer);
    if (buffer.length > 0) {
        fwrite(buffer.data, 1, buffer.length, stdout);
    }
    fputc('\n', stdout);
}
