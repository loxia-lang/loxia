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

/* True when the class descriptor lists `interface_id`. The table holds the
 * effective interfaces (own + inherited, ADR-0080/0146). */
static int lox_implements_interface(const void *descriptor, int64_t interface_id) {
    if (descriptor == NULL) {
        return 0;
    }
    const LoxClassDescRuntime *desc = (const LoxClassDescRuntime *)descriptor;
    const LoxInterfaceEntryRuntime *entries = desc->interfaces;
    for (int64_t index = 0; index < desc->interface_count; index++) {
        if (entries[index].interface_id == interface_id) {
            return 1;
        }
    }
    return 0;
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
 * E<id>=enum, C<id>=class, J<id>=interface.
 *
 * `kind` uses the LoxValue tag for concrete types; -1 is Any, -2 is union,
 * -3 is never and -4 is interface. For E/C/J, `count` stores the id (negative
 * for local classes).
 * --------------------------------------------------------------------------- */

/* Allocates a zeroed node (kind 0 = nil). */
LoxTypeDesc *lox_type_desc_new(void) {
    LoxTypeDesc *desc = lox_alloc(sizeof(LoxTypeDesc));
    desc->kind = 0;
    desc->a = NULL;
    desc->b = NULL;
    desc->count = 0;
    desc->items = NULL;
    desc->sig = NULL;
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
    case 'K': {
        desc->kind = -5;
        cursor++; /* '<' */
        int64_t values[3] = {0, 0, 0};
        for (int index = 0; index < 3; index++) {
            int64_t value = 0;
            while (*cursor >= '0' && *cursor <= '9') {
                value = value * 10 + (*cursor - '0');
                cursor += 1;
            }
            values[index] = value;
            cursor += 1; /* ',' */
        }
        LoxFnSig *sig = lox_alloc(sizeof(LoxFnSig));
        sig->min_arity = values[0];
        sig->variadic = values[1];
        sig->n_params = values[2];
        sig->max_arity = values[1] ? INT64_MAX : values[2];
        sig->params = values[2] > 0
            ? lox_alloc(sizeof(LoxTypeDesc *) * (size_t)values[2])
            : NULL;
        for (int64_t index = 0; index < values[2]; index++) {
            sig->params[index] = lox_type_desc_new();
            cursor = lox_parse_type(cursor, sig->params[index]);
            cursor += 1; /* ',' */
        }
        sig->ret = lox_type_desc_new();
        cursor = lox_parse_type(cursor, sig->ret);
        cursor += 1; /* '>' */
        desc->sig = sig;
        return cursor;
    }
    case 'E':
    case 'C':
    case 'J': {
        desc->kind = kind == 'E' ? 12 : (kind == 'C' ? 6 : -4);
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

/* ADR-0147: type-to-type equality/assignability and function signatures. */
static int lox_type_equal(const LoxTypeDesc *a, const LoxTypeDesc *b);
static int lox_fn_equal(const LoxFnSig *a, const LoxFnSig *b);
static int lox_implements_interface(const void *descriptor, int64_t interface_id);
int lox_class_id_matches(const void *descriptor, int64_t id);

#define LOX_CLASS_REGISTRY_MAX 4096
static void *lox_class_registry[LOX_CLASS_REGISTRY_MAX];
static int64_t lox_class_registry_count;

void lox_register_class(void *descriptor) {
    if (lox_class_registry_count < LOX_CLASS_REGISTRY_MAX) {
        lox_class_registry[lox_class_registry_count++] = descriptor;
    }
}

void *lox_class_desc_for_id(int64_t id) {
    for (int64_t index = 0; index < lox_class_registry_count; index++) {
        const int64_t *words = lox_class_registry[index];
        if (words[1] == id) {
            return lox_class_registry[index];
        }
    }
    return NULL;
}

static int lox_fn_equal(const LoxFnSig *a, const LoxFnSig *b) {
    if (a == NULL || b == NULL) {
        return a == b;
    }
    if (a->min_arity != b->min_arity || a->variadic != b->variadic ||
        a->n_params != b->n_params) {
        return 0;
    }
    for (int64_t index = 0; index < a->n_params; index++) {
        if (!lox_type_equal(a->params[index], b->params[index])) {
            return 0;
        }
    }
    return lox_type_equal(a->ret, b->ret);
}

static int lox_type_equal(const LoxTypeDesc *a, const LoxTypeDesc *b) {
    if (a == NULL || b == NULL) {
        return a == b;
    }
    if (a->kind != b->kind) {
        return 0;
    }
    switch (a->kind) {
    case -1: /* Any */
    case -3: /* never */
    case 0:  /* nil */
    case 1:  /* int */
    case 2:  /* float */
    case 3:  /* bool */
    case 4:  /* string */
    case 8:  /* range */
    case 13: /* bytes */
        return 1;
    case 6:  /* class */
    case 12: /* enum */
    case -4: /* interface */
        return a->count == b->count;
    case -5: /* function */
        return lox_fn_equal(a->sig, b->sig);
    case -2: /* union */
    case 11: /* tuple */
        if (a->count != b->count) {
            return 0;
        }
        for (int64_t index = 0; index < a->count; index++) {
            if (!lox_type_equal(&a->items[index], &b->items[index])) {
                return 0;
            }
        }
        return 1;
    case 9: /* list */
        return lox_type_equal(a->a, b->a);
    case 10: /* map */
        return lox_type_equal(a->a, b->a) && lox_type_equal(a->b, b->b);
    default:
        return 0;
    }
}

/* Machine representation code: the backend's ABI must match for a dynamic call. */
static int64_t lox_rep_code(const LoxTypeDesc *type) {
    if (type == NULL) {
        return 0;
    }
    switch (type->kind) {
    case -1: /* Any: two words */
        return 0;
    case 1:
    case 2:
    case 3:
        return (int64_t)type->kind;
    case 0: /* nil */
        return 4;
    case -2: { /* union: optional scalar/pointer keeps the payload representation */
        if (type->count == 2) {
            const LoxTypeDesc *nil = NULL;
            const LoxTypeDesc *other = NULL;
            for (int64_t index = 0; index < 2; index++) {
                if (type->items[index].kind == 0) {
                    nil = &type->items[index];
                } else {
                    other = &type->items[index];
                }
            }
            if (nil != NULL && other != NULL) {
                if (other->kind == 1 || other->kind == 2 || other->kind == 3) {
                    return 100 + (int64_t)other->kind;
                }
                if (other->kind == 4 || other->kind == 6 || other->kind == 8 ||
                    other->kind == 9 || other->kind == 10 || other->kind == 11 ||
                    other->kind == 12 || other->kind == 13 || other->kind == -4 ||
                    other->kind == -5) {
                    return 5;
                }
            }
        }
        return 0; /* a multi-type union is stored as Any */
    }
    case -5: /* function: pointer */
    case 4:
    case 6:
    case 8:
    case 9:
    case 10:
    case 11:
    case 12:
    case 13:
    case -4:
        return 5;
    default:
        return 0;
    }
}

static int lox_rep_equal(const LoxTypeDesc *a, const LoxTypeDesc *b) {
    return lox_rep_code(a) == lox_rep_code(b);
}

int lox_type_assignable(const LoxTypeDesc *expected, const LoxTypeDesc *actual) {
    if (expected == NULL) {
        return 1;
    }
    if (expected->kind == -1) { /* Any accepts anything */
        return 1;
    }
    if (actual == NULL) {
        return 0;
    }
    if (actual->kind == -1) {
        return 0;
    }
    if (expected->kind == -2 && actual->kind == -2) {
        for (int64_t index = 0; index < actual->count; index++) {
            int matched = 0;
            for (int64_t candidate = 0; candidate < expected->count; candidate++) {
                if (lox_type_assignable(&expected->items[candidate],
                                        &actual->items[index])) {
                    matched = 1;
                    break;
                }
            }
            if (!matched) {
                return 0;
            }
        }
        return 1;
    }
    if (expected->kind == -2) {
        for (int64_t index = 0; index < expected->count; index++) {
            if (lox_type_assignable(&expected->items[index], actual)) {
                return 1;
            }
        }
        return 0;
    }
    if (actual->kind == -2) {
        for (int64_t index = 0; index < actual->count; index++) {
            if (!lox_type_assignable(expected, &actual->items[index])) {
                return 0;
            }
        }
        return 1;
    }
    if (expected->kind == 6 && actual->kind == 6) {
        if (expected->count == actual->count) {
            return 1;
        }
        void *descriptor = lox_class_desc_for_id(actual->count);
        return descriptor != NULL && lox_class_id_matches(descriptor, expected->count);
    }
    if (expected->kind == -4 && actual->kind == 6) {
        void *descriptor = lox_class_desc_for_id(actual->count);
        return descriptor != NULL && lox_implements_interface(descriptor, expected->count);
    }
    if (expected->kind == -4 && actual->kind == -4) {
        return expected->count == actual->count;
    }
    if (expected->kind == 6 && actual->kind == -4) {
        return 0;
    }
    if (expected->kind == -5 && actual->kind == -5) {
        return lox_fn_assignable(actual->sig, expected->sig);
    }
    return lox_type_equal(expected, actual);
}

int lox_fn_assignable(const LoxFnSig *actual, const LoxFnSig *target) {
    if (actual == NULL || target == NULL) {
        return 0;
    }
    if (actual->variadic != target->variadic) {
        return 0;
    }
    int64_t count = target->n_params;
    if (actual->variadic) {
        if (actual->n_params != target->n_params) {
            return 0;
        }
    } else if (count != actual->n_params) {
        /* O alvo precisa passar todos os parâmetros; defaults só na chamada estática. */
        return 0;
    }
    for (int64_t index = 0; index < count; index++) {
        if (!lox_type_assignable(actual->params[index], target->params[index])) {
            return 0;
        }
    }
    if (!lox_type_assignable(target->ret, actual->ret)) {
        return 0;
    }
    for (int64_t index = 0; index < count; index++) {
        if (!lox_rep_equal(target->params[index], actual->params[index])) {
            return 0;
        }
    }
    return lox_rep_equal(target->ret, actual->ret);
}

LoxFnSig *lox_fn_sig_cached(const char *text) {
    LoxTypeDesc *desc = lox_type_parse_cached(text);
    return desc->kind == -5 ? desc->sig : NULL;
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
    if (type->kind == -4) {
        if (tag != 6) {
            return 0;
        }
        const void *instance = (const void *)payload;
        return lox_implements_interface(*(const void * const *)instance,
                                        type->count);
    }
    if (type->kind == -5) {
        if (tag != 7) {
            return 0;
        }
        const LoxClosure *closure = (const LoxClosure *)(intptr_t)payload;
        return lox_fn_assignable(closure->signature, type->sig);
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
