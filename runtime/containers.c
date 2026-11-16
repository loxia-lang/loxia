/* Range, List, Map, Tuple, Enum e igualdade estrutural (ADR-0007, ADR-0017,
 * ADR-0036, ADR-0041). */
#include "lox_runtime.h"


void *lox_range_new(int64_t start, int64_t end, int64_t step,
                    int32_t inclusive) {
    if (step == 0) {
        lox_panic(0, 0, "R1014", "range() step can't be zero.");
    }
    LoxRange *range = lox_alloc(sizeof(LoxRange));
    range->start = start;
    range->end = end;
    range->step = step;
    range->inclusive = inclusive != 0 ? 1 : 0;
    return range;
}

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

int32_t lox_range_equal(const void *left_pointer, const void *right_pointer) {
    const LoxRange *left = left_pointer;
    const LoxRange *right = right_pointer;
    return left->start == right->start && left->end == right->end &&
           left->step == right->step && left->inclusive == right->inclusive;
}

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

void *lox_str_from_range(const void *pointer) {
    const LoxRange *range = pointer;
    char buffer[128];
    int length;
    if (range->step == 1) {
        length = snprintf(buffer, sizeof buffer, "<range %" PRId64 "..%" PRId64 ">",
                          range->start, range->end);
    } else {
        length = snprintf(buffer, sizeof buffer,
                          "<range %" PRId64 "..%" PRId64 " step %" PRId64 ">",
                          range->start, range->end, range->step);
    }
    return string_from_ascii(buffer, (size_t)length);
}



void *lox_list_new(void) {
    LoxList *list = lox_alloc(sizeof(LoxList));
    list->count = 0;
    list->capacity = 4;
    list->items = lox_alloc(sizeof(LoxValue) * (size_t)list->capacity);
    list->version = 0;
    return list;
}

void lox_list_grow(LoxList *list) {
    int64_t capacity = list->capacity * 2;
    LoxValue *items = lox_alloc(sizeof(LoxValue) * (size_t)capacity);
    for (int64_t index = 0; index < list->count; index++) {
        items[index] = list->items[index];
    }
    list->items = items;
    list->capacity = capacity;
}

void lox_list_push(void *pointer, int64_t tag, int64_t payload) {
    LoxList *list = pointer;
    if (list->count == list->capacity) {
        lox_list_grow(list);
    }
    list->items[list->count].tag = tag;
    list->items[list->count].payload = payload;
    list->count += 1;
    list->version += 1;
}

int64_t lox_list_len(const void *pointer) {
    return ((const LoxList *)pointer)->count;
}

LoxValue lox_list_get(const void *pointer, int64_t index, int32_t line,
                      int32_t column) {
    const LoxList *list = pointer;
    if (index < 0 || index >= list->count) {
        lox_panic(line, column, "R1007", "List index out of bounds.");
    }
    return list->items[index];
}

void lox_list_set(void *pointer, int64_t index, int64_t tag, int64_t payload,
                  int32_t line, int32_t column) {
    LoxList *list = pointer;
    if (index < 0 || index >= list->count) {
        lox_panic(line, column, "R1007", "List index out of bounds.");
    }
    list->items[index].tag = tag;
    list->items[index].payload = payload;
    list->version += 1;
}

LoxValue lox_list_pop(void *pointer, int32_t line, int32_t column) {
    LoxList *list = pointer;
    if (list->count == 0) {
        lox_panic(line, column, "R1007", "Can't pop from an empty list.");
    }
    list->count -= 1;
    list->version += 1;
    return list->items[list->count];
}


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
        if (!lox_value_equal(left->items[index], right->items[index])) {
            return 0;
        }
    }
    return 1;
}

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
        default:
            return left.payload == right.payload;
    }
}



void *lox_map_new(void) {
    LoxMap *map = lox_alloc(sizeof(LoxMap));
    map->count = 0;
    map->capacity = 4;
    map->entries = lox_alloc(sizeof(LoxMapEntry) * (size_t)map->capacity);
    map->version = 0;
    return map;
}

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

int64_t lox_map_find(const LoxMap *map, LoxValue key) {
    for (int64_t index = 0; index < map->count; index++) {
        if (lox_map_key_equal(map->entries[index].key, key)) {
            return index;
        }
    }
    return -1;
}

