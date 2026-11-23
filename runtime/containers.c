/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * containers.c — `Range`, `List`, `Map`, tuple, enum values and the structural
 * equality used by `==` on the native path.
 *
 * Who calls it: the container lowering (lower_range/list/map/tuple/enums) and
 * `format_value`/`lox_print_any` from strings.c. The interpreter is the oracle
 * for all semantics here.
 *
 * Invariants:
 *  - lists and maps preserve insertion order; `version` increments on every
 *    mutation and is how `for-in` detects mutation during iteration;
 *  - map keys may only be String/Int/Bool (ADR-0017);
 *  - `LoxValue` is `{tag, payload}`; Float goes in `payload` via memcpy;
 *  - container equality is structural and dispatches by tag;
 *  - cycles are cut in equality/`str` (bounded depth).
 *
 * ADRs: 0007 (Range), 0017 (Map), 0036 (tuples), 0041 (enums), 0049 (Any).
 */
#include "lox_runtime.h"


/* ---------------------------------------------------------------------------
 * Range (ADR-0007)
 * --------------------------------------------------------------------------- */

/* Immutable Range `{start, end, step, inclusive}`; step 0 is R1014. `inclusive`
 * makes the end participate in iteration and in the `..=` format. */
void *lox_range_new(int64_t start, int64_t end, int64_t step,
                    int32_t inclusive, int32_t line, int32_t column) {
    if (step == 0) {
        lox_panic(line, column, "R1000", "range() step can't be zero.");
    }
    LoxRange *range = lox_alloc(sizeof(LoxRange));
    range->start = start;
    range->end = end;
    range->step = step;
    range->inclusive = inclusive != 0 ? 1 : 0;
    return range;
}

/* Accessors used by the `for-in` lowering and by `is`/`as`. */
int64_t lox_range_start(const void *pointer) {
    return ((const LoxRange *)pointer)->start;
}

int64_t lox_range_end(const void *pointer) {
    return ((const LoxRange *)pointer)->end;
}

int64_t lox_range_step(const void *pointer) {
    return ((const LoxRange *)pointer)->step;
}

int32_t lox_range_inclusive(const void *pointer) {
    return ((const LoxRange *)pointer)->inclusive;
}

/* Equality by start/end/step/inclusive (ranges do not support `<`). */
int32_t lox_range_equal(const void *left_pointer, const void *right_pointer) {
    const LoxRange *left = left_pointer;
    const LoxRange *right = right_pointer;
    return left->start == right->start && left->end == right->end &&
           left->step == right->step && left->inclusive == right->inclusive;
}

/* `print(Range)` as `<range a..b>`/`<range a..=b step s>`. */
void lox_print_range(const void *pointer) {
    const LoxRange *range = pointer;
    const char *operator = range->inclusive ? "..=" : "..";
    if (range->step == 1) {
        printf("<range %" PRId64 "%s%" PRId64 ">\n", range->start, operator,
               range->end);
    } else {
        printf("<range %" PRId64 "%s%" PRId64 " step %" PRId64 ">\n",
               range->start, operator, range->end, range->step);
    }
}

/* `str(Range)` for `str`/interpolation.
 *
 * NOTE: this format always uses `..`, ignoring `inclusive`; `lox_print_range`
 * uses the correct operator. No corpus case compares `str(..=)` across engines —
 * if you fix this, add the differential golden with it. */
void *lox_str_from_range(const void *pointer) {
    const LoxRange *range = pointer;
    const char *operator = range->inclusive ? "..=" : "..";
    char buffer[128];
    int length;
    if (range->step == 1) {
        length = snprintf(buffer, sizeof buffer,
                          "<range %" PRId64 "%s%" PRId64 ">",
                          range->start, operator, range->end);
    } else {
        length = snprintf(buffer, sizeof buffer,
                          "<range %" PRId64 "%s%" PRId64 " step %" PRId64 ">",
                          range->start, operator, range->end, range->step);
    }
    return string_from_ascii(buffer, (size_t)length);
}



