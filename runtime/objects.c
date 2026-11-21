/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/*
 * objects.c — class/interface identity and the `is`/`as` matcher.
 *
 * Who calls it: the class/interface lowering and the dynamic (`Any`) path in
 * lower_class_codegen.py, lower_instances.py and lower_model.py. Generated code
 * passes compact type strings (grammar below) and the matcher caches them by
 * pointer in the `lox_type_cache` global.
 *
 * Invariants:
 *  - class descriptor = {super, id, name, vtable, ...} (ADR-0048/0080);
 *  - inheritance is the `super` chain; `lox_is_instance` compares descriptors;
 *  - the type cache assumes the string is an immutable literal/global;
 *  - `LoxValue` tags: 0 nil, 1 Int, 2 Float, 3 Bool, 4 String, 5 Class,
 *    6 Instance, 7 Function, 8 Range, 9 List, 10 Map, 11 Tuple, 12 Enum.
 *
 * ADRs: 0025/0029 (`is`/`as`), 0080 (interfaces), 0048 (class ABI).
 */
#include "lox_runtime.h"

LoxTypeCache *lox_type_cache = NULL;

/* ---------------------------------------------------------------------------
 * Interface dispatch (ADR-0080)
 * --------------------------------------------------------------------------- */

/* Looks up `method_index` in the itab of interface `interface_id`. The itab is
 * parallel to the method declaration order; R1004 when the instance does not
 * implement the interface. */
void *lox_interface_method(const void *instance, int64_t interface_id,
                           int64_t method_index) {
    if (instance == NULL) {
        lox_panic(0, 0, "R1004", "Interface method not found.");
        return NULL;
    }
    const LoxClassDescRuntime *descriptor =
        *(const LoxClassDescRuntime * const *)instance;
    const LoxInterfaceEntryRuntime *entries = descriptor->interfaces;
    for (int64_t index = 0; index < descriptor->interface_count; index++) {
        if (entries[index].interface_id == interface_id) {
            void **itab = entries[index].itab;
            return itab[method_index];
        }
    }
    lox_panic(0, 0, "R1004", "Interface method not found.");
    return NULL;
}

