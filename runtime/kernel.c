/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * kernel.c — kernel 13.2 host primitives: strings, UTF-8, stdin/stdout, files,
 * environment, `os.exit`, `time.*` and `args`.
 *
 * Who calls it: generated code calls these symbols directly; the signatures come
 * from `kernel_gen.h`, generated from `loxia_core/execution/primitives.py`. The
 * stdlib (`std/fs.lx`, `std/io.lx`) is a thin shell over them.
 *
 * Invariants:
 *  - `site: true` in `primitives.py` appends `(line, column)` to the signature;
 *    pass them to `lox_panic` so errors point at the call;
 *  - ambient operations (files, stdin, env, clock) stay outside the I1 corpus;
 *  - `fs.listDir` order is byte-sorted (I3);
 *  - `io.readUtf8` validates strict UTF-8; `io.write*` flushes for observable
 *    ordering with stderr;
 *  - paths and values handed to the OS are copied into C strings.
 *
 * ADRs: 0071 (primitives), 0094 (io flush/readUtf8), 0095 (processes).
 */
#include "lox_runtime.h"
#include "kernel_gen.h"

/* ---------------------------------------------------------------------------
 * Kernel strings
 * --------------------------------------------------------------------------- */

/* `substr(s, start, end)` with code-point indices. `start < 0`, `end < start`
 * or `end > cp_len` is R1000. */
void *lox_substr(const void *pointer, int64_t start, int64_t end,
                 int32_t line, int32_t column) {
    const LoxStr *string = pointer;
    if (start < 0 || end < start || end > string->cp_len) {
        lox_panic(line, column, "R1000", "substr() index out of bounds.");
        return NULL;
    }
    int64_t begin = utf8_cp_offset(string, start);
    int64_t finish = utf8_cp_offset(string, end);
    size_t length = (size_t)(finish - begin);
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *data = (char *)(result + 1);
    memcpy(data, string->data + begin, length);
    data[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = end - start;
    result->data = data;
    result->cp_offsets = NULL;
    return result;
}

/* `join(parts, separator)`; any element that is not a String is R1000. */
void *lox_join(const void *parts_pointer, const void *separator_pointer,
               int32_t line, int32_t column) {
    const LoxList *parts = parts_pointer;
    const LoxStr *separator = separator_pointer;
    size_t bytes = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        const LoxValue *item = &parts->items[index];
        if (item->tag != 4) {
            lox_panic(line, column, "R1000", "join() expects List[String].");
        }
        bytes += (size_t)((const LoxStr *)item->payload)->byte_len;
        if (index + 1 < parts->count) {
            bytes += (size_t)separator->byte_len;
        }
    }
    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes + 1);
    char *data = (char *)(result + 1);
    size_t used = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        const LoxStr *item = (const LoxStr *)parts->items[index].payload;
        memcpy(data + used, item->data, (size_t)item->byte_len);
        used += (size_t)item->byte_len;
        if (index + 1 < parts->count) {
            memcpy(data + used, separator->data, (size_t)separator->byte_len);
            used += (size_t)separator->byte_len;
        }
    }
    data[used] = '\0';
    result->byte_len = (int64_t)used;
    result->cp_len = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        result->cp_len += ((const LoxStr *)parts->items[index].payload)->cp_len;
        if (index + 1 < parts->count) {
            result->cp_len += separator->cp_len;
        }
    }
    result->data = data;
    result->cp_offsets = NULL;
    return result;
}


/* `charCodeAt(s, i)`: Unicode code point at a code-point index; R1000 when out
 * of bounds. */
int64_t lox_char_code_at(const void *pointer, int64_t index, int32_t line,
                         int32_t column) {
    const LoxStr *string = pointer;
    if (index < 0 || index >= string->cp_len) {
        lox_panic(line, column, "R1000", "charCodeAt() index out of bounds.");
    }
    int64_t offset = utf8_cp_offset(string, index);
    size_t length = 0;
    return utf8_decode((const unsigned char *)string->data + offset, &length);
}

/* `fromCodePoint`: builds a one-code-point String; rejects surrogates and values
 * above U+10FFFF with R1000. */
