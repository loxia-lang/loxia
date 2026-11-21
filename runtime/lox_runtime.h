/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * Native backend runtime: shared types, limits and internal contract.
 *
 * The runtime is compiled as several units (core, objects, strings, containers,
 * numeric, kernel, proc); this header is the single place for shared types and
 * prototypes.
 *
 * Unit map (details in runtime/README.md):
 *   core.c        lox_init, lox_stack_*, lox_panic*, lox_throw*, lox_alloc*
 *   objects.c     lox_interface_method, lox_is_instance, lox_type_*
 *   strings.c     lox_str_*, lox_print_*, format_*, buffer_*
 *   containers.c  lox_range_*, lox_list_*, lox_map_*, lox_tuple_*, lox_enum_*
 *   numeric.c     lox_math_*, lox_parse_*, lox_int_*, lox_float_*, lox_shift
 *   kernel.c      lox_substr/join/charCodeAt/fromCodePoint, lox_io_*, lox_fs_*,
 *                 lox_os_*, lox_time_*, lox_args
 *   proc.c        lox_proc_*
 *
 * Generated code and the C runtime agree on the layouts below; the lowering
 * mirrors them in loxia_core/backend/lower_model.py.
 */
#ifndef LOX_RUNTIME_H
#define LOX_RUNTIME_H

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <gc.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <dirent.h>
#include <inttypes.h>
#include <locale.h>
#include <math.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <time.h>

/* Collected-heap hard cap (ADR-0087); the driver passes the build value. */
#ifndef LOX_GC_MAX_HEAP_BYTES
#define LOX_GC_MAX_HEAP_BYTES (512ull * 1024ull * 1024ull)
#endif

/* Stack contract (ADR-0077); the driver passes the build value. */
#ifndef LOX_MAX_CALL_DEPTH
#define LOX_MAX_CALL_DEPTH 10000
#endif
#ifndef LOX_STACK_RESERVE_BYTES
#define LOX_STACK_RESERVE_BYTES (128ull * 1024ull * 1024ull)
#endif

/* Stack trace (ADR-0089): same numbers as execution/limits.py, via the driver. */
#ifndef LOX_TRACE_HEAD
#define LOX_TRACE_HEAD 5
#endif
#ifndef LOX_TRACE_TAIL
#define LOX_TRACE_TAIL 5
#endif

/*
 * Immutable String: UTF-8 bytes + code-point count (ADR-0031, decision 6).
 * The IR uses `i8*` for the pointer; this struct is the layout.
 */
typedef struct {
    int64_t byte_len;
    int64_t cp_len;
    const char *data;
    int32_t *cp_offsets; /* lazy cache; NULL until the first random access */
} LoxStr;

/*
 * Call stack (ADR-0077): the counter is the contract; the OS reserve is an
 * internal budget for fat frames. Native calls do not enter the counter.
 *
 * ADR-0089: the same array carries the stack trace. `file` is the current
 * function (panic header); `call_*` is where it was called from (the frame's
 * line). The call site arrives through the globals below, written by the
 * lowering immediately before the call.
 */
typedef struct {
    const char *name;
    const char *file;
    const char *call_file;
    int32_t call_line;
    int32_t call_column;
} LoxFrame;

/*
 * L4 closure (ADR-0046): `{ fnptr, env, display }`. The IR allocates through the
 * wrappers; `display` is a deterministic C string (`<fn f>`/`<lambda>`), never an
 * address.
 */
typedef struct {
    void *fn;
    void *env;
    const char *display;
} LoxClosure;

/* Mirrored layout of `_CLASS_DESC`/`_INTERFACE_ENTRY` (ADR-0080, phase B2). */
typedef struct {
    void *super;
    int64_t id;
    void *name;
    void *vtable;
    int64_t field_count;
    void *init;
    int64_t init_min;
    int64_t init_max;
    int64_t interface_count;
    void *interfaces;
} LoxClassDescRuntime;

typedef struct {
    int64_t interface_id;
    void *itab;
} LoxInterfaceEntryRuntime;

/* L6 Range: immutable value, pointer to `{start, end, step}`. */
typedef struct {
    int64_t start;
    int64_t end;
    int64_t step;
    int32_t inclusive;
} LoxRange;

