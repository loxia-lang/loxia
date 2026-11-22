/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * lox_regex.h — stable C ABI of the Loxia regex engine (ADR-0131).
 *
 * Implemented in Rust (`native/regex/src/lib.rs`). The C runtime and the
 * Python binding (ctypes) are the only consumers; the public Loxia API lives
 * in `bundled/regex.lx`.
 *
 * All offsets crossing this ABI are UTF-8 byte offsets, except `start` and the
 * spans written by `loxr_match`, which are code-point offsets (Loxia strings
 * count code points, ADR-0035).
 */
#ifndef LOX_REGEX_ABI_H
#define LOX_REGEX_ABI_H

#include <stddef.h>
#include <stdint.h>

#define LOXR_ABI_VERSION 1u

/* Modes (ADR-0131): linear is the safe default. */
#define LOXR_MODE_LINEAR 0u
#define LOXR_MODE_FULL 1u

/* Compile flags. */
#define LOXR_FLAG_CASELESS 1u
#define LOXR_FLAG_MULTILINE 2u
#define LOXR_FLAG_DOTALL 4u
#define LOXR_FLAG_EXTENDED 8u

/* Return codes. */
#define LOXR_OK 0
#define LOXR_NO_MATCH (-100)
#define LOXR_ERR_PANIC (-1)
#define LOXR_ERR_ARGS (-2)
#define LOXR_ERR_MODE (-3)
#define LOXR_ERR_LIMIT (-4)
#define LOXR_ERR_HANDLE (-5)
#define LOXR_ERR_UTF8 (-6)
#define LOXR_ERR_HANDLES (-7)
#define LOXR_ERR_COMPILE (-10)

/* ABI version; the loader refuses a mismatch. */
uint32_t loxr_abi_version(void);

/*
 * Compiles `pattern` (UTF-8, `len` bytes). On success writes a 1-based handle
 * to `out_handle` and returns LOXR_OK. On a syntax error returns
 * LOXR_ERR_COMPILE and writes the byte offset (or -1 when unknown) to
 * `out_offset`.
 */
int32_t loxr_compile(const uint8_t *pattern, size_t len, uint32_t flags,
                     uint32_t mode, int64_t *out_handle, int64_t *out_offset);

/*
 * Matches `handle` against `subject` (UTF-8, `len` bytes) starting at the
 * code-point offset `start`. Writes pairs (start, end) in code points, one per
 * group (-1, -1 for a group that did not participate), and returns the number
 * of int64 values written. Returns LOXR_NO_MATCH when the pattern does not
 * match at or after `start`, or a negative error code.
 */
int32_t loxr_match(int64_t handle, const uint8_t *subject, size_t len,
                   size_t start, int64_t *out_spans, size_t capacity);

/* Releases a handle. Idempotent; safe on an unknown handle. */
void loxr_free(int64_t handle);

#endif /* LOX_REGEX_ABI_H */