void *lox_from_code_point(int64_t code_point, int32_t line, int32_t column) {
    if (code_point < 0 || code_point > 0x10FFFF ||
        (code_point >= 0xD800 && code_point <= 0xDFFF)) {
        lox_panic(line, column, "R1000",
                  "fromCodePoint() expects a valid Unicode code point.");
    }
    char bytes[4];
    size_t length;
    if (code_point < 0x80) {
        bytes[0] = (char)code_point;
        length = 1;
    } else if (code_point < 0x800) {
        bytes[0] = (char)(0xC0 | (code_point >> 6));
        bytes[1] = (char)(0x80 | (code_point & 0x3F));
        length = 2;
    } else if (code_point < 0x10000) {
        bytes[0] = (char)(0xE0 | (code_point >> 12));
        bytes[1] = (char)(0x80 | ((code_point >> 6) & 0x3F));
        bytes[2] = (char)(0x80 | (code_point & 0x3F));
        length = 3;
    } else {
        bytes[0] = (char)(0xF0 | (code_point >> 18));
        bytes[1] = (char)(0x80 | ((code_point >> 12) & 0x3F));
        bytes[2] = (char)(0x80 | ((code_point >> 6) & 0x3F));
        bytes[3] = (char)(0x80 | (code_point & 0x3F));
        length = 4;
    }
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *data = (char *)(result + 1);
    memcpy(data, bytes, length);
    data[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = 1;
    result->data = data;
    result->cp_offsets = NULL;
    return result;
}



/* ---------------------------------------------------------------------------
 * UTF-8 helpers and `args`
 * --------------------------------------------------------------------------- */

/* Counts leading bytes (code points); it does not validate the sequence. */
int64_t utf8_code_points(const char *data, size_t length) {
    int64_t count = 0;
    for (size_t index = 0; index < length; index++) {
        unsigned char byte = (unsigned char)data[index];
        if ((byte & 0xC0) != 0x80) {
            count += 1;
        }
    }
    return count;
}

/*
 * Strict UTF-8: rejects overlong encodings, surrogates, values above U+10FFFF and
 * truncated sequences. Mirrors the oracle's `bytes.decode("utf-8")` (io.readUtf8).
 */
int utf8_valid(const unsigned char *data, size_t length) {
    size_t index = 0;
    while (index < length) {
        unsigned char byte = data[index];
        if (byte < 0x80) {
            index += 1;
            continue;
        }
        size_t extra;
        uint32_t code;
        uint32_t minimum;
        if ((byte & 0xE0) == 0xC0) {
            extra = 1;
            code = byte & 0x1Fu;
            minimum = 0x80;
        } else if ((byte & 0xF0) == 0xE0) {
            extra = 2;
            code = byte & 0x0Fu;
            minimum = 0x800;
        } else if ((byte & 0xF8) == 0xF0) {
            extra = 3;
            code = byte & 0x07u;
            minimum = 0x10000;
        } else {
            return 0;
        }
        if (index + extra >= length) {
            return 0;
        }
        for (size_t offset = 1; offset <= extra; offset++) {
            unsigned char next = data[index + offset];
            if ((next & 0xC0) != 0x80) {
                return 0;
            }
            code = (code << 6) | (next & 0x3Fu);
        }
        if (code < minimum || code > 0x10FFFF) {
            return 0;
        }
        if (code >= 0xD800 && code <= 0xDFFF) {
            return 0;
        }
        index += extra + 1;
    }
    return 1;
}

/* `args()`: argv without argv[0], each entry as a String. */
void *lox_args(void) {
    void *list = lox_list_new();
    for (int32_t index = 1; index < lox_argc; index++) {
        const char *argument = lox_argv[index];
        size_t length = strlen(argument);
        lox_list_push(list, 4, (int64_t)string_from_bytes(
            argument, length, utf8_code_points(argument, length)));
    }
    return list;
}

/* ---------------------------------------------------------------------------
 * Standard I/O
 * --------------------------------------------------------------------------- */

/* `io.write`: raw bytes + immediate flush (ordering with stderr matters). */
void lox_io_write(const void *pointer) {
    const LoxStr *text = pointer;
    fwrite(text->data, 1, (size_t)text->byte_len, stdout);
    fflush(stdout);
}

/* `io.writeErr`: raw bytes to stderr + immediate flush. */
void lox_io_write_err(const void *pointer) {
    const LoxStr *text = pointer;
    fwrite(text->data, 1, (size_t)text->byte_len, stderr);
    fflush(stderr);
}

/* `io.flush`: flushes stdout and stderr. */
void lox_io_flush(void) {
    fflush(stdout);
    fflush(stderr);
}

/*
 * Reads exactly `count` bytes from stdin and decodes strict UTF-8. `NULL` only on
 * immediate EOF (no bytes); mid-stream EOF or invalid bytes are an error at the
 * call site, like the oracle's `NativeError`.
 */
void *lox_io_read_utf8(int64_t count, int32_t line, int32_t column) {
    if (count < 0) {
        lox_panic(line, column, "R1000",
                  "io.readUtf8() expects a non-negative count.");
        return NULL;
    }
    if (count == 0) {
        return string_from_bytes("", 0, 0);
    }
    LoxBuffer buffer;
    buffer_init(&buffer);
    char chunk[4096];
    while (buffer.length < (size_t)count) {
        size_t want = (size_t)count - buffer.length;
        if (want > sizeof chunk) {
            want = sizeof chunk;
        }
        size_t read = fread(chunk, 1, want, stdin);
        if (read == 0) {
            break;
        }
        buffer_bytes(&buffer, chunk, read);
    }
    if (buffer.length == 0) {
        return NULL;
    }
    if (buffer.length < (size_t)count) {
        char message[64];
        snprintf(message, sizeof message,
                 "io.readUtf8() expects exactly %" PRId64 " bytes.", count);
        lox_panic(line, column, "R1000", message);
        return NULL;
    }
    if (!utf8_valid((const unsigned char *)buffer.data, buffer.length)) {
        lox_panic(line, column, "R1000",
                  "io.readUtf8() expects UTF-8 input.");
        return NULL;
    }
    return string_from_bytes(buffer.data, buffer.length,
                             utf8_code_points(buffer.data, buffer.length));
}

/* `io.readFile`: whole file as a String, or NULL when `fopen` fails.
 *
 * NOTE: unlike the tree-walk, this path does not validate UTF-8; `code_points`
 * is a best-effort count. See `io.readUtf8` for the validating reader. */
void *lox_io_read_file(const void *pointer) {
    const LoxStr *path = pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    FILE *file = fopen(path_copy, "rb");
    if (file == NULL) {
        return NULL;
    }
    LoxBuffer buffer;
    buffer_init(&buffer);
    char chunk[4096];
    size_t read;
    while ((read = fread(chunk, 1, sizeof chunk, file)) > 0) {
        buffer_bytes(&buffer, chunk, read);
    }
    fclose(file);
    return string_from_bytes(buffer.data, buffer.length,
                             utf8_code_points(buffer.data, buffer.length));
}

/* `io.writeFile`: truncates/creates the file and writes all bytes; 1 on success,
 * 0 on any I/O error. */
int32_t lox_io_write_file(const void *path_pointer, const void *text_pointer) {
    const LoxStr *path = path_pointer;
    const LoxStr *text = text_pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    FILE *file = fopen(path_copy, "wb");
    if (file == NULL) {
        return 0;
    }
    size_t written = fwrite(text->data, 1, (size_t)text->byte_len, file);
    int ok = written == (size_t)text->byte_len;
    if (fclose(file) != 0) {
        ok = 0;
    }
    return ok ? 1 : 0;
}

/* `io.readLine`: one line, stripping LF and a trailing CR; NULL at immediate EOF.
 *
 * NOTE: no UTF-8 validation here (the tree-walk raises on invalid input). */
void *lox_io_read_line(void) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    int byte;
    while ((byte = fgetc(stdin)) != EOF && byte != '\n') {
        buffer_char(&buffer, (char)byte);
    }
    if (byte == EOF && buffer.length == 0) {
        return NULL;
    }
    if (buffer.length > 0 && buffer.data[buffer.length - 1] == '\r') {
        buffer.length -= 1;
    }
    return string_from_bytes(buffer.data, buffer.length,
                             utf8_code_points(buffer.data, buffer.length));
}