/* L6 List: boxed `LoxValue{tag,payload}` elements, insertion order. */
/*
 * Boxed value used by the dynamic path and containers. Tag table (keep in sync
 * with strings.c, objects.c and containers.c):
 *   0 nil, 1 Int, 2 Float, 3 Bool, 4 String, 5 Class, 6 Instance,
 *   7 Function, 8 Range, 9 List, 10 Map, 11 Tuple, 12 Enum.
 * Float stores its bit pattern in `payload`; tags 0..3 carry immediates, tag 4
 * carries a LoxStr pointer, and tags 5..12 carry object/container pointers.
 */
typedef struct {
    int64_t tag;
    int64_t payload;
} LoxValue;

typedef struct {
    int64_t count;
    int64_t capacity;
    LoxValue *items;
    int64_t version;
} LoxList;

/* L6 Map: boxed entries in insertion order. */
typedef struct {
    LoxValue key;
    LoxValue value;
} LoxMapEntry;

typedef struct {
    int64_t count;
    int64_t capacity;
    LoxMapEntry *entries;
    int64_t version;
} LoxMap;

/* L6 Tuple: boxed elements, fixed arity, immutable. */
typedef struct {
    int64_t count;
    LoxValue *items;
} LoxTuple;

/* L6 Enum: identity + variant + boxed payload. */
typedef struct {
    int64_t enum_id;
    const char *enum_name;
    const char *variant_name;
    int64_t count;
    LoxValue *payload;
} LoxEnumValue;

/* Runtime type check for `is`/`as` (ADR-0025, ADR-0029).
 *
 * The lowering serializes the target type into a compact string and the matcher
 * walks lists, maps and tuples with the same runtime accessors. The tree is
 * cached by string pointer (the global owned by each `is`/`as` site).
 *
 * Grammar: A=Any, X=never, N=nil, B=Bool, I=Int, F=Float, S=String,
 * R=Range, L<T>=List, M<K,V>=Map, T<T1,...>=Tuple, U<T1|...>=Union,
 * E<id>=enum, C<id>=class.
 */
typedef struct LoxTypeDesc {
    int64_t kind;
    struct LoxTypeDesc *a;
    struct LoxTypeDesc *b;
    int64_t count;
    struct LoxTypeDesc *items;
} LoxTypeDesc;

typedef struct LoxTypeCache {
    const char *text;
    LoxTypeDesc *desc;
    struct LoxTypeCache *next;
} LoxTypeCache;

/* L6 exceptions: try frames, throw and minimal cleanup (ADR-0062). */
typedef struct {
    const char *type_name;
    void *instance;
    const char *message;
    const char *code; /* R1xxx when the throw came from a panic; NULL for user exceptions */
    const char *file; /* throw origin (ADR-0089; module in the header) */
    int32_t line;
    int32_t column;
    int64_t trace_depth; /* live frames at throw time: unwinding does not erase them */
} LoxException;

typedef struct LoxTryFrame {
    jmp_buf env;
    struct LoxTryFrame *previous;
    LoxException exception;
    int32_t active;
    int64_t depth;
} LoxTryFrame;

typedef struct {
    char *data;
    size_t length;
    size_t capacity;
    const void *active[64];
    int active_depth;
} LoxBuffer;

/* ---------------------------------------------------------------------------
 * Process state (defined in core.c and objects.c)
 * --------------------------------------------------------------------------- */

extern const char *lox_source_path;
extern int32_t lox_argc;
extern char **lox_argv;
extern LoxFrame lox_frames[];
extern int64_t lox_call_depth;
extern const char *lox_call_file;
extern int32_t lox_call_line;
extern int32_t lox_call_column;
extern LoxTypeCache *lox_type_cache;
extern LoxTryFrame *lox_current_try;

/* ---------------------------------------------------------------------------
 * ABI surface: initialization, stack, allocation and panic
 *
 * Everything below is called by generated code or shared between runtime units.
 * --------------------------------------------------------------------------- */

extern void lox_init (const char *source_path, int32_t argc, char **argv);
extern const char *lox_current_file (void);
extern void lox_stack_enter (const char *name, const char *file, int32_t decl_line, int32_t decl_column);
extern void lox_stack_leave (void);
extern void lox_call_site_restore (void);
extern void lox_print_frame (const LoxFrame *frame);
extern void lox_print_frames (int64_t depth);
extern void lox_reserve_stack (void);
extern void *lox_oom (size_t size);
extern void *lox_alloc (size_t size);
extern void *lox_alloc_atomic (size_t size);
extern void *lox_alloc_cell (void);
extern void *lox_alloc_env (int64_t count);
extern void *lox_alloc_closure (void);
extern void *lox_alloc_bytes (int64_t size);
extern void *lox_interface_method (const void *instance, int64_t interface_id, int64_t method_index);
extern int lox_is_instance (void *descriptor, void *target);
extern void lox_print_function (const void *pointer);
/* ---------------------------------------------------------------------------
 * Strings, printing and value formatting
 * --------------------------------------------------------------------------- */