/* ---------------------------------------------------------------------------
 * List (ADR-0015/0031)
 *
 * Doubling `LoxValue` array. `count` is the logical size; `capacity` is the
 * allocation. The old array is left to the GC. `version` is the mutation
 * discriminator observed by `for-in`.
 * --------------------------------------------------------------------------- */

/* Element kinds for typed storage: 0 = boxed `LoxValue`, 1..4 mirror the value
 * tags (Int, Float, Bool, String). A typed array stores the payload in an i64
 * slot (Float keeps its bit pattern), so `lox_list_value_at` can rebuild the
 * `LoxValue` without allocating; String slots hold pointers and are scanned. */

static void *list_raw_new(int32_t kind, int64_t capacity) {
    size_t bytes = sizeof(int64_t) * (size_t)capacity;
    return kind == 4 ? lox_alloc(bytes) : lox_alloc_atomic(bytes);
}

/* Boxed-value view of one element (no bounds check; internal callers iterate). */
LoxValue lox_list_value_at(const LoxList *list, int64_t index) {
    if (list->kind == 0) {
        return list->items[index];
    }
    LoxValue value;
    value.tag = list->kind;
    value.payload = ((const int64_t *)list->raw)[index];
    return value;
}

/* Converts typed storage to boxed `LoxValue` storage (once). */
static void list_promote(LoxList *list) {
    if (list->kind == 0) {
        return;
    }
    LoxValue *items = lox_alloc(sizeof(LoxValue) * (size_t)list->capacity);
    for (int64_t index = 0; index < list->count; index++) {
        items[index] = lox_list_value_at(list, index);
    }
    list->items = items;
    list->raw = NULL;
    list->kind = 0;
}

/* Empty list with initial capacity 4 (boxed storage). */
void *lox_list_new(void) {
    LoxList *list = lox_alloc(sizeof(LoxList));
    list->count = 0;
    list->capacity = 4;
    list->items = lox_alloc(sizeof(LoxValue) * (size_t)list->capacity);
    list->version = 0;
    list->raw = NULL;
    list->kind = 0;
    return list;
}

/* Empty list whose elements are `kind` (1 Int, 2 Float, 3 Bool, 4 String). */
void *lox_list_new_typed(int32_t kind) {
    LoxList *list = lox_alloc(sizeof(LoxList));
    list->count = 0;
    list->capacity = 4;
    list->items = NULL;
    list->version = 0;
    list->raw = list_raw_new(kind, list->capacity);
    list->kind = kind;
    return list;
}

/* Doubles capacity and copies the elements; the old array is collected. */
void lox_list_grow(LoxList *list) {
    int64_t capacity = list->capacity * 2;
    if (list->kind == 0) {
        LoxValue *items = lox_alloc(sizeof(LoxValue) * (size_t)capacity);
        for (int64_t index = 0; index < list->count; index++) {
            items[index] = list->items[index];
        }
        list->items = items;
    } else {
        int64_t *raw = list_raw_new(list->kind, capacity);
        memcpy(raw, list->raw, sizeof(int64_t) * (size_t)list->count);
        list->raw = raw;
    }
    list->capacity = capacity;
}

/* `push`: grows if needed, writes at the end and increments `version`.
 * A tag that does not match the typed element kind promotes to boxed. */
void lox_list_push(void *pointer, int64_t tag, int64_t payload) {
    LoxList *list = pointer;
    if (list->kind != 0 && tag != (int64_t)list->kind) {
        list_promote(list);
    }
    if (list->count == list->capacity) {
        lox_list_grow(list);
    }
    if (list->kind == 0) {
        list->items[list->count].tag = tag;
        list->items[list->count].payload = payload;
    } else {
        ((int64_t *)list->raw)[list->count] = payload;
    }
    list->count += 1;
    list->version += 1;
}

/* `len(xs)`. */
int64_t lox_list_len(const void *pointer) {
    return ((const LoxList *)pointer)->count;
}