/* `io.readAll`: all remaining stdin. No UTF-8 validation on this path. */
void *lox_io_read_all(void) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    char chunk[4096];
    size_t read;
    while ((read = fread(chunk, 1, sizeof chunk, stdin)) > 0) {
        buffer_bytes(&buffer, chunk, read);
    }
    return string_from_bytes(buffer.data, buffer.length,
                             utf8_code_points(buffer.data, buffer.length));
}

/* ---------------------------------------------------------------------------
 * Filesystem
 * --------------------------------------------------------------------------- */

/* `fs.exists`: `stat`-based check for any file, directory or other entry. */
int32_t lox_fs_exists(const void *path_pointer) {
    const LoxStr *path = path_pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    struct stat info;
    return stat(path_copy, &info) == 0 ? 1 : 0;
}

/* `qsort` comparator: byte order (equivalent to code-point order in UTF-8). */
int compare_dir_names(const void *left, const void *right) {
    const char *a = *(const char *const *)left;
    const char *b = *(const char *const *)right;
    return strcmp(a, b);
}

/*
 * Lists in byte order (equivalent to code-point order in UTF-8), excluding "." and
 * "..", so the directory order never leaks (I3). Returns NULL when the path is not
 * a readable directory; the stdlib translates that to nil.
 */
void *lox_fs_list_dir(const void *path_pointer) {
    const LoxStr *path = path_pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    DIR *dir = opendir(path_copy);
    if (dir == NULL) {
        return NULL;
    }
    size_t count = 0;
    size_t capacity = 8;
    char **names = lox_alloc(sizeof(char *) * capacity);
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        const char *name = entry->d_name;
        if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0) {
            continue;
        }
        if (count == capacity) {
            size_t grown_capacity = capacity * 2;
            char **grown = lox_alloc(sizeof(char *) * grown_capacity);
            memcpy(grown, names, sizeof(char *) * count);
            names = grown;
            capacity = grown_capacity;
        }
        size_t length = strlen(name);
        char *copy = lox_alloc_atomic(length + 1);
        memcpy(copy, name, length + 1);
        names[count] = copy;
        count += 1;
    }
    closedir(dir);
    qsort(names, count, sizeof(char *), compare_dir_names);
    void *list = lox_list_new();
    for (size_t index = 0; index < count; index++) {
        size_t length = strlen(names[index]);
        lox_list_push(list, 4, (int64_t)string_from_bytes(
            names[index], length, utf8_code_points(names[index], length)));
    }
    return list;
}

