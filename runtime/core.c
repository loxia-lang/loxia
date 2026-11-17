/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* Núcleo do runtime: inicialização, GC, pilha, panic e exceções (ADR-0074,
 * ADR-0077, ADR-0089). */
#include "lox_runtime.h"

/* Estado do processo (uma execução por binário). */
const char *lox_source_path = "<lox>";
int32_t lox_argc = 0;
char **lox_argv = NULL;

LoxFrame lox_frames[LOX_MAX_CALL_DEPTH];
int64_t lox_call_depth = 0;
LoxTryFrame *lox_current_try = NULL;

void lox_init(const char *source_path, int32_t argc, char **argv) {
    lox_source_path = source_path;
    lox_argc = argc;
    lox_argv = argv;
    setlocale(LC_NUMERIC, "C");
    /* `proc.write` em pipe fechado deve devolver EPIPE, não matar o processo. */
    signal(SIGPIPE, SIG_IGN);
    lox_reserve_stack();
    GC_set_all_interior_pointers(1);
    GC_INIT();
    GC_set_warn_proc(GC_ignore_warn_proc);
    GC_set_max_heap_size((GC_word)LOX_GC_MAX_HEAP_BYTES);
    GC_set_oom_fn(lox_oom);
}

/*
 * String imutável: bytes UTF-8 + contagem de code points (ADR-0031, decisão 6).
 * O IR usa `i8*` para o ponteiro; o layout é este struct.
 */
/*
 * Pilha de chamadas (ADR-0077): o contador é o contrato; a reserva de SO é
 * orçamento interno para frames gordos. Chamadas nativas não entram no contador.
 *
 * ADR-0089: o mesmo array carrega o stack trace. `file` é a função atual (cabeçalho
 * de panic); `call_*` é onde ela foi chamada (linha do frame). O call site chega
 * pelos globais abaixo, gravados pelo lowering imediatamente antes da chamada.
 */

const char *lox_call_file = NULL;
int32_t lox_call_line = 0;
int32_t lox_call_column = 0;

const char *lox_current_file(void) {
    if (lox_call_depth <= 0) {
        return lox_source_path;
    }
    return lox_frames[lox_call_depth - 1].file;
}

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

void lox_stack_leave(void) {
    if (lox_call_depth > 0) {
        lox_call_depth -= 1;
    }
}

/* Devolve o call site do frame atual (ctor → init após inicializadores). */
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

void lox_print_frames(int64_t depth) {
    if (depth <= 0) {
        return;
    }

    int64_t head = LOX_TRACE_HEAD;
    int64_t tail = LOX_TRACE_TAIL;
    int64_t show_head = depth < head ? depth : head;
    int64_t show_tail = 0;
    int64_t omitted = 0;
    if (depth > head + tail) {
        omitted = depth - head - tail;
        show_tail = tail;
    }

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

/* Sobe o soft limit da pilha da thread principal; virtual, commit sob demanda. */
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

/* Heap coletado (ADR-0074): o Boehm é o único alocador; sem free manual. */
void *lox_oom(size_t size) {
    (void)size;
    lox_panic(0, 0, "R1000", "Out of memory.");
    return NULL;
}

void *lox_alloc(size_t size) {
    void *pointer = GC_MALLOC(size > 0 ? size : 1u);
    if (pointer == NULL) {
        lox_panic(0, 0, "R1000", "Out of memory.");
    }
    return pointer;
}

/* Bloco sem ponteiros (bytes de string, buffers de formatação). */
void *lox_alloc_atomic(size_t size) {
    void *pointer = GC_MALLOC_ATOMIC(size > 0 ? size : 1u);
    if (pointer == NULL) {
        lox_panic(0, 0, "R1000", "Out of memory.");
    }
    return pointer;
}

/*
 * Closure do L4 (ADR-0046): `{ fnptr, env, display }`. O IR aloca via estes wrappers;
 * `display` é uma string C determinística (`<fn f>`/`<lambda>`), nunca um endereço.
 */

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


/* Exceções do L6j: frames de try, throw e cleanup mínimo (ADR-0062). */

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

void *lox_try_buffer(void *pointer) {
    return &((LoxTryFrame *)pointer)->env;
}

void lox_try_pop(void *pointer) {
    LoxTryFrame *frame = pointer;
    if (frame->active) {
        frame->active = 0;
        /* Desfaz o contador das funções abandonadas pelo longjmp (ADR-0077). */
        lox_call_depth = frame->depth;
    }
    if (lox_current_try == frame) {
        lox_current_try = frame->previous;
    }
}

void *lox_try_exception(void *pointer) {
    return &((LoxTryFrame *)pointer)->exception;
}

void *lox_exception_instance(const void *pointer) {
    return ((const LoxException *)pointer)->instance;
}

const char *lox_exception_message(const void *pointer) {
    return ((const LoxException *)pointer)->message;
}

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
                    memcmp(name->data, type_name, length) == 0) {
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
 * `code != NULL` marca um panic de runtime convertido em exceção para um `try`.
 * Se ele não for capturado, o topo imprime o código original (ex.: R1015), como o
 * tree-walk; sem `code`, é uma exceção de usuário (R1010 unhandled).
 *
 * `file`/`trace_depth` são os do ponto do throw: o longjmp desempilha os frames, mas
 * os do array continuam válidos para o trace (ADR-0089).
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

void lox_raise_current(int32_t line, int32_t column) {
    LoxTryFrame *frame = lox_current_try;
    if (frame == NULL) {
        lox_panic(line, column, "R1014", "No exception to re-raise.");
    }
    /* `raise;` reemite como exceção de usuário; o código do panic não sobrevive. */
    lox_throw_internal_at(lox_current_file(), NULL, frame->exception.instance,
                          frame->exception.type_name,
                          frame->exception.message, line, column,
                          lox_call_depth);
}

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

void lox_panic(int32_t line, int32_t column, const char *code,
               const char *message) {
    lox_panic_at(lox_current_file(), line, column, code, message);
}