extern void *lox_str_from_function (const void *pointer);
extern void lox_print_str (const void *pointer);
extern int64_t lox_str_len (const void *pointer);
extern int32_t lox_str_compare (const void *left_pointer, const void *right_pointer);
extern int32_t lox_str_equal (const void *left_pointer, const void *right_pointer);
extern void *lox_str_concat (const void *left_pointer, const void *right_pointer);
/* ---------------------------------------------------------------------------
 * Containers: Range, List, Map, Tuple, Enum
 * --------------------------------------------------------------------------- */

extern void *lox_range_new (int64_t start, int64_t end, int64_t step,
                            int32_t inclusive, int32_t line, int32_t column);
extern int64_t lox_range_start (const void *pointer);
extern int64_t lox_range_end (const void *pointer);
extern int64_t lox_range_step (const void *pointer);
extern int32_t lox_range_inclusive (const void *pointer);
extern int32_t lox_range_equal (const void *left_pointer, const void *right_pointer);
extern void lox_print_range (const void *pointer);
extern void *lox_str_from_range (const void *pointer);
extern void *lox_list_new (void);
extern void lox_list_grow (LoxList *list);
extern void lox_list_push (void *pointer, int64_t tag, int64_t payload);
extern int64_t lox_list_len (const void *pointer);
extern int64_t lox_list_version (const void *pointer);
extern LoxValue lox_list_get (const void *pointer, int64_t index, int32_t line, int32_t column);
extern void lox_list_set (void *pointer, int64_t index, int64_t tag, int64_t payload, int32_t line, int32_t column);
extern LoxValue lox_list_pop (void *pointer, int32_t line, int32_t column);
extern int lox_list_equal (const void *left_pointer, const void *right_pointer);
extern int lox_value_equal (LoxValue left, LoxValue right);
extern void *lox_map_new (void);
extern int lox_map_key_equal (LoxValue left, LoxValue right);
extern int64_t lox_map_find (const LoxMap *map, LoxValue key);
extern void lox_map_grow (LoxMap *map);
extern void lox_map_check_key (int64_t tag, int32_t line, int32_t column);
extern void lox_map_set (void *pointer, int64_t key_tag, int64_t key_payload, int64_t value_tag, int64_t value_payload, int32_t line, int32_t column);
extern void lox_map_set_literal (void *pointer, int64_t key_tag, int64_t key_payload, int64_t value_tag, int64_t value_payload, int32_t line, int32_t column);
extern int64_t lox_map_len (const void *pointer);
extern int64_t lox_map_version (const void *pointer);
extern int32_t lox_map_has (const void *pointer, int64_t key_tag, int64_t key_payload, int32_t line, int32_t column);
extern LoxValue lox_map_get (const void *pointer, int64_t key_tag, int64_t key_payload, int32_t line, int32_t column);
extern LoxValue lox_map_get_checked (const void *pointer, int64_t key_tag, int64_t key_payload, int32_t line, int32_t column);
extern LoxValue lox_map_remove (void *pointer, int64_t key_tag, int64_t key_payload, int32_t line, int32_t column);
extern LoxValue lox_map_key_at (const void *pointer, int64_t index);
extern void *lox_map_keys (const void *pointer);
extern void *lox_map_values (const void *pointer);
extern int lox_map_equal (const void *left_pointer, const void *right_pointer);
extern void *lox_tuple_new (int64_t count);
extern void lox_tuple_set (void *pointer, int64_t index, int64_t tag, int64_t payload);
extern LoxValue lox_tuple_get (const void *pointer, int64_t index, int32_t line, int32_t column);
extern int64_t lox_tuple_len (const void *pointer);
extern int lox_tuple_equal (const void *left_pointer, const void *right_pointer);
/* digest.c — FIPS 180-4 SHA-256; the kernel wrapper renders lowercase hex. */
extern void lox_sha256 (const unsigned char *data, size_t length, unsigned char out[32]);
extern void *lox_chars (const void *pointer);
extern int lox_any_equal (int64_t left_tag, int64_t left_payload, int64_t right_tag, int64_t right_payload);
extern int lox_tuple_is2 (const void *pointer, int64_t tag0, int64_t tag1);
extern int64_t lox_math_abs_int (int64_t value);
extern double lox_math_abs_float (double value);
extern double lox_math_sqrt (double value);
extern int64_t lox_math_floor (double value, int32_t line, int32_t column);
extern int64_t lox_math_ceil (double value, int32_t line, int32_t column);
extern int64_t lox_math_round (double value, int32_t line, int32_t column);
extern int64_t lox_math_trunc (double value, int32_t line, int32_t column);
extern LoxValue lox_parse_int (const void *pointer);
extern LoxValue lox_parse_float (const void *pointer);
extern void *lox_enum_new (int64_t enum_id, const char *enum_name, const char *variant_name, int64_t count);
extern void lox_enum_set (void *pointer, int64_t index, int64_t tag, int64_t payload);
extern LoxValue lox_enum_payload (const void *pointer, int64_t index, int32_t line, int32_t column);
extern int64_t lox_enum_variant (const void *pointer);
extern int64_t lox_enum_variant_index (const void *pointer, const char *name);
extern int lox_enum_equal (const void *left_pointer, const void *right_pointer);
/* ---------------------------------------------------------------------------
 * Runtime type descriptors (`is`/`as`)
 * --------------------------------------------------------------------------- */

