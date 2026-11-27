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

#include <errno.h>
#include <fcntl.h>
#include <unistd.h>

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
    memcpy(data, lox_str_bytes(string) + begin, length);
    data[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = end - start;
    result->flat = data;
    result->cp_offsets = NULL;
    result->hash = 0;
    result->left = NULL;
    result->right = NULL;
    return result;
}

/* `join(parts, separator)`; any element that is not a String is R1000. */
void *lox_join(const void *parts_pointer, const void *separator_pointer,
               int32_t line, int32_t column) {
    const LoxList *parts = parts_pointer;
    const LoxStr *separator = separator_pointer;
    size_t bytes = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        LoxValue item = lox_list_value_at(parts, index);
        if (item.tag != 4) {
            lox_panic(line, column, "R1000", "join() expects List[String].");
        }
        bytes += (size_t)((const LoxStr *)item.payload)->byte_len;
        if (index + 1 < parts->count) {
            bytes += (size_t)separator->byte_len;
        }
    }
    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes + 1);
    char *data = (char *)(result + 1);
    size_t used = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        const LoxStr *item = (const LoxStr *)lox_list_value_at(parts, index).payload;
        memcpy(data + used, lox_str_bytes(item), (size_t)item->byte_len);
        used += (size_t)item->byte_len;
        if (index + 1 < parts->count) {
            memcpy(data + used, lox_str_bytes(separator), (size_t)separator->byte_len);
            used += (size_t)separator->byte_len;
        }
    }
    data[used] = '\0';
    result->byte_len = (int64_t)used;
    result->cp_len = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        result->cp_len += ((const LoxStr *)lox_list_value_at(parts, index).payload)->cp_len;
        if (index + 1 < parts->count) {
            result->cp_len += separator->cp_len;
        }
    }
    result->flat = data;
    result->cp_offsets = NULL;
    result->hash = 0;
    result->left = NULL;
    result->right = NULL;
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
    return utf8_decode((const unsigned char *)lox_str_bytes(string) + offset, &length);
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
    result->flat = data;
    result->cp_offsets = NULL;
    result->hash = 0;
    result->left = NULL;
    result->right = NULL;
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
    fwrite(lox_str_bytes(text), 1, (size_t)text->byte_len, stdout);
    fflush(stdout);
}

