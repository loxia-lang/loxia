/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * core.c — process startup, allocator/GC, call stack, panics and exceptions for
 * the native backend.
 *
 * Who calls it: the generated `main` calls `lox_init`; the lowering emits
 * `lox_stack_enter`/`lox_stack_leave` in every function, `lox_alloc*` for heap
 * objects and `lox_panic`/`lox_throw*` at error sites. `lox_print_frames` is
 * used by panics and by the uncaught-exception path.
 *
 * Invariants:
 *  - the heap is Boehm-only (`GC_MALLOC`/`GC_MALLOC_ATOMIC`); never call `free`;
 *  - `lox_call_depth` never exceeds `LOX_MAX_CALL_DEPTH` (R1015);
 *  - try frames form a LIFO stack rooted at `lox_current_try`;
 *  - stdout is flushed before stderr/exit (observable order for I1);
 *  - no output may contain an address, PID or timestamp (I3).
 *
 * ADRs: 0074 (GC), 0077 (stack), 0087 (heap cap), 0089 (stack trace), 0062
 * (exceptions), 0075 (diagnostics).
 */
#include "lox_runtime.h"

/* Process state (one execution per binary). */
const char *lox_source_path = "<lox>";
int32_t lox_argc = 0;
char **lox_argv = NULL;

LoxFrame lox_frames[LOX_MAX_CALL_DEPTH];
int64_t lox_call_depth = 0;
LoxTryFrame *lox_current_try = NULL;

/* ---------------------------------------------------------------------------
 * Startup
 * --------------------------------------------------------------------------- */

/* Binary entry point: pins locale/SIGPIPE, reserves the stack and configures
 * Boehm (interior pointers, heap cap and OOM callback). */
void lox_init(const char *source_path, int32_t argc, char **argv) {
    lox_source_path = source_path;
    lox_argc = argc;
    lox_argv = argv;
    setlocale(LC_NUMERIC, "C");
    /* `proc.write` on a closed pipe must return EPIPE, not kill the process. */
    signal(SIGPIPE, SIG_IGN);
    lox_reserve_stack();
    GC_set_all_interior_pointers(1);
    GC_INIT();
    GC_set_warn_proc(GC_ignore_warn_proc);
    GC_set_max_heap_size((GC_word)LOX_GC_MAX_HEAP_BYTES);
    GC_set_oom_fn(lox_oom);
}

/* ---------------------------------------------------------------------------
 * Call stack and stack trace
 *
 * ADR-0077: the counter is the contract; the OS reserve is an internal budget for
 * fat frames. Native calls do not enter the counter.
 *
 * ADR-0089: `lox_frames` also carries the stack trace. `file` is the current
 * function (panic header); `call_*` is where it was called from (the frame's
 * line). The call site arrives through the globals below, written by the
 * lowering immediately before the call.
 * --------------------------------------------------------------------------- */

/* Call site of the next call, restored by `lox_call_site_restore`. */
const char *lox_call_file = NULL;
int32_t lox_call_line = 0;
int32_t lox_call_column = 0;

/* Source file of the current frame; without frames, the main script. */
const char *lox_current_file(void) {
    if (lox_call_depth <= 0) {
        return lox_source_path;
    }
    return lox_frames[lox_call_depth - 1].file;
}

/* Enters a user function. Raises R1015 before recording the frame; `decl_*` is
 * the declaration position used by the overflow diagnostic. */
void lox_stack_enter(const char *name, const char *file, int32_t decl_line,
                     int32_t decl_column) {
    if (lox_call_depth >= LOX_MAX_CALL_DEPTH) {
        lox_panic_at(file != NULL ? file : lox_source_path, decl_line,
                     decl_column, "R1015", "Stack overflow.");
        return;
    }
    LoxFrame *frame = &lox_frames[lox_call_depth];
    frame->name = name != NULL ? name : "<fn>";
    frame->file = file != NULL ? file : lox_source_path;
    frame->call_file = lox_call_file != NULL ? lox_call_file : frame->file;
    frame->call_line = lox_call_line;
    frame->call_column = lox_call_column;
    lox_call_depth += 1;
}

/* Leaves the current function; never goes below 0. */
void lox_stack_leave(void) {
    if (lox_call_depth > 0) {
        lox_call_depth -= 1;
    }
}

/* Restores the current frame call site (ctor → init after initializers). */
void lox_call_site_restore(void) {
    if (lox_call_depth <= 0) {
        return;
    }
    const LoxFrame *frame = &lox_frames[lox_call_depth - 1];
    lox_call_file = frame->call_file;
    lox_call_line = frame->call_line;
    lox_call_column = frame->call_column;
}