extern LoxTypeDesc *lox_type_desc_new (void);
extern const char *lox_parse_type (const char *cursor, LoxTypeDesc *desc);
extern LoxTypeDesc *lox_type_parse_cached (const char *text);
extern int lox_class_id_matches (const void *descriptor, int64_t id);
extern int lox_type_matches_desc (int64_t tag, int64_t payload, const LoxTypeDesc *type);
extern int lox_type_matches_str (int64_t tag, int64_t payload, const char *text);
extern int64_t utf8_cp_offset (const LoxStr *string, int64_t index);
extern void *lox_str_char_at (const void *pointer, int64_t index);
extern int64_t utf8_decode (const unsigned char *data, size_t *length);
extern int64_t lox_int_pow (int64_t base, int64_t exponent, int32_t line, int32_t column);
extern int64_t lox_int_add_checked (int64_t left, int64_t right, int32_t line, int32_t column);
extern int64_t lox_int_sub_checked (int64_t left, int64_t right, int32_t line, int32_t column);
extern int64_t lox_int_mul_checked (int64_t left, int64_t right, int32_t line, int32_t column);
extern int64_t lox_int_neg_checked (int64_t value, int32_t line, int32_t column);
extern int64_t lox_int_pow_checked (int64_t base, int64_t exponent, int32_t line, int32_t column);
extern int64_t lox_int_div_checked (int64_t left, int64_t right, int32_t line, int32_t column);
extern int64_t lox_int_mod_checked (int64_t left, int64_t right, int32_t line, int32_t column);
extern int64_t lox_math_abs_int_checked (int64_t value, int32_t line, int32_t column);
extern double lox_math_min (double left, double right);
extern double lox_math_max (double left, double right);
extern double lox_math_clamp (double value, double low, double high, int32_t line, int32_t column);
extern int64_t lox_shift (int64_t value, int64_t count, int32_t kind, int32_t line, int32_t column);
extern int64_t lox_float_to_int (double value, int32_t line, int32_t column);
/* ---------------------------------------------------------------------------
 * Exceptions and try frames
 * --------------------------------------------------------------------------- */

extern void *lox_try_push (void);
extern void *lox_try_buffer (void *pointer);
extern void lox_try_pop (void *pointer);
extern void *lox_try_exception (void *pointer);
extern void *lox_exception_instance (const void *pointer);
extern const char *lox_exception_message (const void *pointer);
extern int32_t lox_exception_matches (const void *pointer, const void *expected,
                                     const char *type_name);
/* ADR-0120: `file:line:column` strings for caught exceptions. */
extern void *lox_exception_site (int32_t line, int32_t column);
extern void *lox_exception_site_at (const void *pointer);
/* ---------------------------------------------------------------------------
 * Runtime diagnostics and panic
 * --------------------------------------------------------------------------- */