/* `for-in` guard: mutation while iterating is R1012, as in the tree-walk. */
int64_t lox_list_version(const void *pointer) {
    return ((const LoxList *)pointer)->version;
}

/* `xs[i]`; an index outside 0..count-1 is R1007, com índice e tamanho como
 * no tree-walk (`List index 2 out of bounds for length 1.`). */
static void panic_index(const char *kind, int64_t index, int64_t count,
                        int32_t line, int32_t column) {
    char message[128];
    int length = snprintf(message, sizeof message,
                          "%s index %" PRId64 " out of bounds for length %" PRId64 ".",
                          kind, index, count);
    lox_panic(line, column, "R1007", message);
    (void)length;
}

LoxValue lox_list_get(const void *pointer, int64_t index, int32_t line,
                      int32_t column) {
    const LoxList *list = pointer;
    if (index < 0 || index >= list->count) {
        panic_index("List", index, list->count, line, column);
    }
    return lox_list_value_at(list, index);
}

/* `xs[i] = v`; an index outside 0..count-1 is R1007; increments `version`. */
void lox_list_set(void *pointer, int64_t index, int64_t tag, int64_t payload,
                  int32_t line, int32_t column) {
    LoxList *list = pointer;
    if (index < 0 || index >= list->count) {
        panic_index("List", index, list->count, line, column);
    }
    if (list->kind != 0 && tag != (int64_t)list->kind) {
        list_promote(list);
    }
    if (list->kind == 0) {
        list->items[index].tag = tag;
        list->items[index].payload = payload;
    } else {
        ((int64_t *)list->raw)[index] = payload;
    }
    list->version += 1;
}

/* `pop`: removes from the end; an empty list is R1007; increments `version`. */
LoxValue lox_list_pop(void *pointer, int32_t line, int32_t column) {
    LoxList *list = pointer;
    if (list->count == 0) {
        lox_panic(line, column, "R1007", "Can't pop from an empty list.");
    }
    list->count -= 1;
    list->version += 1;
    return lox_list_value_at(list, list->count);
}


/* Structural list equality, element by element. */
int lox_list_equal(const void *left_pointer, const void *right_pointer) {
    if (left_pointer == right_pointer) {
        return 1;
    }
    const LoxList *left = left_pointer;
    const LoxList *right = right_pointer;
    if (left->count != right->count) {
        return 0;
    }
    for (int64_t index = 0; index < left->count; index++) {
        if (!lox_value_equal(lox_list_value_at(left, index),
                             lox_list_value_at(right, index))) {
            return 0;
        }
    }
    return 1;
}

/* Dynamic `LoxValue` equality (used by `==`, lists, maps and tuples).
 *
 * Int and Float compare numerically with promotion (`1 == 1.0`); NaN != NaN;
 * strings compare content; containers compare structure; other tags compare the
 * payload. */
int lox_value_equal(LoxValue left, LoxValue right) {
    if ((left.tag == 1 || left.tag == 2) &&
        (right.tag == 1 || right.tag == 2)) {
        double a = left.tag == 1 ? (double)left.payload : 0.0;
        double b = right.tag == 1 ? (double)right.payload : 0.0;
        if (left.tag == 2) {
            memcpy(&a, &left.payload, sizeof(a));
        }
        if (right.tag == 2) {
            memcpy(&b, &right.payload, sizeof(b));
        }
        return a == b;
    }
    if (left.tag != right.tag) {
        return 0;
    }
    switch (left.tag) {
        case 0:
            return 1;
        case 1:
        case 3:
            return left.payload == right.payload;
        case 2: {
            double a, b;
            memcpy(&a, &left.payload, sizeof(a));
            memcpy(&b, &right.payload, sizeof(b));
            return a == b;
        }
        case 4:
            return lox_str_equal((const void *)left.payload,
                                 (const void *)right.payload);
        case 8: {
            const LoxRange *a = (const void *)left.payload;
            const LoxRange *b = (const void *)right.payload;
            return a->start == b->start && a->end == b->end &&
                   a->step == b->step;
        }
        case 9:
            return lox_list_equal((const void *)left.payload,
                                  (const void *)right.payload);
        case 10:
            return lox_map_equal((const void *)left.payload,
                                 (const void *)right.payload);
        case 11:
            return lox_tuple_equal((const void *)left.payload,
                                   (const void *)right.payload);
        case 12:
            return lox_enum_equal((const void *)left.payload,
                                  (const void *)right.payload);
        case 13:
            return lox_bytes_equal((const void *)left.payload,
                                   (const void *)right.payload);
        default:
            return left.payload == right.payload;
    }
}