void lox_print_frame(const LoxFrame *frame) {
    fprintf(stderr, "  at %s (%s:%" PRId32 ":%" PRId32 ")\n", frame->name,
            frame->call_file, frame->call_line, frame->call_column);
}

/* Prints up to LOX_TRACE_HEAD frames from the top and LOX_TRACE_TAIL from the
 * bottom, eliding the middle. `depth` is the value frozen at throw time (the
 * longjmp unwinds the counter, but the frames remain in the array). */
void lox_print_frames(int64_t depth) {
    if (depth <= 0) {
        return;
    }

    int64_t head = LOX_TRACE_HEAD;
    int64_t tail = LOX_TRACE_TAIL;
    int64_t show_head = depth < head ? depth : head;
    int64_t show_tail = depth <= head + tail ? depth - show_head : tail;
    int64_t omitted = depth > head + tail ? depth - head - tail : 0;

    for (int64_t index = 0; index < show_head; index++) {
        lox_print_frame(&lox_frames[depth - 1 - index]);
    }
    if (omitted > 0) {
        fprintf(stderr, "  ... %" PRId64 " frames omitted\n", omitted);
    }
    for (int64_t index = show_tail; index > 0; index--) {
        lox_print_frame(&lox_frames[index - 1]);
    }
}

/* ---------------------------------------------------------------------------
 * OS stack reserve
 * --------------------------------------------------------------------------- */

/* Raises the main thread stack soft limit; virtual memory, committed on demand. */
void lox_reserve_stack(void) {
    struct rlimit limit;
    if (getrlimit(RLIMIT_STACK, &limit) != 0) {
        return;
    }
    rlim_t desired = (rlim_t)LOX_STACK_RESERVE_BYTES;
    if (limit.rlim_cur >= desired) {
        return;
    }
    if (limit.rlim_max != RLIM_INFINITY && desired > limit.rlim_max) {
        desired = limit.rlim_max;
    }
    limit.rlim_cur = desired;
    (void)setrlimit(RLIMIT_STACK, &limit);
}

/* ---------------------------------------------------------------------------
 * Collected allocator (Boehm GC, ADR-0074)
 *
 * Boehm is the only allocator; there is no `free`. Use `lox_alloc` for blocks
 * with pointers and `lox_alloc_atomic` for pure bytes (string data, buffers).
 * --------------------------------------------------------------------------- */

/* Boehm OOM callback: fixed message and exit 70. */

void lox_oom_exit(void) {
    fflush(stdout);
    fputs("error[R1000]: Out of memory.\n", stderr);
    fflush(stderr);
    exit(70);
}

void *lox_oom(size_t size) {
    (void)size;
    lox_oom_exit();
    return NULL;
}

void *lox_alloc(size_t size) {
    void *pointer = GC_MALLOC(size > 0 ? size : 1u);
    if (pointer == NULL) {
        lox_oom_exit();
    }
    return pointer;
}

/* Pointer-free block (string bytes, formatting buffers). */
void *lox_alloc_atomic(size_t size) {
    void *pointer = GC_MALLOC_ATOMIC(size > 0 ? size : 1u);
    if (pointer == NULL) {
        lox_oom_exit();
    }
    return pointer;
}

/* ---------------------------------------------------------------------------
 * Lowering allocation wrappers (L4 closures/cells, ADR-0046)
 *
 * A closure is `{fnptr, env, display}`; `display` is a deterministic C string
 * (`<fn f>`/`<lambda>`), never an address. A capture cell is a 16-byte block
 * holding `{i64, tag}` or `{double, tag}`.
 * --------------------------------------------------------------------------- */

/* Captured-variable cell: 2 words (scalar + tag). */
void *lox_alloc_cell(void) {
    /* Fits the largest scalar value: `{i1, i64}`/`{i1, double}` (16 bytes). */
    return lox_alloc(2 * sizeof(int64_t));
}

/* Closure environment: array of `count` pointers (cells or values). */
void *lox_alloc_env(int64_t count) {
    size_t entries = count > 0 ? (size_t)count : 1u;
    return lox_alloc(entries * sizeof(void *));
}

/* L4 closure: `{fnptr, env, display}`. */
void *lox_alloc_closure(void) {
    return lox_alloc(sizeof(LoxClosure));
}

/* Untagged byte buffer (internal to the lowering/kernel). */
void *lox_alloc_bytes(int64_t size) {
    return lox_alloc(size > 0 ? (size_t)size : 1u);
}


/* ---------------------------------------------------------------------------
 * Exceptions: try, throw and cleanup (ADR-0062)
 *
 * The lowering pushes a LoxTryFrame before the `try` body, calls `setjmp` on the
 * buffer returned by `lox_try_buffer` and pops in `lox_try_pop`. A `throw` does a
 * longjmp to the current frame; abandoned frames are restored by the `depth`
 * recorded on entry.
 * --------------------------------------------------------------------------- */

