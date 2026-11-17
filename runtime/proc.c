/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * proc.c — kernel processes and streams (ADR-0095): `posix_spawnp`, pipes and
 * `poll(2)`.
 *
 * Who calls it: `std/proc.lx` through the `process.*` primitives (kernel_gen.h).
 * The interpreter uses `proc_runtime.py`; messages and semantics must match.
 *
 * Invariants:
 *  - no shell, no threads: argv is a `List[String]` and concurrency is `poll`;
 *  - handles are 1-based ids in `lox_proc_handles`; 0 is never valid;
 *  - a process owns three streams (stdin/stdout/stderr); `close` frees them all;
 *  - `read` only returns complete UTF-8 prefixes and keeps up to 3 pending bytes;
 *  - SIGPIPE is ignored in core.c so `write` returns EPIPE/false.
 *
 * ADRs: 0095 (processes), 0071 (kernel).
 */
#include "lox_runtime.h"
#include "kernel_gen.h"

extern char **environ;

/* ---------------------------------------------------------------------------
 * Handle table
 * --------------------------------------------------------------------------- */

#define LOX_MAX_PROC_HANDLES 256

/* One slot of the fixed handle table. `kind` 0 is free, 1 stream, 2 process.
 * `pending` keeps up to 3 bytes of an incomplete UTF-8 sequence. */
typedef struct {
    int kind; /* 0 free, 1 stream, 2 process */
    int fd;
    pid_t pid;
    int status;
    int has_status;
    int64_t streams[3];
    unsigned char pending[4];
    size_t pending_len;
} LoxProcHandle;

/* Fixed table; ids are 1-based indexes into this array. */
static LoxProcHandle lox_proc_handles[LOX_MAX_PROC_HANDLES];

/* Validates an id and returns its slot; R1000 for a zero/out-of-range/free id. */
static LoxProcHandle *proc_handle_at(int64_t id, int32_t line, int32_t column) {
    if (id < 1 || id > LOX_MAX_PROC_HANDLES) {
        lox_panic(line, column, "R1000", "proc: invalid handle.");
        return NULL;
    }
    LoxProcHandle *handle = &lox_proc_handles[id - 1];
    if (handle->kind == 0) {
        lox_panic(line, column, "R1000", "proc: invalid handle.");
        return NULL;
    }
    return handle;
}

/* Like `proc_handle_at`, but also checks the expected kind and reports a
 * primitive-specific message. */
static LoxProcHandle *proc_require(int64_t id, int kind, const char *name,
                                   int32_t line, int32_t column) {
    LoxProcHandle *handle = proc_handle_at(id, line, column);
    if (handle == NULL) {
        return NULL;
    }
    if (handle->kind != kind) {
        char message[64];
        snprintf(message, sizeof message, "%s() expects a %s handle.", name,
                 kind == 1 ? "stream" : "process");
        lox_panic(line, column, "R1000", message);
        return NULL;
    }
    return handle;
}

/* Finds a free slot and initializes it; 0 when the table is full. */
static int64_t proc_new(int kind) {
    for (int index = 0; index < LOX_MAX_PROC_HANDLES; index++) {
        if (lox_proc_handles[index].kind == 0) {
            LoxProcHandle *handle = &lox_proc_handles[index];
            memset(handle, 0, sizeof *handle);
            handle->kind = kind;
            handle->fd = -1;
            return (int64_t)index + 1;
        }
    }
    return 0;
}

/* Stores the wait status: exit code, or the negated signal number. */
static void proc_record_status(LoxProcHandle *process, int status) {
    process->has_status = 1;
    process->status = WIFEXITED(status) ? WEXITSTATUS(status)
                      : WIFSIGNALED(status) ? -WTERMSIG(status)
                                            : -1;
}

/* ---------------------------------------------------------------------------
 * Spawn and channels
 * --------------------------------------------------------------------------- */

/* Creates three pipes, dup2s them into the child and spawns without a shell.
 * Returns the process id, or 0 on failure (closing every opened fd and slot). */