/* `io.writeErr`: raw bytes to stderr + immediate flush. */
void lox_io_write_err(const void *pointer) {
    const LoxStr *text = pointer;
    fwrite(lox_str_bytes(text), 1, (size_t)text->byte_len, stderr);
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
    memcpy(path_copy, lox_str_bytes(path), (size_t)path->byte_len);
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
    memcpy(path_copy, lox_str_bytes(path), (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    FILE *file = fopen(path_copy, "wb");
    if (file == NULL) {
        return 0;
    }
    size_t written = fwrite(lox_str_bytes(text), 1, (size_t)text->byte_len, file);
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
    if (memchr(lox_str_bytes(path), '\0', (size_t)path->byte_len) != NULL) {
        return 0;
    }
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, lox_str_bytes(path), (size_t)path->byte_len);
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
    if (memchr(lox_str_bytes(path), '\0', (size_t)path->byte_len) != NULL) {
        return NULL;
    }
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, lox_str_bytes(path), (size_t)path->byte_len);
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
    memcpy(name_copy, lox_str_bytes(name), (size_t)name->byte_len);
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

size_t utf8_complete_prefix(const unsigned char *data, size_t length) {
    size_t cut = length;
    size_t back = 0;
    while (cut > 0 && back < 3 && (data[cut - 1] & 0xC0) == 0x80) {
        cut -= 1;
        back += 1;
    }
    if (cut == 0) {
        return 0;
    }
    unsigned char lead = data[cut - 1];
    size_t need = lead < 0x80   ? 1
                  : (lead & 0xE0) == 0xC0 ? 2
                  : (lead & 0xF0) == 0xE0 ? 3
                                          : 4;
    size_t have = length - (cut - 1);
    return have >= need ? length : cut - 1;
}

/* ---------------------------------------------------------------------------
 * File handles: `fs.open`, `fs.read`, `fs.write`, `fs.close` (ADR-0119)
 * --------------------------------------------------------------------------- */

#ifndef LOX_MAX_FS_HANDLES
#define LOX_MAX_FS_HANDLES 128
#endif

/* `pending` guards UTF-8 boundaries: an incomplete sequence from the previous
 * read waits here (up to 3 bytes) and is completed by the next call. */
typedef struct {
    int used;
    int fd;
    int writable;
    unsigned char pending[4];
    size_t pending_len;
} LoxFsHandle;

static LoxFsHandle lox_fs_handles[LOX_MAX_FS_HANDLES];

static const char *fs_kind(int error) {
    switch (error) {
        case ENOENT: return "notFound";
        case EACCES:
        case EPERM: return "permission";
        case EISDIR: return "isDirectory";
        case ENOTDIR: return "notDirectory";
        case EEXIST: return "alreadyExists";
        case EMFILE:
        case ENFILE: return "tooManyFiles";
        case ENOSPC: return "noSpace";
        case ENOTEMPTY: return "notEmpty";
        case EXDEV: return "crossDevice";
        default: return "io";
    }
}

/* Panic messages must outlive `lox_panic` (it stores the pointer in a catchable
 * error), so they are static strings chosen by kind — never a stack buffer. */
static const char *fs_open_message(int error) {
    switch (error) {
        case ENOENT: return "notFound: can't open the file.";
        case EACCES:
        case EPERM: return "permission: can't open the file.";
        case EISDIR: return "isDirectory: can't open a directory.";
        case ENOTDIR: return "notDirectory: can't open the file.";
        case EMFILE:
        case ENFILE: return "tooManyFiles: can't open the file.";
        case ENOSPC: return "noSpace: can't open the file.";
        default: return "io: can't open the file.";
    }
}

static const char *fs_read_message(int error) {
    switch (error) {
        case ENOENT: return "notFound: read failed.";
        case EACCES:
        case EPERM: return "permission: read failed.";
        case EISDIR: return "isDirectory: read failed.";
        case ENOTDIR: return "notDirectory: read failed.";
        case EEXIST: return "alreadyExists: read failed.";
        case EMFILE:
        case ENFILE: return "tooManyFiles: read failed.";
        case ENOSPC: return "noSpace: read failed.";
        default: return "io: read failed.";
    }
}

static const char *fs_write_message(int error) {
    switch (error) {
        case EACCES:
        case EPERM: return "permission: write failed.";
        case ENOSPC: return "noSpace: write failed.";
        default: return "io: write failed.";
    }
}

static const char *fs_rename_message(int error) {
    switch (error) {
        case ENOENT: return "notFound: can't rename.";
        case EACCES:
        case EPERM: return "permission: can't rename.";
        case EISDIR: return "isDirectory: can't rename over a directory.";
        case ENOTDIR: return "notDirectory: can't rename.";
        case ENOTEMPTY: return "notEmpty: can't rename.";
        case EEXIST: return "alreadyExists: can't rename.";
        case EXDEV: return "crossDevice: can't rename across filesystems.";
        case ENOSPC: return "noSpace: can't rename.";
        default: return "io: can't rename.";
    }
}

static const char *fs_remove_message(int error) {
    switch (error) {
        case ENOENT: return "notFound: can't remove.";
        case EACCES:
        case EPERM: return "permission: can't remove.";
        case EISDIR: return "isDirectory: can't remove a directory.";
        case ENOTDIR: return "notDirectory: can't remove.";
        default: return "io: can't remove.";
    }
}

static const char *fs_mkdir_message(int error) {
    switch (error) {
        case ENOENT: return "notFound: can't create the directory.";
        case EACCES:
        case EPERM: return "permission: can't create the directory.";
        case EEXIST: return "alreadyExists: can't create the directory.";
        case ENOTDIR: return "notDirectory: can't create the directory.";
        case ENOSPC: return "noSpace: can't create the directory.";
        default: return "io: can't create the directory.";
    }
}

static const char *fs_stat_message(int error) {
    switch (error) {
        case ENOENT: return "notFound: can't stat.";
        case EACCES:
        case EPERM: return "permission: can't stat.";
        case ENOTDIR: return "notDirectory: can't stat.";
        default: return "io: can't stat.";
    }
}

/* Copia uma string Lox para `char *`; NUL interno é caminho inválido, não
 * um truncamento silencioso (o Python rejeita com ValueError). */
static char *fs_c_string(const void *pointer, int32_t line, int32_t column) {
    const LoxStr *string = pointer;
    if (memchr(lox_str_bytes(string), '\0', (size_t)string->byte_len) != NULL) {
        lox_panic(line, column, "R1000", "io: invalid path.");
        return NULL;
    }
    char *copy = lox_alloc_atomic((size_t)string->byte_len + 1);
    memcpy(copy, lox_str_bytes(string), (size_t)string->byte_len);
    copy[string->byte_len] = '\0';
    return copy;
}

/* `fs.rename(src, dst)`: POSIX rename semantics — atomic, replaces the target. */
void lox_fs_rename(const void *source_pointer, const void *target_pointer, int32_t line,
                   int32_t column) {
    char *source = fs_c_string(source_pointer, line, column);
    char *target = fs_c_string(target_pointer, line, column);
    if (rename(source, target) != 0) {
        lox_panic(line, column, "R1000", fs_rename_message(errno));
    }
}

/* `fs.remove(path)`: file or symlink; a directory is `isDirectory`. */
void lox_fs_remove(const void *path_pointer, int32_t line, int32_t column) {
    char *path = fs_c_string(path_pointer, line, column);
    if (unlink(path) != 0) {
        /* macOS returns EPERM for unlink(directory); normalize the kind to match
         * Linux (EISDIR), so the public `kind` is platform independent. */
        int error = errno;
        struct stat info;
        if (stat(path, &info) == 0 && S_ISDIR(info.st_mode)) {
            lox_panic(line, column, "R1000", "isDirectory: can't remove a directory.");
            return;
        }
        lox_panic(line, column, "R1000", fs_remove_message(error));
    }
}

/* `fs.mkdir(path)`: one level; an existing path is `alreadyExists`. */
void lox_fs_mkdir(const void *path_pointer, int32_t line, int32_t column) {
    char *path = fs_c_string(path_pointer, line, column);
    if (mkdir(path, 0777) != 0) {
        lox_panic(line, column, "R1000", fs_mkdir_message(errno));
    }
}

/* `fs.stat(path)`: `(size, mtimeMs, isDir)`, following symlinks. */
void *lox_fs_stat(const void *path_pointer, int32_t line, int32_t column) {
    char *path = fs_c_string(path_pointer, line, column);
    struct stat info;
    if (stat(path, &info) != 0) {
        lox_panic(line, column, "R1000", fs_stat_message(errno));
        return NULL;
    }
    void *tuple = lox_tuple_new(3);
    /* Tags mirror ANY_TAG_INT/ANY_TAG_BOOL (lower_model.py). */
    lox_tuple_set(tuple, 0, 1, (int64_t)info.st_size);
#if defined(__APPLE__)
    int64_t mtime_ms = (int64_t)info.st_mtimespec.tv_sec * 1000 +
                       (int64_t)(info.st_mtimespec.tv_nsec / 1000000L);
#else
    int64_t mtime_ms = (int64_t)info.st_mtim.tv_sec * 1000 +
                       (int64_t)(info.st_mtim.tv_nsec / 1000000L);
#endif
    lox_tuple_set(tuple, 1, 1, mtime_ms);
    lox_tuple_set(tuple, 2, 3, S_ISDIR(info.st_mode) ? 1 : 0);
    return tuple;
}

/* `digest.sha256(text)`: lowercase hex of the UTF-8 bytes (FIPS 180-4). */
void *lox_digest_sha256(const void *text_pointer) {
    const LoxStr *text = text_pointer;
    unsigned char digest[32];
    lox_sha256((const unsigned char *)lox_str_bytes(text), (size_t)text->byte_len, digest);
    static const char hex_digits[] = "0123456789abcdef";
    char output[64];
    for (int index = 0; index < 32; index++) {
        output[index * 2] = hex_digits[digest[index] >> 4];
        output[index * 2 + 1] = hex_digits[digest[index] & 0x0F];
    }
    return string_from_bytes(output, 64, 64);
}

/* `digest.sha256Bytes(data)`: the raw 32-byte digest (FIPS 180-4). */
void *lox_digest_sha256_bytes(const void *bytes_pointer) {
    const LoxBytes *data = bytes_pointer;
    LoxBytes *output = lox_bytes_new(32);
    lox_sha256(data->data, (size_t)data->len, output->data);
    return output;
}

static LoxFsHandle *fs_handle_at(int64_t id, int32_t line, int32_t column) {
    if (id < 1 || id > LOX_MAX_FS_HANDLES) {
        lox_panic(line, column, "R1000", "fs: invalid handle.");
        return NULL;
    }
    LoxFsHandle *handle = &lox_fs_handles[id - 1];
    if (!handle->used) {
        lox_panic(line, column, "R1000", "closed: handle is already closed.");
        return NULL;
    }
    return handle;
}

/* `fs.open(path, mode)`: 1-based handle, or R1000 with a stable kind prefix. */
int64_t lox_fs_open(const void *path_pointer, const void *mode_pointer, int32_t line,
                    int32_t column) {
    const LoxStr *mode = mode_pointer;
    int flags;
    int writable = 0;
    if (mode->byte_len == 1 && lox_str_bytes(mode)[0] == 'r') {
        flags = O_RDONLY;
    } else if (mode->byte_len == 1 && lox_str_bytes(mode)[0] == 'w') {
        flags = O_WRONLY | O_CREAT | O_TRUNC;
        writable = 1;
    } else if (mode->byte_len == 1 && lox_str_bytes(mode)[0] == 'a') {
        flags = O_WRONLY | O_CREAT | O_APPEND;
        writable = 1;
    } else {
        lox_panic(line, column, "R1000", "badMode: expected 'r', 'w' or 'a'.");
        return 0;
    }
    char *path = fs_c_string(path_pointer, line, column);
    int fd;
    do {
        fd = open(path, flags, 0644);
    } while (fd < 0 && errno == EINTR);
    if (fd < 0) {
        lox_panic(line, column, "R1000", fs_open_message(errno));
        return 0;
    }
    for (int index = 0; index < LOX_MAX_FS_HANDLES; index++) {
        if (lox_fs_handles[index].used) {
            continue;
        }
        lox_fs_handles[index].used = 1;
        lox_fs_handles[index].fd = fd;
        lox_fs_handles[index].writable = writable;
        lox_fs_handles[index].pending_len = 0;
        return (int64_t)index + 1;
    }
    close(fd);
    lox_panic(line, column, "R1000", "tooManyFiles: too many open files.");
    return 0;
}

/* `fs.read(id, n)`: at most n bytes, always a complete UTF-8 prefix; NULL is EOF. */
void *lox_fs_read(int64_t id, int64_t count, int32_t line, int32_t column) {
    LoxFsHandle *handle = fs_handle_at(id, line, column);
    if (handle == NULL) {
        return NULL;
    }
    if (handle->writable) {
        lox_panic(line, column, "R1000", "badMode: handle is not open for reading.");
        return NULL;
    }
    if (count < 0) {
        lox_panic(line, column, "R1000", "fs.read() expects a non-negative size.");
        return NULL;
    }
    if (count == 0) {
        return string_from_bytes("", 0, 0);
    }
    if (handle->pending_len > 0 && (size_t)count <= handle->pending_len) {
        return string_from_bytes("", 0, 0);
    }
    size_t want = (size_t)count;
    unsigned char *buffer = lox_alloc_atomic(want);
    size_t total = 0;
    if (handle->pending_len > 0) {
        total = handle->pending_len < want ? handle->pending_len : want;
        memcpy(buffer, handle->pending, total);
        if (handle->pending_len > total) {
            memmove(handle->pending, handle->pending + total, handle->pending_len - total);
            handle->pending_len -= total;
        } else {
            handle->pending_len = 0;
        }
    }
    int eof = 0;
    while (total < want) {
        ssize_t got;
        do {
            got = read(handle->fd, buffer + total, want - total);
        } while (got < 0 && errno == EINTR);
        if (got < 0) {
            lox_panic(line, column, "R1000", fs_read_message(errno));
            return NULL;
        }
        if (got == 0) {
            eof = 1;
            break;
        }
        total += (size_t)got;
    }
    if (total == 0) {
        return NULL;
    }
    size_t cut = utf8_complete_prefix(buffer, total);
    if (cut < total) {
        size_t keep = total - cut;
        if (keep > sizeof handle->pending) {
            keep = sizeof handle->pending;
        }
        memcpy(handle->pending, buffer + cut, keep);
        handle->pending_len = keep;
        total = cut;
    }
    if (total == 0) {
        if (eof) {
            lox_panic(line, column, "R1000", "io: file ends inside a UTF-8 sequence.");
        }
        return string_from_bytes("", 0, 0);
    }
    if (!utf8_valid(buffer, total)) {
        lox_panic(line, column, "R1000", "io: file is not valid UTF-8.");
        return NULL;
    }
    return string_from_bytes((const char *)buffer, total,
                             utf8_code_points((const char *)buffer, total));
}

/* `fs.readBytes(id, n)`: at most `n` raw bytes (no UTF-8), or NULL at EOF. */
void *lox_fs_read_bytes(int64_t id, int64_t count, int32_t line, int32_t column) {
    LoxFsHandle *handle = fs_handle_at(id, line, column);
    if (handle == NULL) {
        return NULL;
    }
    if (handle->writable) {
        lox_panic(line, column, "R1000", "badMode: handle is not open for reading.");
        return NULL;
    }
    if (count < 0) {
        lox_panic(line, column, "R1000",
                  "fs.readBytes() expects a non-negative size.");
        return NULL;
    }
    if (count == 0) {
        return lox_bytes_new(0);
    }
    LoxBytes *value = lox_bytes_new(count);
    size_t total = 0;
    if (handle->pending_len > 0) {
        size_t take = handle->pending_len < (size_t)count ? handle->pending_len
                                                           : (size_t)count;
        memcpy(value->data, handle->pending, take);
        if (handle->pending_len > take) {
            memmove(handle->pending, handle->pending + take,
                    handle->pending_len - take);
            handle->pending_len -= take;
        } else {
            handle->pending_len = 0;
        }
        total = take;
    }
    if (total < (size_t)count) {
        ssize_t got;
        do {
            got = read(handle->fd, value->data + total, (size_t)count - total);
        } while (got < 0 && errno == EINTR);
        if (got < 0) {
            lox_panic(line, column, "R1000", fs_read_message(errno));
            return NULL;
        }
        if (got > 0) {
            total += (size_t)got;
        }
    }
    if (total == 0) {
        return NULL;
    }
    value->len = (int64_t)total;
    return value;
}

/* `fs.write(id, text)`: writes every byte, retrying EINTR. */
void lox_fs_write(int64_t id, const void *text_pointer, int32_t line, int32_t column) {
    LoxFsHandle *handle = fs_handle_at(id, line, column);
    if (handle == NULL) {
        return;
    }
    if (!handle->writable) {
        lox_panic(line, column, "R1000", "badMode: handle is not open for writing.");
        return;
    }
    const LoxStr *text = text_pointer;
    const char *cursor = lox_str_bytes(text);
    size_t remaining = (size_t)text->byte_len;
    while (remaining > 0) {
        ssize_t written = write(handle->fd, cursor, remaining);
        if (written < 0) {
            if (errno == EINTR) {
                continue;
            }
            lox_panic(line, column, "R1000", fs_write_message(errno));
            return;
        }
        cursor += written;
        remaining -= (size_t)written;
    }
}

/* `fs.close(id)`: idempotent; an id that never existed is R1000. */
void lox_fs_close(int64_t id, int32_t line, int32_t column) {
    if (id < 1 || id > LOX_MAX_FS_HANDLES) {
        lox_panic(line, column, "R1000", "fs: invalid handle.");
        return;
    }
    LoxFsHandle *handle = &lox_fs_handles[id - 1];
    if (!handle->used) {
        return;
    }
    close(handle->fd);
    handle->used = 0;
    handle->pending_len = 0;
}