/* Pushes a try frame and returns its address (the setjmp buffer base). */
void *lox_try_push(void) {
    LoxTryFrame *frame = lox_alloc(sizeof(LoxTryFrame));
    frame->previous = lox_current_try;
    frame->active = 1;
    frame->depth = lox_call_depth;
    frame->exception.type_name = NULL;
    frame->exception.instance = NULL;
    frame->exception.message = NULL;
    frame->exception.code = NULL;
    frame->exception.file = NULL;
    frame->exception.line = 0;
    frame->exception.column = 0;
    frame->exception.trace_depth = 0;
    lox_current_try = frame;
    return frame;
}

/* The frame setjmp/longjmp buffer. */
void *lox_try_buffer(void *pointer) {
    return &((LoxTryFrame *)pointer)->env;
}

/* Deactivates the frame and restores `lox_call_depth` to its value on try
 * entry (the longjmp abandoned frames of functions that were in flight). */
void lox_try_pop(void *pointer) {
    LoxTryFrame *frame = pointer;
    if (frame->active) {
        frame->active = 0;
        /* Undoes the counter for functions abandoned by the longjmp (ADR-0077). */
        lox_call_depth = frame->depth;
    }
    if (lox_current_try == frame) {
        lox_current_try = frame->previous;
    }
}

/* Exception captured by the frame (valid after the longjmp). */
void *lox_try_exception(void *pointer) {
    return &((LoxTryFrame *)pointer)->exception;
}

/* User exception instance, or NULL for runtime panics. */
void *lox_exception_instance(const void *pointer) {
    return ((const LoxException *)pointer)->instance;
}

/* Already-materialized message (panics) or the instance `message` field. */
const char *lox_exception_message(const void *pointer) {
    return ((const LoxException *)pointer)->message;
}

/* Matches the exception against a descriptor (`expected`) or a type name.
 * Instances walk the `super` chain; `Exception` is the root. Panics have no
 * instance and match by name only (`RuntimeError`). */
int32_t lox_exception_matches(const void *pointer, const void *expected,
                              const char *type_name) {
    const LoxException *exception = pointer;
    if (exception->instance != NULL) {
        void *descriptor = *(void **)exception->instance;
        while (descriptor != NULL) {
            if (expected != NULL) {
                if (descriptor == expected) {
                    return 1;
                }
            } else if (type_name != NULL) {
                const LoxStr *name = ((const LoxStr **)descriptor)[2];
                size_t length = strlen(type_name);
                if (name->byte_len == (int64_t)length &&
                    memcmp(lox_str_bytes(name), type_name, length) == 0) {
                    return 1;
                }
            }
            descriptor = *(void **)descriptor;
        }
        return 0;
    }
    if (exception->type_name == NULL || type_name == NULL) {
        return 0;
    }
    if (strcmp(exception->type_name, type_name) == 0) {
        return 1;
    }
    return strcmp(type_name, "Exception") == 0;
}

/* ADR-0120: `file:line:column` for caught exceptions. No address, PID or
 * absolute path is introduced here; `file` comes from the lowering (relative). */
static void *site_string(const char *file, int32_t line, int32_t column) {
    if (file == NULL || line <= 0) {
        return lox_str_from_cstr("");
    }
    char buffer[4096];
    snprintf(buffer, sizeof(buffer), "%s:%" PRId32 ":%" PRId32, file, line,
             column > 0 ? column : 1);
    return lox_str_from_cstr(buffer);
}

/* Call site of the current activation (the line that called `f`, not the
 * `raise` inside it). For a top-level constructor, the pending call site. */
void *lox_exception_site(int32_t line, int32_t column) {
    if (lox_call_depth > 0) {
        const LoxFrame *frame = &lox_frames[lox_call_depth - 1];
        return site_string(frame->call_file, frame->call_line, frame->call_column);
    }
    if (line > 0) {
        return site_string(lox_source_path, line, column);
    }
    if (lox_call_file != NULL && lox_call_line > 0) {
        return site_string(lox_call_file, lox_call_line, lox_call_column);
    }
    return site_string(NULL, 0, 0);
}

/* Position recorded on a panic (`LoxException`), used when it is materialized
 * as a `RuntimeError` for `except`. */
void *lox_exception_site_at(const void *pointer) {
    const LoxException *exception = pointer;
    return site_string(exception->file, exception->line, exception->column);
}

/* ---------------------------------------------------------------------------
 * Runtime diagnostics and panic
 * --------------------------------------------------------------------------- */