int64_t lox_proc_spawn(const void *argv_pointer) {
    const LoxList *argv = argv_pointer;
    if (argv->count < 1) {
        return 0;
    }
    char **arguments =
        lox_alloc_atomic(sizeof(char *) * (size_t)(argv->count + 1));
    for (int64_t index = 0; index < argv->count; index++) {
        const LoxValue *item = &argv->items[index];
        if (item->tag != 4) {
            return 0;
        }
        const LoxStr *text = (const LoxStr *)item->payload;
        char *copy = lox_alloc_atomic((size_t)text->byte_len + 1);
        memcpy(copy, text->data, (size_t)text->byte_len);
        copy[text->byte_len] = '\0';
        arguments[index] = copy;
    }
    arguments[argv->count] = NULL;

    int input[2];
    int output[2];
    int error[2];
    if (pipe(input) != 0) {
        return 0;
    }
    if (pipe(output) != 0) {
        close(input[0]);
        close(input[1]);
        return 0;
    }
    if (pipe(error) != 0) {
        close(input[0]);
        close(input[1]);
        close(output[0]);
        close(output[1]);
        return 0;
    }

    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, input[0], 0);
    posix_spawn_file_actions_adddup2(&actions, output[1], 1);
    posix_spawn_file_actions_adddup2(&actions, error[1], 2);
    posix_spawn_file_actions_addclose(&actions, input[0]);
    posix_spawn_file_actions_addclose(&actions, input[1]);
    posix_spawn_file_actions_addclose(&actions, output[0]);
    posix_spawn_file_actions_addclose(&actions, output[1]);
    posix_spawn_file_actions_addclose(&actions, error[0]);
    posix_spawn_file_actions_addclose(&actions, error[1]);

    pid_t pid = 0;
    int result =
        posix_spawnp(&pid, arguments[0], &actions, NULL, arguments, environ);
    posix_spawn_file_actions_destroy(&actions);
    if (result != 0) {
        close(input[0]);
        close(input[1]);
        close(output[0]);
        close(output[1]);
        close(error[0]);
        close(error[1]);
        return 0;
    }

    close(input[0]);
    close(output[1]);
    close(error[1]);

    int64_t process_id = proc_new(2);
    int64_t stdin_id = proc_new(1);
    int64_t stdout_id = proc_new(1);
    int64_t stderr_id = proc_new(1);
    if (process_id == 0 || stdin_id == 0 || stdout_id == 0 || stderr_id == 0) {
        close(input[1]);
        close(output[0]);
        close(error[0]);
        kill(pid, SIGKILL);
        waitpid(pid, NULL, 0);
        if (process_id != 0) {
            memset(&lox_proc_handles[process_id - 1], 0,
                   sizeof(LoxProcHandle));
        }
        if (stdin_id != 0) {
            memset(&lox_proc_handles[stdin_id - 1], 0, sizeof(LoxProcHandle));
        }
        if (stdout_id != 0) {
            memset(&lox_proc_handles[stdout_id - 1], 0, sizeof(LoxProcHandle));
        }
        if (stderr_id != 0) {
            memset(&lox_proc_handles[stderr_id - 1], 0, sizeof(LoxProcHandle));
        }
        return 0;
    }

    LoxProcHandle *process = &lox_proc_handles[process_id - 1];
    process->pid = pid;
    process->streams[0] = stdin_id;
    process->streams[1] = stdout_id;
    process->streams[2] = stderr_id;
    lox_proc_handles[stdin_id - 1].fd = input[1];
    lox_proc_handles[stdout_id - 1].fd = output[0];
    lox_proc_handles[stderr_id - 1].fd = error[0];
    return process_id;
}

/* `process.stdin`: stream id of the child's stdin pipe. */
int64_t lox_proc_stdin(int64_t id, int32_t line, int32_t column) {
    LoxProcHandle *process = proc_require(id, 2, "process.stdin", line, column);
    return process == NULL ? 0 : process->streams[0];
}

/* `process.stdout`: stream id of the child's stdout pipe. */
int64_t lox_proc_stdout(int64_t id, int32_t line, int32_t column) {
    LoxProcHandle *process = proc_require(id, 2, "process.stdout", line, column);
    return process == NULL ? 0 : process->streams[1];
}

/* `process.stderr`: stream id of the child's stderr pipe. */
int64_t lox_proc_stderr(int64_t id, int32_t line, int32_t column) {
    LoxProcHandle *process = proc_require(id, 2, "process.stderr", line, column);
    return process == NULL ? 0 : process->streams[2];
}

/* `process.wait`: waits once (retrying EINTR), records and caches the status. */
int64_t lox_proc_wait(int64_t id, int32_t line, int32_t column) {
    LoxProcHandle *process = proc_require(id, 2, "process.wait", line, column);
    if (process == NULL) {
        return -1;
    }
    if (!process->has_status) {
        int status = 0;
        pid_t result;
        do {
            result = waitpid(process->pid, &status, 0);
        } while (result < 0 && errno == EINTR);
        if (result < 0) {
            lox_panic(line, column, "R1000", "process.wait() failed.");
            return -1;
        }
        proc_record_status(process, status);
    }
    return process->status;
}