/* ---------------------------------------------------------------------------
 * Map (ADR-0017)
 *
 * Entries stay in insertion order; a separate open-addressing index maps a
 * 64-bit hash to the entry, so lookup is O(1) and `keys`/`values`/`for-in` keep
 * the insertion order the interpreter observes (I3). Keys are String/Int/Bool;
 * `version` increments on every mutation. `set` on an existing key keeps its
 * position and replaces the value; `remove` shifts the entries (O(n)) and
 * rebuilds the index, matching the Python dict order on reinsertion.
 * --------------------------------------------------------------------------- */

/* Empty map: 4 entries, 8 index slots (load factor <= 0.5). */
void *lox_map_new(void) {
    LoxMap *map = lox_alloc(sizeof(LoxMap));
    map->count = 0;
    map->capacity = 4;
    map->entries = lox_alloc(sizeof(LoxMapEntry) * (size_t)map->capacity);
    map->version = 0;
    map->index_capacity = 8;
    map->index = lox_alloc(sizeof(int32_t) * (size_t)map->index_capacity);
    memset(map->index, 0, sizeof(int32_t) * (size_t)map->index_capacity);
    return map;
}

/* Key equality: String by content; Int/Bool by payload + tag. */
int lox_map_key_equal(LoxValue left, LoxValue right) {
    if (left.tag != right.tag) {
        return 0;
    }
    if (left.tag == 4) {
        return lox_str_equal((const void *)left.payload,
                             (const void *)right.payload);
    }
    return left.payload == right.payload;
}

/* 64-bit mix (splitmix64 finalizer) so sequential Int keys do not cluster. */
static uint64_t map_hash(LoxValue key) {
    uint64_t hash;
    if (key.tag == 4) {
        hash = lox_str_hash((const void *)key.payload);
    } else {
        hash = (uint64_t)key.payload ^
               ((uint64_t)key.tag * 0x9e3779b97f4a7c15ULL);
    }
    hash ^= hash >> 30;
    hash *= 0xbf58476d1ce4e5b9ULL;
    hash ^= hash >> 27;
    hash *= 0x94d049bb133111ebULL;
    hash ^= hash >> 31;
    return hash;
}

/* Writes `entry + 1` in the first empty probe slot (the key is absent). */
static void map_index_put(LoxMap *map, int64_t entry) {
    uint64_t mask = (uint64_t)(map->index_capacity - 1);
    uint64_t slot = map_hash(map->entries[entry].key) & mask;
    while (map->index[slot] != 0) {
        slot = (slot + 1) & mask;
    }
    map->index[slot] = (int32_t)(entry + 1);
}

/* Rebuilds the whole index (after remove/grow); O(count). */
static void map_index_rebuild(LoxMap *map) {
    memset(map->index, 0, sizeof(int32_t) * (size_t)map->index_capacity);
    for (int64_t entry = 0; entry < map->count; entry++) {
        map_index_put(map, entry);
    }
}

/* Hashed lookup; returns the entry index or -1. */
int64_t lox_map_find(const LoxMap *map, LoxValue key) {
    if (map->count == 0) {
        return -1;
    }
    uint64_t mask = (uint64_t)(map->index_capacity - 1);
    uint64_t slot = map_hash(key) & mask;
    for (;;) {
        int32_t stored = map->index[slot];
        if (stored == 0) {
            return -1;
        }
        int64_t entry = (int64_t)stored - 1;
        if (lox_map_key_equal(map->entries[entry].key, key)) {
            return entry;
        }
        slot = (slot + 1) & mask;
    }
}