/* `file:line:col: error[CODE]:` header; without a position, omits the prefix. */
void lox_print_prefix_at(const char *file, int32_t line, int32_t column,
                                const char *code) {
    const char *origin = file != NULL ? file : lox_source_path;
    if (line > 0 && column > 0) {
        fprintf(stderr, "%s:%" PRId32 ":%" PRId32 ": error[%s]: ", origin, line,
                column, code);
    } else if (line > 0) {
        fprintf(stderr, "%s:%" PRId32 ": error[%s]: ", origin, line, code);
    } else {
        fprintf(stderr, "error[%s]: ", code);
    }
}

/*
 * `code != NULL` marks a runtime panic converted into an exception for a `try`.
 * If it is not caught, top level prints the original code (e.g. R1015), like the
 * tree-walk; without `code`, it is a user exception (R1010 unhandled).
 *
 * `file`/`trace_depth` are from the throw point: the longjmp unwinds frames, but
 * the ones in the array remain valid for the trace (ADR-0089).
 */
void lox_throw_internal_at(const char *file, const char *code,
                                  void *instance, const char *type_name,
                                  const char *message, int32_t line,
                                  int32_t column, int64_t trace_depth) {
    LoxTryFrame *frame = lox_current_try;
    if (frame == NULL) {
        fflush(stdout);
        if (code != NULL) {
            lox_print_prefix_at(file, line, column, code);
            fprintf(stderr, "%s\n", message);
        } else {
            lox_print_prefix_at(file, line, column, "R1010");
            if (message != NULL) {
                fprintf(stderr, "Unhandled exception: %s: %s\n", type_name,
                        message);
            } else {
                fprintf(stderr, "Unhandled exception: %s\n", type_name);
            }
        }
        lox_print_frames(trace_depth);
        fflush(stderr);
        exit(70);
    }
    frame->exception.type_name = type_name;
    frame->exception.instance = instance;
    frame->exception.message = message;
    frame->exception.code = code;
    frame->exception.file = file;
    frame->exception.line = line;
    frame->exception.column = column;
    frame->exception.trace_depth = trace_depth;
    longjmp(frame->env, 1);
}

void lox_throw_internal(const char *code, void *instance,
                               const char *type_name, const char *message,
                               int32_t line, int32_t column) {
    lox_throw_internal_at(lox_current_file(), code, instance, type_name, message,
                          line, column, lox_call_depth);
}

void lox_throw(void *instance, const char *type_name, const char *message,
               int32_t line, int32_t column) {
    lox_throw_internal(NULL, instance, type_name, message, line, column);
}

void lox_rethrow(void *exception_pointer, int32_t line, int32_t column) {
    LoxException *exception = exception_pointer;
    const char *file = lox_current_file();
    int64_t trace_depth = lox_call_depth;
    if (exception->code != NULL) {
        line = exception->line;
        column = exception->column;
        file = exception->file;
        trace_depth = exception->trace_depth;
    }
    lox_throw_internal_at(file, exception->code, exception->instance,
                          exception->type_name, exception->message, line,
                          column, trace_depth);
}

/* `raise;` dentro de `except`: reemite a exceção como valor de usuário
 * (R1010), não como o panic original (R1002/R1014 etc.). */
void lox_raise_value(void *pointer, int32_t line, int32_t column) {
    LoxException *exception = pointer;
    lox_throw_internal_at(lox_current_file(), NULL, exception->instance,
                          exception->type_name, exception->message, line,
                          column, lox_call_depth);
}

void lox_raise_current(int32_t line, int32_t column) {
    LoxTryFrame *frame = lox_current_try;
    if (frame == NULL) {
        lox_panic(line, column, "R1014", "No exception to re-raise.");
    }
    /* `raise;` re-emits as a user exception; the panic code does not survive. */
    lox_throw_internal_at(lox_current_file(), NULL, frame->exception.instance,
                          frame->exception.type_name,
                          frame->exception.message, line, column,
                          lox_call_depth);
}

/* Runtime panic: with an active try it becomes a catchable `RuntimeError`;
 * otherwise it prints the header + trace and exits 70. Never returns. */
void lox_panic_at(const char *file, int32_t line, int32_t column,
                         const char *code, const char *message) {
    if (lox_current_try != NULL) {
        lox_throw_internal_at(file, code, NULL, "RuntimeError", message, line,
                              column, lox_call_depth);
    }
    fflush(stdout);
    lox_print_prefix_at(file, line, column, code);
    fprintf(stderr, "%s\n", message);
    lox_print_frames(lox_call_depth);
    fflush(stderr);
    exit(70);
}

/* `lox_panic_at` shortcut using the current frame file. */
void lox_panic(int32_t line, int32_t column, const char *code,
               const char *message) {
    lox_panic_at(lox_current_file(), line, column, code, message);
}