extern void lox_print_prefix_at (const char *file, int32_t line, int32_t column, const char *code);
extern void lox_throw_internal_at (const char *file, const char *code, void *instance, const char *type_name, const char *message, int32_t line, int32_t column, int64_t trace_depth);
extern void lox_throw_internal (const char *code, void *instance, const char *type_name, const char *message, int32_t line, int32_t column);
extern void lox_throw (void *instance, const char *type_name, const char *message, int32_t line, int32_t column);
extern void lox_rethrow (void *exception_pointer, int32_t line, int32_t column);
extern void lox_raise_current (int32_t line, int32_t column);
extern void lox_raise_value (void *pointer, int32_t line, int32_t column);
extern void lox_panic_at (const char *file, int32_t line, int32_t column, const char *code, const char *message);
extern void lox_panic (int32_t line, int32_t column, const char *code, const char *message);
/* ---------------------------------------------------------------------------
 * Scalar printing and UTF-8 helpers
 * --------------------------------------------------------------------------- */

extern void lox_print_int (int64_t value);
extern void lox_print_bool (int32_t value);
extern void lox_print_nil (void);
extern void format_double (double value, char *out, size_t size);
extern void format_float_value (double value, char *out, size_t size);
extern void lox_print_float (double value);
extern LoxStr *string_from_ascii (const char *data, size_t length);
extern LoxStr *string_from_bytes (const char *data, size_t length, int64_t code_points);
extern const char *lox_str_data (const void *pointer);
extern void *lox_str_from_int (int64_t value);
extern void *lox_str_from_double (double value);
extern void *lox_str_from_bool (int32_t value);
extern void *lox_str_nil (void);
extern void *lox_str_from_cstr (const char *data);
extern void *lox_str_quote (const void *pointer);
extern void buffer_init (LoxBuffer *buffer);
extern void buffer_need (LoxBuffer *buffer, size_t extra);
extern void buffer_char (LoxBuffer *buffer, char byte);
extern void buffer_text (LoxBuffer *buffer, const char *text);
extern void buffer_bytes (LoxBuffer *buffer, const char *data, size_t length);
extern void format_enum (LoxBuffer *buffer, const LoxEnumValue *value);
extern void format_tuple (LoxBuffer *buffer, const LoxTuple *tuple);
extern void format_map (LoxBuffer *buffer, const LoxMap *map);
extern void format_list (LoxBuffer *buffer, const LoxList *list);
extern void format_value (LoxBuffer *buffer, LoxValue value);
extern void lox_print_list (const void *pointer);
extern void lox_print_map (const void *pointer);
extern void lox_print_enum (const void *pointer);
extern void *lox_str_from_enum (const void *pointer);
extern void lox_print_tuple (const void *pointer);
extern void *lox_str_from_tuple (const void *pointer);
extern void *lox_str_from_map (const void *pointer);
extern void *lox_str_from_list (const void *pointer);
extern void *lox_str_from_any (int64_t tag, int64_t payload);
extern void *lox_repr_from_any (int64_t tag, int64_t payload);
/* ---------------------------------------------------------------------------
 * Arithmetic guards and dynamic Any printing
 * --------------------------------------------------------------------------- */

extern int64_t lox_int_div (int64_t left, int64_t right, int32_t line, int32_t column);
extern double lox_float_div (double left, double right, int32_t line, int32_t column);
extern double lox_float_mod (double left, double right, int32_t line, int32_t column);
extern int64_t lox_int_mod (int64_t left, int64_t right, int32_t line, int32_t column);
extern double lox_float_pow (double base, double exponent, int32_t line, int32_t column);
extern LoxValue lox_any_binary (int32_t op, int64_t left_tag, int64_t left_payload,
                                int64_t right_tag, int64_t right_payload,
                                int32_t line, int32_t column);
extern LoxValue lox_any_neg (int64_t tag, int64_t payload, int32_t line, int32_t column);
extern LoxValue lox_any_bit_not (int64_t tag, int64_t payload, int32_t line, int32_t column);
extern int32_t lox_any_compare (int32_t op, int64_t left_tag, int64_t left_payload,
                                int64_t right_tag, int64_t right_payload,
                                int32_t line, int32_t column);
extern void lox_print_any (int64_t tag, int64_t payload);
extern int64_t utf8_code_points (const char *data, size_t length);
extern int utf8_valid (const unsigned char *data, size_t length);
extern size_t utf8_complete_prefix (const unsigned char *data, size_t length);
extern int compare_dir_names (const void *left, const void *right);

#endif /* LOX_RUNTIME_H */