/* Doubles the entries and rebuilds the index with the new capacity. */
void lox_map_grow(LoxMap *map) {
    int64_t capacity = map->capacity * 2;
    LoxMapEntry *entries = lox_alloc(sizeof(LoxMapEntry) * (size_t)capacity);
    memcpy(entries, map->entries, sizeof(LoxMapEntry) * (size_t)map->count);
    map->entries = entries;
    map->capacity = capacity;
    int64_t index_capacity = map->index_capacity;
    while (index_capacity < capacity * 2) {
        index_capacity *= 2;
    }
    map->index = lox_alloc(sizeof(int32_t) * (size_t)index_capacity);
    map->index_capacity = index_capacity;
    map_index_rebuild(map);
}

/* ADR-0017: only String, Int and Bool are keys; the interpreter is the oracle. */
void lox_map_check_key(int64_t tag, int32_t line, int32_t column) {
    if (tag != 1 && tag != 3 && tag != 4) {
        lox_panic(line, column, "R1014",
                  "Map keys must be strings, integers or booleans.");
    }
}

void lox_map_set(void *pointer, int64_t key_tag, int64_t key_payload,
                 int64_t value_tag, int64_t value_payload, int32_t line,
                 int32_t column) {
    LoxMap *map = pointer;
    LoxValue key = {key_tag, key_payload};
    lox_map_check_key(key_tag, line, column);
    int64_t found = lox_map_find(map, key);
    if (found >= 0) {
        map->entries[found].value.tag = value_tag;
        map->entries[found].value.payload = value_payload;
        map->version += 1;
        return;
    }
    if (map->count == map->capacity) {
        lox_map_grow(map);
    }
    map->entries[map->count].key = key;
    map->entries[map->count].value.tag = value_tag;
    map->entries[map->count].value.payload = value_payload;
    map_index_put(map, map->count);
    map->count += 1;
    map->version += 1;
}

/* `Map` literal: chave duplicada é R1014 (o interpretador é o oráculo). */
void lox_map_set_literal(void *pointer, int64_t key_tag, int64_t key_payload,
                         int64_t value_tag, int64_t value_payload,
                         int32_t line, int32_t column) {
    LoxMap *map = pointer;
    LoxValue key = {key_tag, key_payload};
    lox_map_check_key(key_tag, line, column);
    if (lox_map_find(map, key) >= 0) {
        lox_panic(line, column, "R1014", "Duplicate key in map literal.");
    }
    lox_map_set(pointer, key_tag, key_payload, value_tag, value_payload, line,
                column);
}

/* `len(m)`: number of entries. */
int64_t lox_map_len(const void *pointer) {
    return ((const LoxMap *)pointer)->count;
}

/* `for-in` guard: mutation while iterating is R1012, as in the tree-walk. */
int64_t lox_map_version(const void *pointer) {
    return ((const LoxMap *)pointer)->version;
}

/* `m.has(k)`: checks the key without creating an entry. */
int32_t lox_map_has(const void *pointer, int64_t key_tag, int64_t key_payload,
                    int32_t line, int32_t column) {
    LoxValue key = {key_tag, key_payload};
    lox_map_check_key(key_tag, line, column);
    return lox_map_find(pointer, key) >= 0;
}

/* `m.get(k)`: returns `nil` when absent (this is not `m[k]`, which errors). */
LoxValue lox_map_get(const void *pointer, int64_t key_tag, int64_t key_payload,
                     int32_t line, int32_t column) {
    LoxValue key = {key_tag, key_payload};
    lox_map_check_key(key_tag, line, column);
    int64_t found = lox_map_find(pointer, key);
    if (found < 0) {
        LoxValue nil = {0, 0};
        return nil;
    }
    return ((const LoxMap *)pointer)->entries[found].value;
}