/* ---------------------------------------------------------------------------
 * OS and environment
 * --------------------------------------------------------------------------- */

/* `os.exit`: flushes both streams and exits; a code outside 0..255 is R1000. */
void lox_os_exit(int64_t code, int32_t line, int32_t column) {
    if (code < 0 || code > 255) {
        lox_panic(line, column, "R1000",
                  "os.exit() expects a code between 0 and 255.");
    }
    fflush(stdout);
    fflush(stderr);
    exit((int)code);
}

/* `os.getenv`: NULL becomes nil; the value is copied into a LoxStr. */
void *lox_os_getenv(const void *name_pointer) {
    const LoxStr *name = name_pointer;
    char *name_copy = lox_alloc_atomic((size_t)name->byte_len + 1);
    memcpy(name_copy, name->data, (size_t)name->byte_len);
    name_copy[name->byte_len] = '\0';
    const char *value = getenv(name_copy);
    if (value == NULL) {
        return NULL;
    }
    size_t length = strlen(value);
    return string_from_bytes(value, length, utf8_code_points(value, length));
}

/* ---------------------------------------------------------------------------
 * Time (ambient)
 * --------------------------------------------------------------------------- */

/* `time.now`: milliseconds since the Unix epoch. */
int64_t lox_time_now(void) {
    struct timespec timestamp;
    timespec_get(&timestamp, TIME_UTC);
    return (int64_t)timestamp.tv_sec * 1000 +
           (int64_t)(timestamp.tv_nsec / 1000000);
}

/* `time.sleep`: no-op for 0, loops over `nanosleep` after EINTR; a negative
 * duration is R1000. */
void lox_time_sleep(int64_t milliseconds, int32_t line, int32_t column) {
    if (milliseconds < 0) {
        lox_panic(line, column, "R1000",
                  "time.sleep() expects a non-negative duration.");
    }
    struct timespec duration;
    duration.tv_sec = (time_t)(milliseconds / 1000);
    duration.tv_nsec = (long)((milliseconds % 1000) * 1000000);
    while (nanosleep(&duration, &duration) == -1) {
        /* interrupted by a signal: continue with the remaining time */
    }
}