/* Nominal class `is`: walks the `super` chain comparing descriptors. */
int lox_is_instance(void *descriptor, void *target) {
    while (descriptor != NULL) {
        if (descriptor == target) {
            return 1;
        }
        descriptor = *(void **)descriptor;
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * Runtime types for `is`/`as` (ADR-0025, ADR-0029)
 *
 * The lowering serializes the target type into a compact string and the matcher
 * walks lists, maps and tuples with the same runtime accessors. The tree is
 * cached by string pointer (the global owned by each `is`/`as` site).
 *
 * Grammar: A=Any, X=never, N=nil, B=Bool, I=Int, F=Float, S=String,
 * R=Range, L<T>=List, M<K,V>=Map, T<T1,...>=Tuple, U<T1|...>=Union,
 * E<id>=enum, C<id>=class.
 *
 * `kind` uses the LoxValue tag for concrete types; -1 is Any, -2 is union and
 * -3 is never. For E/C, `count` stores the id (negative for local classes).
 * --------------------------------------------------------------------------- */

/* Allocates a zeroed node (kind 0 = nil). */
LoxTypeDesc *lox_type_desc_new(void) {
    LoxTypeDesc *desc = lox_alloc(sizeof(LoxTypeDesc));
    desc->kind = 0;
    desc->a = NULL;
    desc->b = NULL;
    desc->count = 0;
    desc->items = NULL;
    return desc;
}

/* Recursive parser for the compact string: consumes `<`, `,`, `|` and `>` and
 * returns the cursor just past the type. Inner nodes are GC-allocated. */
const char *lox_parse_type(const char *cursor, LoxTypeDesc *desc) {
    char kind = *cursor++;
    switch (kind) {
    case 'A':
        desc->kind = -1;
        return cursor;
    case 'X':
        desc->kind = -3;
        return cursor;
    case 'N':
        desc->kind = 0;
        return cursor;
    case 'I':
        desc->kind = 1;
        return cursor;
    case 'F':
        desc->kind = 2;
        return cursor;
    case 'B':
        desc->kind = 3;
        return cursor;
    case 'S':
        desc->kind = 4;
        return cursor;
    case 'R':
        desc->kind = 8;
        return cursor;
    case 'Y':
        desc->kind = 13;
        return cursor;
    case 'L':
        desc->kind = 9;
        cursor++; /* '<' */
        desc->a = lox_type_desc_new();
        cursor = lox_parse_type(cursor, desc->a);
        cursor++; /* '>' */
        return cursor;
    case 'M':
        desc->kind = 10;
        cursor++; /* '<' */
        desc->a = lox_type_desc_new();
        cursor = lox_parse_type(cursor, desc->a);
        cursor++; /* ',' */
        desc->b = lox_type_desc_new();
        cursor = lox_parse_type(cursor, desc->b);
        cursor++; /* '>' */
        return cursor;
    case 'T':
    case 'U': {
        desc->kind = kind == 'T' ? 11 : -2;
        cursor++; /* '<' */
        int64_t capacity = 0;
        int64_t count = 0;
        LoxTypeDesc *items = NULL;
        for (;;) {
            LoxTypeDesc *item = lox_type_desc_new();
            cursor = lox_parse_type(cursor, item);
            if (count == capacity) {
                capacity = capacity == 0 ? 4 : capacity * 2;
                LoxTypeDesc *grown =
                    lox_alloc(sizeof(LoxTypeDesc) * (size_t)capacity);
                if (items != NULL) {
                    memcpy(grown, items,
                           sizeof(LoxTypeDesc) * (size_t)count);
                }
                items = grown;
            }
            items[count] = *item;
            count += 1;
            if (*cursor == ',' || *cursor == '|') {
                cursor += 1;
                continue;
            }
            break;
        }
        desc->count = count;
        desc->items = items;
        cursor++; /* '>' */
        return cursor;
    }
    case 'E':
    case 'C': {
        desc->kind = kind == 'E' ? 12 : 6;
        cursor++; /* '<' */
        int64_t value = 0;
        int negative = 0;
        if (*cursor == '-') {
            negative = 1;
            cursor += 1;
        }
        while (*cursor >= '0' && *cursor <= '9') {
            value = value * 10 + (*cursor - '0');
            cursor += 1;
        }
        desc->count = negative ? -value : value;
        cursor++; /* '>' */
        return cursor;
    }
    default:
        desc->kind = -3;
        return cursor;
    }
}

/* Cache by string pointer identity (the text is not copied): each `is`/`as` site
 * owns a constant global, so the pointer is stable. */
LoxTypeDesc *lox_type_parse_cached(const char *text) {
    for (LoxTypeCache *entry = lox_type_cache; entry != NULL;
         entry = entry->next) {
        if (entry->text == text) {
            return entry->desc;
        }
    }
    LoxTypeDesc *desc = lox_type_desc_new();
    (void)lox_parse_type(text, desc);
    LoxTypeCache *entry = lox_alloc(sizeof(LoxTypeCache));
    entry->text = text;
    entry->desc = desc;
    entry->next = lox_type_cache;
    lox_type_cache = entry;
    return desc;
}

/* ---------------------------------------------------------------------------
 * Class descriptors
 * --------------------------------------------------------------------------- */

/* Class descriptor: [super, id, name, ...]. The instance stores its descriptor
 * in the first field; inheritance is the `super` chain. */
int lox_class_id_matches(const void *descriptor, int64_t id) {
    while (descriptor != NULL) {
        const int64_t *words = descriptor;
        if (words[1] == id) {
            return 1;
        }
        descriptor = *(const void *const *)descriptor;
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * `is`/`as` matcher
 * --------------------------------------------------------------------------- */

/* Decides whether `(tag, payload)` matches the `type` tree. Containers walk their
 * elements; classes compare the id along the inheritance chain; enums compare
 * the id. `is`/`as` call it with the tree cached by `lox_type_parse_cached`. */
int lox_type_matches_desc(int64_t tag, int64_t payload,
                                 const LoxTypeDesc *type) {
    if (type == NULL || type->kind == -1) {
        return 1;
    }
    if (type->kind == -2) {
        for (int64_t index = 0; index < type->count; index++) {
            if (lox_type_matches_desc(tag, payload, &type->items[index])) {
                return 1;
            }
        }
        return 0;
    }
    if (type->kind == -3 || tag != type->kind) {
        return 0;
    }
    switch (tag) {
    case 0: /* nil */
    case 1: /* int */
    case 2: /* float */
    case 3: /* bool */
    case 4: /* string */
    case 8: /* range */
        return 1;
    case 6: { /* instance */
        const void *instance = (const void *)payload;
        return lox_class_id_matches(*(const void *const *)instance,
                                    type->count);
    }
    case 9: { /* list */
        const void *list = (const void *)payload;
        if (type->a == NULL || type->a->kind == -1) {
            return 1;
        }
        int64_t count = lox_list_len(list);
        for (int64_t index = 0; index < count; index++) {
            LoxValue item = lox_list_get(list, index, 0, 0);
            if (!lox_type_matches_desc(item.tag, item.payload, type->a)) {
                return 0;
            }
        }
        return 1;
    }
    case 10: { /* map */
        const LoxMap *map = (const LoxMap *)payload;
        for (int64_t index = 0; index < map->count; index++) {
            LoxValue key = map->entries[index].key;
            LoxValue value = map->entries[index].value;
            if (type->a != NULL && type->a->kind != -1 &&
                !lox_type_matches_desc(key.tag, key.payload, type->a)) {
                return 0;
            }
            if (type->b != NULL && type->b->kind != -1 &&
                !lox_type_matches_desc(value.tag, value.payload, type->b)) {
                return 0;
            }
        }
        return 1;
    }
    case 11: { /* tuple */
        const void *tuple = (const void *)payload;
        if (lox_tuple_len(tuple) != type->count) {
            return 0;
        }
        for (int64_t index = 0; index < type->count; index++) {
            LoxValue item = lox_tuple_get(tuple, index, 0, 0);
            if (!lox_type_matches_desc(item.tag, item.payload,
                                       &type->items[index])) {
                return 0;
            }
        }
        return 1;
    }
    case 12: /* enum */
        return ((const LoxEnumValue *)payload)->enum_id == type->count;
    case 13: /* bytes */
        return 1;
    default:
        return 0;
    }
}

int lox_type_matches_str(int64_t tag, int64_t payload, const char *text) {
    return lox_type_matches_desc(tag, payload, lox_type_parse_cached(text));
}