/* `m[k]`: a missing key is R1008. */
LoxValue lox_map_get_checked(const void *pointer, int64_t key_tag,
                             int64_t key_payload, int32_t line,
                             int32_t column) {
    LoxValue key = {key_tag, key_payload};
    lox_map_check_key(key_tag, line, column);
    int64_t found = lox_map_find(pointer, key);
    if (found < 0) {
        lox_panic(line, column, "R1008", "Key not found in map.");
    }
    return ((const LoxMap *)pointer)->entries[found].value;
}

/* `m.remove(k)`: R1008 when absent; shifts the entries and rebuilds the index. */
LoxValue lox_map_remove(void *pointer, int64_t key_tag, int64_t key_payload,
                        int32_t line, int32_t column) {
    LoxMap *map = pointer;
    LoxValue key = {key_tag, key_payload};
    lox_map_check_key(key_tag, line, column);
    int64_t found = lox_map_find(map, key);
    if (found < 0) {
        lox_panic(line, column, "R1008", "Key not found in map.");
    }
    LoxValue value = map->entries[found].value;
    for (int64_t index = found; index + 1 < map->count; index++) {
        map->entries[index] = map->entries[index + 1];
    }
    map->count -= 1;
    map->version += 1;
    map_index_rebuild(map);
    return value;
}

/* Key at position `index` (used by `for-in`). */
LoxValue lox_map_key_at(const void *pointer, int64_t index) {
    return ((const LoxMap *)pointer)->entries[index].key;
}

/* `m.keys`: new list in insertion order. */
void *lox_map_keys(const void *pointer) {
    const LoxMap *map = pointer;
    void *list = lox_list_new();
    for (int64_t index = 0; index < map->count; index++) {
        lox_list_push(list, map->entries[index].key.tag,
                      map->entries[index].key.payload);
    }
    return list;
}

/* `m.values`: new list in insertion order. */
void *lox_map_values(const void *pointer) {
    const LoxMap *map = pointer;
    void *list = lox_list_new();
    for (int64_t index = 0; index < map->count; index++) {
        lox_list_push(list, map->entries[index].value.tag,
                      map->entries[index].value.payload);
    }
    return list;
}

int lox_map_equal(const void *left_pointer, const void *right_pointer) {
    /* Cycle guard: `depth` is shared across recursion; every path that
       increments it must decrement before returning. */
    static int depth = 0;
    if (left_pointer == right_pointer) {
        return 1;
    }
    if (depth > 32) {
        return 1;
    }
    depth += 1;
    const LoxMap *left = left_pointer;
    const LoxMap *right = right_pointer;
    int result = 0;
    if (left->count == right->count) {
        result = 1;
        for (int64_t index = 0; index < left->count; index++) {
            LoxValue key = left->entries[index].key;
            int64_t found = lox_map_find(right, key);
            if (found < 0 || !lox_value_equal(left->entries[index].value,
                                               right->entries[found].value)) {
                result = 0;
                break;
            }
        }
    }
    depth -= 1;
    return result;
}



/* ---------------------------------------------------------------------------
 * Tuple (ADR-0036)
 * --------------------------------------------------------------------------- */

/* Immutable tuple of fixed arity; the lowering fills it with `lox_tuple_set`. */
void *lox_tuple_new(int64_t count) {
    LoxTuple *tuple = lox_alloc(sizeof(LoxTuple));
    tuple->count = count;
    tuple->items = lox_alloc(sizeof(LoxValue) * (size_t)(count > 0 ? count : 1));
    return tuple;
}

/* Fills position `index` during construction (no bounds check). */
void lox_tuple_set(void *pointer, int64_t index, int64_t tag, int64_t payload) {
    LoxTuple *tuple = pointer;
    tuple->items[index].tag = tag;
    tuple->items[index].payload = payload;
}

/* `t[i]`; an index outside 0..count-1 is R1007. */
LoxValue lox_tuple_get(const void *pointer, int64_t index, int32_t line,
                       int32_t column) {
    const LoxTuple *tuple = pointer;
    if (index < 0 || index >= tuple->count) {
        panic_index("Tuple", index, tuple->count, line, column);
    }
    return tuple->items[index];
}