void lox_map_grow(LoxMap *map) {
    int64_t capacity = map->capacity * 2;
    LoxMapEntry *entries = lox_alloc(sizeof(LoxMapEntry) * (size_t)capacity);
    for (int64_t index = 0; index < map->count; index++) {
        entries[index] = map->entries[index];
    }
    map->entries = entries;
    map->capacity = capacity;
}

/* ADR-0017: só String, Int e Bool são chaves; o interpretador é o oráculo. */
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
    map->count += 1;
    map->version += 1;
}

int64_t lox_map_len(const void *pointer) {
    return ((const LoxMap *)pointer)->count;
}

int32_t lox_map_has(const void *pointer, int64_t key_tag, int64_t key_payload,
                    int32_t line, int32_t column) {
    LoxValue key = {key_tag, key_payload};
    lox_map_check_key(key_tag, line, column);
    return lox_map_find(pointer, key) >= 0;
}

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
    return value;
}

LoxValue lox_map_key_at(const void *pointer, int64_t index) {
    return ((const LoxMap *)pointer)->entries[index].key;
}

void *lox_map_keys(const void *pointer) {
    const LoxMap *map = pointer;
    void *list = lox_list_new();
    for (int64_t index = 0; index < map->count; index++) {
        lox_list_push(list, map->entries[index].key.tag,
                      map->entries[index].key.payload);
    }
    return list;
}

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
    /* Guarda de ciclo: `depth` é compartilhada pela recursão; todo caminho que
       incrementa precisa decrementar antes de retornar. */
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



void *lox_tuple_new(int64_t count) {
    LoxTuple *tuple = lox_alloc(sizeof(LoxTuple));
    tuple->count = count;
    tuple->items = lox_alloc(sizeof(LoxValue) * (size_t)(count > 0 ? count : 1));
    return tuple;
}

void lox_tuple_set(void *pointer, int64_t index, int64_t tag, int64_t payload) {
    LoxTuple *tuple = pointer;
    tuple->items[index].tag = tag;
    tuple->items[index].payload = payload;
}

LoxValue lox_tuple_get(const void *pointer, int64_t index, int32_t line,
                       int32_t column) {
    const LoxTuple *tuple = pointer;
    if (index < 0 || index >= tuple->count) {
        lox_panic(line, column, "R1007", "Tuple index out of bounds.");
    }
    return tuple->items[index];
}

int64_t lox_tuple_len(const void *pointer) {
    return ((const LoxTuple *)pointer)->count;
}

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

int lox_any_equal(int64_t left_tag, int64_t left_payload, int64_t right_tag,
                  int64_t right_payload) {
    LoxValue left = {left_tag, left_payload};
    LoxValue right = {right_tag, right_payload};
    return lox_value_equal(left, right);
}

int lox_tuple_is2(const void *pointer, int64_t tag0, int64_t tag1) {
    const LoxTuple *tuple = pointer;
    if (tuple->count != 2) {
        return 0;
    }
    return tuple->items[0].tag == tag0 && tuple->items[1].tag == tag1;
}



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

void lox_enum_set(void *pointer, int64_t index, int64_t tag, int64_t payload) {
    LoxEnumValue *value = pointer;
    value->payload[index].tag = tag;
    value->payload[index].payload = payload;
}

LoxValue lox_enum_payload(const void *pointer, int64_t index, int32_t line,
                          int32_t column) {
    const LoxEnumValue *value = pointer;
    if (index < 0 || index >= value->count) {
        lox_panic(line, column, "R1007", "Enum payload index out of bounds.");
    }
    return value->payload[index];
}

int64_t lox_enum_variant(const void *pointer) {
    const LoxEnumValue *value = pointer;
    /* A variante é comparada pelo nome estável; o backend passa o índice. */
    return value->count >= 0 ? (int64_t)0 : (int64_t)0;
}

int64_t lox_enum_variant_index(const void *pointer, const char *name) {
    const LoxEnumValue *value = pointer;
    return strcmp(value->variant_name, name) == 0 ? 1 : 0;
}

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