/* `process.kill`: returns 0 when the child was already reaped; otherwise sends
 * SIGKILL and reports whether the signal was delivered. */
int32_t lox_proc_kill(int64_t id, int32_t line, int32_t column) {
    LoxProcHandle *process = proc_require(id, 2, "process.kill", line, column);
    if (process == NULL || process->has_status) {
        return 0;
    }
    int status = 0;
    pid_t reaped = waitpid(process->pid, &status, WNOHANG);
    if (reaped == process->pid) {
        proc_record_status(process, status);
        return 0;
    }
    return kill(process->pid, SIGKILL) == 0 ? 1 : 0;
}

/* `process.close`: closes the stream fd, or all three child streams, and frees
 * the slot. It does not kill a running child. */
void lox_proc_close(int64_t id, int32_t line, int32_t column) {
    LoxProcHandle *handle = proc_handle_at(id, line, column);
    if (handle == NULL) {
        return;
    }
    if (handle->kind == 1) {
        close(handle->fd);
    } else {
        for (int index = 0; index < 3; index++) {
            int64_t stream_id = handle->streams[index];
            if (stream_id > 0) {
                LoxProcHandle *stream = &lox_proc_handles[stream_id - 1];
                if (stream->kind == 1) {
                    close(stream->fd);
                }
                memset(stream, 0, sizeof *stream);
            }
        }
    }
    memset(handle, 0, sizeof *handle);
}

/* ---------------------------------------------------------------------------
 * Stream reads and writes
 * --------------------------------------------------------------------------- */