/* `len(t)`. */
int64_t lox_tuple_len(const void *pointer) {
    return ((const LoxTuple *)pointer)->count;
}

/* Structural tuple equality (arity + elements). */
int lox_tuple_equal(const void *left_pointer, const void *right_pointer) {
    if (left_pointer == right_pointer) {
        return 1;
    }
    const LoxTuple *left = left_pointer;
    const LoxTuple *right = right_pointer;
    if (left->count != right->count) {
        return 0;
    }
    for (int64_t index = 0; index < left->count; index++) {
        if (!lox_value_equal(left->items[index], right->items[index])) {
            return 0;
        }
    }
    return 1;
}

/* Lowering entry point for `==` on the dynamic path. */
int lox_any_equal(int64_t left_tag, int64_t left_payload, int64_t right_tag,
                  int64_t right_payload) {
    LoxValue left = {left_tag, left_payload};
    LoxValue right = {right_tag, right_payload};
    return lox_value_equal(left, right);
}

/* Recognizes a 2-element tuple with the given tags (destructuring). */
int lox_tuple_is2(const void *pointer, int64_t tag0, int64_t tag1) {
    const LoxTuple *tuple = pointer;
    if (tuple->count != 2) {
        return 0;
    }
    return tuple->items[0].tag == tag0 && tuple->items[1].tag == tag1;
}



/* ---------------------------------------------------------------------------
 * Enum (ADR-0041)
 * --------------------------------------------------------------------------- */

/* Immutable enum: enum id + stable variant name + boxed payload. */
void *lox_enum_new(int64_t enum_id, const char *enum_name,
                   const char *variant_name, int64_t count) {
    LoxEnumValue *value = lox_alloc(sizeof(LoxEnumValue));
    value->enum_id = enum_id;
    value->enum_name = enum_name;
    value->variant_name = variant_name;
    value->count = count;
    value->payload = lox_alloc(sizeof(LoxValue) * (size_t)(count > 0 ? count : 1));
    return value;
}

/* Fills the payload during construction. */
void lox_enum_set(void *pointer, int64_t index, int64_t tag, int64_t payload) {
    LoxEnumValue *value = pointer;
    value->payload[index].tag = tag;
    value->payload[index].payload = payload;
}

/* Payload access in `match`; an invalid index is R1007. */
LoxValue lox_enum_payload(const void *pointer, int64_t index, int32_t line,
                          int32_t column) {
    const LoxEnumValue *value = pointer;
    if (index < 0 || index >= value->count) {
        lox_panic(line, column, "R1007", "Enum payload index out of bounds.");
    }
    return value->payload[index];
}

/* Reserved: the current lowering compares variants by name through
 * `lox_enum_variant_index`; generated code does not call this helper. */
int64_t lox_enum_variant(const void *pointer) {
    const LoxEnumValue *value = pointer;
    /* Variants are compared by stable name; the backend passes the index. */
    return value->count >= 0 ? (int64_t)0 : (int64_t)0;
}

/* Variant `match`: compares the stable name and returns 1/0. */
int64_t lox_enum_variant_index(const void *pointer, const char *name) {
    const LoxEnumValue *value = pointer;
    return strcmp(value->variant_name, name) == 0 ? 1 : 0;
}

/* Structural equality: enum id + variant + payload. */
int lox_enum_equal(const void *left_pointer, const void *right_pointer) {
    if (left_pointer == right_pointer) {
        return 1;
    }
    const LoxEnumValue *left = left_pointer;
    const LoxEnumValue *right = right_pointer;
    if (left->enum_id != right->enum_id ||
        strcmp(left->variant_name, right->variant_name) != 0 ||
        left->count != right->count) {
        return 0;
    }
    for (int64_t index = 0; index < left->count; index++) {
        if (!lox_value_equal(left->payload[index], right->payload[index])) {
            return 0;
        }
    }
    return 1;
}
