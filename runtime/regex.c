/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * regex.c — adaptadores Lox das primitivas `regex_engine.*` (ADR-0131).
 *
 * O motor é Rust (`native/regex/`, ABI em `include/lox_regex.h`). Este arquivo só
 * converte `LoxStr` → bytes, bytes → spans e código de erro → panic, exatamente
 * como `loxia_core/execution/primitives.py` faz no interpretador; as mensagens
 * precisam ser idênticas nos dois motores (I1).
 *
 * Invariantes:
 *  - `compile` devolve `[1, handle]` ou `[0, code, offset]`; erro de sintaxe não é panic;
 *  - `find` devolve `nil` (sem match) ou a lista de spans em code points;
 *  - `free` é idempotente; handle < 1 é panic, como no interpretador;
 *  - esta unidade só entra no link quando o programa usa `regex_engine.*`.
 *
 * ADRs: 0131 (motor Rust), 0126 (camada nativa), 0071 (primitivas).
 */
#include "lox_runtime.h"
#include "kernel_gen.h"

#include "../native/regex/include/lox_regex.h"

#define LOX_REGEX_LOCAL_SPANS 64
#define LOX_REGEX_GROW_CAPACITY 8192

static const char *regex_error_message(int32_t code) {
    switch (code) {
        case LOXR_ERR_LIMIT:
            return "regex match limit exceeded.";
        case LOXR_ERR_HANDLE:
            return "regex handle is closed or unknown.";
        default:
            return "regex engine internal error.";
    }
}

void *lox_regex_engine_compile(const void *pattern_pointer, int64_t flags, int64_t mode,
                               int32_t line, int32_t column) {
    const LoxStr *pattern = pattern_pointer;
    if (flags < 0) {
        lox_panic(line, column, "R1000",
                  "regex_engine.compile() expects a non-negative flags mask.");
        return NULL;
    }
    if (mode != LOXR_MODE_LINEAR && mode != LOXR_MODE_FULL) {
        lox_panic(line, column, "R1000",
                  "regex_engine.compile() expects mode 0 (linear) or 1 (full).");
        return NULL;
    }

    int64_t handle = 0;
    int64_t offset = -1;
    int32_t code = loxr_compile((const uint8_t *)pattern->data, (size_t)pattern->byte_len,
                                (uint32_t)flags, (uint32_t)mode, &handle, &offset);

    LoxList *result = lox_list_new();
    if (code == LOXR_OK) {
        /* [1, handle]: o tag do protocolo e o handle, dois elementos. */
        lox_list_push(result, 1, 1);
        lox_list_push(result, 1, handle);
    } else {
        lox_list_push(result, 1, 0);
        lox_list_push(result, 1, code);
        lox_list_push(result, 1, offset);
    }
    return result;
}

void *lox_regex_engine_find(int64_t handle, const void *subject_pointer, int64_t start,
                            int32_t line, int32_t column) {
    const LoxStr *subject = subject_pointer;
    if (start < 0) {
        lox_panic(line, column, "R1000",
                  "regex_engine.find() expects a non-negative start.");
        return NULL;
    }

    int64_t local[LOX_REGEX_LOCAL_SPANS];
    int32_t code = loxr_match(handle, (const uint8_t *)subject->data, (size_t)subject->byte_len,
                              (size_t)start, local, LOX_REGEX_LOCAL_SPANS);
    int64_t *spans = local;
    if (code == LOXR_ERR_CAPACITY) {
        int64_t *grown = lox_alloc_atomic(sizeof(int64_t) * LOX_REGEX_GROW_CAPACITY);
        code = loxr_match(handle, (const uint8_t *)subject->data, (size_t)subject->byte_len,
                          (size_t)start, grown, LOX_REGEX_GROW_CAPACITY);
        spans = grown;
    }
    if (code == LOXR_NO_MATCH) {
        return NULL;
    }
    if (code == LOXR_ERR_CAPACITY) {
        lox_panic(line, column, "R1000", "regex: pattern has too many capture groups.");
        return NULL;
    }
    if (code < 0) {
        lox_panic(line, column, "R1000", regex_error_message(code));
        return NULL;
    }

    LoxList *result = lox_list_new();
    for (int32_t index = 0; index < code; index++) {
        lox_list_push(result, 1, spans[index]);
    }
    return result;
}

void *lox_regex_engine_group_names(int64_t handle, int32_t line, int32_t column) {
    if (handle < 1) {
        lox_panic(line, column, "R1000",
                  "regex_engine.groupNames() expects a handle from compile.");
        return NULL;
    }
    int32_t needed = loxr_group_names(handle, NULL, 0);
    if (needed < 0) {
        lox_panic(line, column, "R1000", regex_error_message(needed));
        return NULL;
    }
    LoxList *result = lox_list_new();
    if (needed == 0) {
        return result;
    }
    uint8_t *buffer = lox_alloc_atomic((size_t)needed);
    if (loxr_group_names(handle, buffer, (size_t)needed) != needed) {
        lox_panic(line, column, "R1000", "regex engine internal error.");
        return NULL;
    }
    int32_t start = 0;
    for (int32_t index = 0; index < needed; index++) {
        if (buffer[index] != 0) {
            continue;
        }
        void *name = lox_str_from_cstr((const char *)buffer + start);
        lox_list_push(result, 4, (int64_t)name);
        start = index + 1;
    }
    return result;
}

void lox_regex_engine_free(int64_t handle, int32_t line, int32_t column) {
    if (handle < 1) {
        lox_panic(line, column, "R1000",
                  "regex_engine.free() expects a handle from compile.");
        return;
    }
    loxr_free(handle);
}