/* Longest prefix that ends on a UTF-8 character boundary (see proc_runtime.py). */
static size_t utf8_complete_prefix(const unsigned char *data, size_t length) {
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

/* `process.read`: up to `count` bytes, carrying an incomplete UTF-8 sequence in
 * `pending`. Returns NULL at EOF with no bytes; invalid UTF-8 is R1000. */
void *lox_proc_read(int64_t id, int64_t count, int32_t line, int32_t column) {
    LoxProcHandle *stream = proc_require(id, 1, "process.read", line, column);
    if (stream == NULL) {
        return NULL;
    }
    if (count < 0) {
        lox_panic(line, column, "R1000",
                  "process.read() expects a non-negative count.");
        return NULL;
    }
    if (count == 0) {
        return string_from_bytes("", 0, 0);
    }
    if (stream->pending_len > 0 && (size_t)count <= stream->pending_len) {
        return string_from_bytes("", 0, 0);
    }

    size_t want = (size_t)count;
    unsigned char *buffer = lox_alloc_atomic(want);
    size_t total = 0;
    if (stream->pending_len > 0) {
        total = stream->pending_len < want ? stream->pending_len : want;
        memcpy(buffer, stream->pending, total);
        if (stream->pending_len > total) {
            memmove(stream->pending, stream->pending + total,
                    stream->pending_len - total);
            stream->pending_len -= total;
        } else {
            stream->pending_len = 0;
        }
    }

    int eof = 0;
    while (total < want) {
        ssize_t got;
        do {
            got = read(stream->fd, buffer + total, want - total);
        } while (got < 0 && errno == EINTR);
        if (got <= 0) {
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
        if (keep > sizeof stream->pending) {
            keep = sizeof stream->pending;
        }
        memcpy(stream->pending, buffer + cut, keep);
        stream->pending_len = keep;
        total = cut;
    }
    if (total == 0) {
        if (eof) {
            lox_panic(line, column, "R1000",
                      "process.read() expects UTF-8 input.");
        }
        return string_from_bytes("", 0, 0);
    }
    if (!utf8_valid(buffer, total)) {
        lox_panic(line, column, "R1000", "process.read() expects UTF-8 input.");
        return NULL;
    }
    return string_from_bytes((const char *)buffer, total,
                             utf8_code_points((const char *)buffer, total));
}

/* `process.write`: writes every byte, retrying EINTR; 0 when the pipe is closed. */
int32_t lox_proc_write(int64_t id, const void *text_pointer, int32_t line,
                       int32_t column) {
    LoxProcHandle *stream = proc_require(id, 1, "process.write", line, column);
    if (stream == NULL) {
        return 0;
    }
    const LoxStr *text = text_pointer;
    size_t total = 0;
    while (total < (size_t)text->byte_len) {
        ssize_t written;
        do {
            written =
                write(stream->fd, text->data + total,
                      (size_t)text->byte_len - total);
        } while (written < 0 && errno == EINTR);
        if (written <= 0) {
            return 0;
        }
        total += (size_t)written;
    }
    return 1;
}

/* ---------------------------------------------------------------------------
 * Poll
 * --------------------------------------------------------------------------- */

/* Appends an id to `ready[]`, avoiding duplicates. */
static void proc_ready_push(int64_t *ready, size_t *count, int64_t id) {
    for (size_t index = 0; index < *count; index++) {
        if (ready[index] == id) {
            return;
        }
    }
    ready[*count] = id;
    *count += 1;
}

/* `process.poll`: processes are reaped with waitpid(WNOHANG); streams use
 * poll(2). Returns the ready ids (deduplicated). `timeout_ms < 0` waits forever;
 * processes without an fd make the loop wake periodically to check them. */
void *lox_proc_poll(const void *ids_pointer, int64_t timeout_ms, int32_t line,
                    int32_t column) {
    const LoxList *ids = ids_pointer;
    size_t count = (size_t)ids->count;
    size_t size = count > 0 ? count : 1;
    int64_t *identifiers = lox_alloc(sizeof(int64_t) * size);
    int64_t *fd_ids = lox_alloc(sizeof(int64_t) * size);
    struct pollfd *fds = lox_alloc_atomic(sizeof(struct pollfd) * size);
    size_t fd_count = 0;
    int has_processes = 0;

    for (size_t index = 0; index < count; index++) {
        const LoxValue *item = &ids->items[index];
        if (item->tag != 1) {
            lox_panic(line, column, "R1000",
                      "process.poll() expects List[Int].");
            return NULL;
        }
        int64_t id = item->payload;
        LoxProcHandle *handle = proc_handle_at(id, line, column);
        if (handle == NULL) {
            return NULL;
        }
        identifiers[index] = id;
        if (handle->kind == 1) {
            fds[fd_count].fd = handle->fd;
            fds[fd_count].events = POLLIN;
            fds[fd_count].revents = 0;
            fd_ids[fd_count] = id;
            fd_count += 1;
        } else {
            has_processes = 1;
        }
    }

    int64_t deadline = timeout_ms < 0 ? -1 : lox_time_now() + timeout_ms;
    int64_t *ready = lox_alloc(sizeof(int64_t) * size);
    size_t ready_count = 0;
    for (;;) {
        ready_count = 0;
        for (size_t index = 0; index < count; index++) {
            LoxProcHandle *handle = &lox_proc_handles[identifiers[index] - 1];
            if (handle->kind != 2) {
                continue;
            }
            if (handle->has_status) {
                proc_ready_push(ready, &ready_count, identifiers[index]);
                continue;
            }
            int status = 0;
            pid_t reaped = waitpid(handle->pid, &status, WNOHANG);
            if (reaped == handle->pid) {
                proc_record_status(handle, status);
                proc_ready_push(ready, &ready_count, identifiers[index]);
            }
        }
        if (ready_count > 0) {
            break;
        }

        if (fd_count > 0) {
            int wait = -1;
            if (deadline >= 0) {
                int64_t remaining = deadline - lox_time_now();
                wait = remaining < 0
                           ? 0
                           : (remaining > 60000 ? 60000 : (int)remaining);
            } else if (has_processes) {
                /* no deadline: wake up to check processes without an fd */
                wait = 10;
            }
            int result = poll(fds, (nfds_t)fd_count, wait);
            if (result > 0) {
                for (size_t index = 0; index < fd_count; index++) {
                    if (fds[index].revents & (POLLIN | POLLHUP)) {
                        proc_ready_push(ready, &ready_count, fd_ids[index]);
                    }
                }
            }
            if (ready_count > 0) {
                break;
            }
        } else {
            /* no fd: sleep briefly to avoid spinning (also with an empty list) */
            struct timespec pause = {0, 5 * 1000 * 1000};
            nanosleep(&pause, NULL);
        }

        if (deadline >= 0 && lox_time_now() >= deadline) {
            break;
        }
    }

    void *result_list = lox_list_new();
    for (size_t index = 0; index < ready_count; index++) {
        lox_list_push(result_list, 1, ready[index]);
    }
    return result_list;
}
