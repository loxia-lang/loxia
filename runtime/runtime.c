/*
 * Runtime do backend nativo do Lox.
 *
 * Só entra aqui o que o IR gerado não deve carregar: I/O, formatação e os casos de
 * borda da aritmética (divisão por zero e o INT_MIN / -1, que é UB em C e em LLVM).
 *
 * Contrato: `lox_panic` reproduz o diagnóstico do interpretador (stderr e exit 70),
 * `lox_print_*` reproduzem `stringify` + `print` (valor e '\n').
 */

#include <inttypes.h>
#include <locale.h>
#include <setjmp.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * I3: a conversão de/para texto de `double` não pode depender do locale do processo.
 * `snprintf`/`strtod` usam LC_NUMERIC; o binário fixa em "C" no início.
 */
void lox_init(void) {
    setlocale(LC_NUMERIC, "C");
}

/*
 * String imutável: bytes UTF-8 + contagem de code points (ADR-0031, decisão 6).
 * O IR usa `i8*` para o ponteiro; o layout é este struct.
 */
typedef struct {
    int64_t byte_len;
    int64_t cp_len;
    const char *data;
} LoxStr;

static LoxStr *string_from_ascii(const char *data, size_t length);
void lox_panic(int32_t line, const char *message);

/* Arena: um bloco, sem free, com teto determinístico (decisão 7). */
#define LOX_HEAP_BYTES (64ull * 1024ull * 1024ull)

static unsigned char *lox_heap = NULL;
static size_t lox_heap_used = 0;

static void *lox_alloc(size_t size) {
    if (lox_heap == NULL) {
        lox_heap = malloc(LOX_HEAP_BYTES);
        if (lox_heap == NULL) {
            lox_panic(0, "Out of memory.");
        }
    }
    size = (size + 7u) & ~(size_t)7u;
    if (lox_heap_used + size > LOX_HEAP_BYTES) {
        lox_panic(0, "Out of memory.");
    }
    void *pointer = lox_heap + lox_heap_used;
    lox_heap_used += size;
    return pointer;
}

/*
 * Closure do L4 (ADR-0046): `{ fnptr, env, display }`. O IR aloca via estes wrappers;
 * `display` é uma string C determinística (`<fn f>`/`<lambda>`), nunca um endereço.
 */
typedef struct {
    void *fn;
    void *env;
    const char *display;
} LoxClosure;

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

int lox_is_instance(void *descriptor, void *target) {
    while (descriptor != NULL) {
        if (descriptor == target) {
            return 1;
        }
        descriptor = *(void **)descriptor;
    }
    return 0;
}

void lox_print_function(const void *pointer) {
    const LoxClosure *closure = pointer;
    fputs(closure->display, stdout);
    fputc('\n', stdout);
}

void *lox_str_from_function(const void *pointer) {
    const LoxClosure *closure = pointer;
    const char *display = closure->display;
    size_t length = strlen(display);

    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *data = (char *)(result + 1);
    memcpy(data, display, length + 1);

    result->byte_len = (int64_t)length;
    result->cp_len = (int64_t)length;
    result->data = data;
    return result;
}

void lox_print_str(const void *pointer) {
    const LoxStr *string = pointer;
    fwrite(string->data, 1, (size_t)string->byte_len, stdout);
    fputc('\n', stdout);
}

int64_t lox_str_len(const void *pointer) {
    return ((const LoxStr *)pointer)->cp_len;
}

int32_t lox_str_compare(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    size_t shared = (size_t)(left->byte_len < right->byte_len ? left->byte_len
                                                               : right->byte_len);
    int result = memcmp(left->data, right->data, shared);
    if (result != 0) {
        return result < 0 ? -1 : 1;
    }
    if (left->byte_len == right->byte_len) {
        return 0;
    }
    return left->byte_len < right->byte_len ? -1 : 1;
}

int32_t lox_str_equal(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    if (left->byte_len != right->byte_len) {
        return 0;
    }
    return memcmp(left->data, right->data, (size_t)left->byte_len) == 0;
}

void *lox_str_concat(const void *left_pointer, const void *right_pointer) {
    const LoxStr *left = left_pointer;
    const LoxStr *right = right_pointer;
    size_t bytes = (size_t)left->byte_len + (size_t)right->byte_len;

    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes + 1);
    char *data = (char *)(result + 1);
    memcpy(data, left->data, (size_t)left->byte_len);
    memcpy(data + left->byte_len, right->data, (size_t)right->byte_len);
    data[bytes] = '\0';

    result->byte_len = (int64_t)bytes;
    result->cp_len = left->cp_len + right->cp_len;
    result->data = data;
    return result;
}


/* Range do L6: valor imutável, ponteiro para `{start, end, step}`. */
typedef struct {
    int64_t start;
    int64_t end;
    int64_t step;
} LoxRange;

void *lox_range_new(int64_t start, int64_t end, int64_t step) {
    if (step == 0) {
        lox_panic(0, "range() step can't be zero.");
    }
    LoxRange *range = lox_alloc(sizeof(LoxRange));
    range->start = start;
    range->end = end;
    range->step = step;
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

int32_t lox_range_equal(const void *left_pointer, const void *right_pointer) {
    const LoxRange *left = left_pointer;
    const LoxRange *right = right_pointer;
    return left->start == right->start && left->end == right->end &&
           left->step == right->step;
}

void lox_print_range(const void *pointer) {
    const LoxRange *range = pointer;
    if (range->step == 1) {
        printf("<range %" PRId64 "..%" PRId64 ">\n", range->start,
               range->end);
    } else {
        printf("<range %" PRId64 "..%" PRId64 " step %" PRId64 ">\n",
               range->start, range->end, range->step);
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


/* List do L6: elementos boxeados `LoxValue{tag,payload}`, ordem de inserção. */
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

void *lox_list_new(void) {
    LoxList *list = lox_alloc(sizeof(LoxList));
    list->count = 0;
    list->capacity = 4;
    list->items = lox_alloc(sizeof(LoxValue) * (size_t)list->capacity);
    list->version = 0;
    return list;
}

static void lox_list_grow(LoxList *list) {
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

LoxValue lox_list_get(const void *pointer, int64_t index, int32_t line) {
    const LoxList *list = pointer;
    if (index < 0 || index >= list->count) {
        lox_panic(line, "List index out of bounds.");
    }
    return list->items[index];
}

void lox_list_set(void *pointer, int64_t index, int64_t tag, int64_t payload,
                  int32_t line) {
    LoxList *list = pointer;
    if (index < 0 || index >= list->count) {
        lox_panic(line, "List index out of bounds.");
    }
    list->items[index].tag = tag;
    list->items[index].payload = payload;
    list->version += 1;
}

LoxValue lox_list_pop(void *pointer, int32_t line) {
    LoxList *list = pointer;
    if (list->count == 0) {
        lox_panic(line, "Can't pop from an empty list.");
    }
    list->count -= 1;
    list->version += 1;
    return list->items[list->count];
}

static int lox_value_equal(LoxValue left, LoxValue right);
int lox_map_equal(const void *left_pointer, const void *right_pointer);
int lox_tuple_equal(const void *left_pointer, const void *right_pointer);
int lox_enum_equal(const void *left_pointer, const void *right_pointer);

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

static int lox_value_equal(LoxValue left, LoxValue right) {
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


/* Map do L6: entradas boxeadas em ordem de inserção. */
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

void *lox_map_new(void) {
    LoxMap *map = lox_alloc(sizeof(LoxMap));
    map->count = 0;
    map->capacity = 4;
    map->entries = lox_alloc(sizeof(LoxMapEntry) * (size_t)map->capacity);
    map->version = 0;
    return map;
}

static int lox_map_key_equal(LoxValue left, LoxValue right) {
    if (left.tag != right.tag) {
        return 0;
    }
    if (left.tag == 4) {
        return lox_str_equal((const void *)left.payload,
                             (const void *)right.payload);
    }
    return left.payload == right.payload;
}

static int64_t lox_map_find(const LoxMap *map, LoxValue key) {
    for (int64_t index = 0; index < map->count; index++) {
        if (lox_map_key_equal(map->entries[index].key, key)) {
            return index;
        }
    }
    return -1;
}

static void lox_map_grow(LoxMap *map) {
    int64_t capacity = map->capacity * 2;
    LoxMapEntry *entries = lox_alloc(sizeof(LoxMapEntry) * (size_t)capacity);
    for (int64_t index = 0; index < map->count; index++) {
        entries[index] = map->entries[index];
    }
    map->entries = entries;
    map->capacity = capacity;
}

void lox_map_set(void *pointer, int64_t key_tag, int64_t key_payload,
                 int64_t value_tag, int64_t value_payload) {
    LoxMap *map = pointer;
    LoxValue key = {key_tag, key_payload};
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

int32_t lox_map_has(const void *pointer, int64_t key_tag, int64_t key_payload) {
    LoxValue key = {key_tag, key_payload};
    return lox_map_find(pointer, key) >= 0;
}

LoxValue lox_map_get(const void *pointer, int64_t key_tag, int64_t key_payload) {
    LoxValue key = {key_tag, key_payload};
    int64_t found = lox_map_find(pointer, key);
    if (found < 0) {
        LoxValue nil = {0, 0};
        return nil;
    }
    return ((const LoxMap *)pointer)->entries[found].value;
}

LoxValue lox_map_get_checked(const void *pointer, int64_t key_tag,
                             int64_t key_payload, int32_t line) {
    LoxValue key = {key_tag, key_payload};
    int64_t found = lox_map_find(pointer, key);
    if (found < 0) {
        lox_panic(line, "Key not found in map.");
    }
    return ((const LoxMap *)pointer)->entries[found].value;
}

LoxValue lox_map_remove(void *pointer, int64_t key_tag, int64_t key_payload,
                        int32_t line) {
    LoxMap *map = pointer;
    LoxValue key = {key_tag, key_payload};
    int64_t found = lox_map_find(map, key);
    if (found < 0) {
        lox_panic(line, "Key not found in map.");
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
    if (left->count != right->count) {
        return 0;
    }
    for (int64_t index = 0; index < left->count; index++) {
        LoxValue key = left->entries[index].key;
        int64_t found = lox_map_find(right, key);
        if (found < 0 || !lox_value_equal(left->entries[index].value,
                                           right->entries[found].value)) {
            depth -= 1;
            return 0;
        }
    }
    depth -= 1;
    return 1;
}


/* Tupla do L6: elementos boxeados, aridade fixa e imutável. */
typedef struct {
    int64_t count;
    LoxValue *items;
} LoxTuple;

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

LoxValue lox_tuple_get(const void *pointer, int64_t index, int32_t line) {
    const LoxTuple *tuple = pointer;
    if (index < 0 || index >= tuple->count) {
        lox_panic(line, "Tuple index out of bounds.");
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

void *lox_str_char_at(const void *pointer, int64_t index);

void *lox_chars(const void *pointer) {
    const LoxStr *string = pointer;
    void *list = lox_list_new();
    for (int64_t index = 0; index < string->cp_len; index++) {
        void *character = lox_str_char_at(string, index);
        lox_list_push(list, 4, (int64_t)character);
    }
    return list;
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


int64_t lox_float_to_int(double value, int32_t line);

int64_t lox_math_abs_int(int64_t value) {
    return value < 0 ? (int64_t)(0u - (uint64_t)value) : value;
}

double lox_math_abs_float(double value) {
    return fabs(value);
}

double lox_math_sqrt(double value) {
    return sqrt(value);
}

int64_t lox_math_floor(double value, int32_t line) {
    return lox_float_to_int(floor(value), line);
}

int64_t lox_math_ceil(double value, int32_t line) {
    return lox_float_to_int(ceil(value), line);
}

int64_t lox_math_round(double value, int32_t line) {
    return lox_float_to_int(round(value), line);
}

int64_t lox_math_trunc(double value, int32_t line) {
    return lox_float_to_int(trunc(value), line);
}

LoxValue lox_parse_int(const void *pointer) {
    const LoxStr *string = pointer;
    const char *data = string->data;
    size_t size = (size_t)string->byte_len;
    LoxValue nil = {0, 0};
    if (size == 0) {
        return nil;
    }
    size_t index = 0;
    int negative = 0;
    if (data[index] == '+' || data[index] == '-') {
        negative = data[index] == '-';
        index += 1;
    }
    if (index == size) {
        return nil;
    }
    uint64_t value = 0;
    for (; index < size; index++) {
        char byte = data[index];
        if (byte < '0' || byte > '9') {
            return nil;
        }
        unsigned digit = (unsigned)(byte - '0');
        if (value > (UINT64_MAX - digit) / 10u) {
            return nil;
        }
        value = value * 10u + digit;
    }
    if ((!negative && value > (uint64_t)INT64_MAX) ||
        (negative && value > (uint64_t)INT64_MAX + 1u)) {
        return nil;
    }
    int64_t result = negative ? (int64_t)(0u - value) : (int64_t)value;
    LoxValue some = {1, result};
    return some;
}

LoxValue lox_parse_float(const void *pointer) {
    const LoxStr *string = pointer;
    LoxValue nil = {0, 0};
    size_t size = (size_t)string->byte_len;
    if (size == 0) {
        return nil;
    }
    char *copy = lox_alloc(size + 1);
    memcpy(copy, string->data, size);
    copy[size] = '\0';
    char *end = NULL;
    double value = strtod(copy, &end);
    if (end != copy + size || !isfinite(value)) {
        return nil;
    }
    LoxValue some;
    some.tag = 2;
    memcpy(&some.payload, &value, sizeof(value));
    return some;
}


/* Enum do L6: identidade + variante + payload boxeado. */
typedef struct {
    int64_t enum_id;
    const char *enum_name;
    const char *variant_name;
    int64_t count;
    LoxValue *payload;
} LoxEnumValue;

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

LoxValue lox_enum_payload(const void *pointer, int64_t index, int32_t line) {
    const LoxEnumValue *value = pointer;
    if (index < 0 || index >= value->count) {
        lox_panic(line, "Enum payload index out of bounds.");
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

/* `chars(s)[i]`: i é índice em code points, não em bytes. */
void *lox_str_char_at(const void *pointer, int64_t index) {
    const LoxStr *string = pointer;
    if (index < 0 || index >= string->cp_len) {
        lox_panic(0, "String index out of bounds.");
    }
    const unsigned char *data = (const unsigned char *)string->data;
    size_t offset = 0;
    for (int64_t position = 0; position < index; position++) {
        unsigned char byte = data[offset];
        if (byte < 0x80) {
            offset += 1;
        } else if ((byte & 0xE0) == 0xC0) {
            offset += 2;
        } else if ((byte & 0xF0) == 0xE0) {
            offset += 3;
        } else {
            offset += 4;
        }
    }
    unsigned char byte = data[offset];
    size_t length = byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                     : (byte & 0xF0) == 0xE0 ? 3
                                             : 4;
    return string_from_ascii((const char *)data + offset, length);
}


int64_t lox_int_pow(int64_t base, int64_t exponent, int32_t line) {
    if (exponent < 0) {
        lox_panic(line, "Negative exponent not allowed for integer power.");
    }
    uint64_t power = (uint64_t)exponent;
    uint64_t result = 1;
    uint64_t factor = (uint64_t)base;
    while (power != 0) {
        if (power & 1u) {
            result *= factor;
        }
        power >>= 1u;
        if (power != 0) {
            factor *= factor;
        }
    }
    return (int64_t)result;
}

int64_t lox_shift(int64_t value, int64_t count, int32_t kind, int32_t line) {
    if (count < 0 || count > 63) {
        lox_panic(line, "Shift count must be between 0 and 63.");
    }
    if (kind == 0) {
        return (int64_t)((uint64_t)value << (uint64_t)count);
    }
    if (kind == 1) {
        return value >> (uint64_t)count;
    }
    return (int64_t)((uint64_t)value >> (uint64_t)count);
}

int64_t lox_float_to_int(double value, int32_t line) {
    if (isnan(value) || isinf(value) || value < -9223372036854775808.0 ||
        value >= 9223372036854775808.0) {
        lox_panic(line, "Can't cast value to Int.");
    }
    return (int64_t)value;
}


/* Exceções do L6j: frames de try, throw e cleanup mínimo (ADR-0062). */
typedef struct {
    const char *type_name;
    void *instance;
    const char *message;
    int32_t line;
} LoxException;

typedef struct LoxTryFrame {
    jmp_buf env;
    struct LoxTryFrame *previous;
    LoxException exception;
    int32_t active;
} LoxTryFrame;

static LoxTryFrame *lox_current_try = NULL;

void *lox_try_push(void) {
    LoxTryFrame *frame = lox_alloc(sizeof(LoxTryFrame));
    frame->previous = lox_current_try;
    frame->active = 1;
    frame->exception.type_name = NULL;
    frame->exception.instance = NULL;
    frame->exception.message = NULL;
    frame->exception.line = 0;
    lox_current_try = frame;
    return frame;
}

void *lox_try_buffer(void *pointer) {
    return &((LoxTryFrame *)pointer)->env;
}

void lox_try_pop(void *pointer) {
    LoxTryFrame *frame = pointer;
    frame->active = 0;
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

int32_t lox_exception_matches(const void *pointer, const char *type_name) {
    const LoxException *exception = pointer;
    if (exception->instance != NULL) {
        void *descriptor = *(void **)exception->instance;
        while (descriptor != NULL) {
            const LoxStr *name = ((const LoxStr **)descriptor)[2];
            size_t length = strlen(type_name);
            if (name->byte_len == (int64_t)length &&
                memcmp(name->data, type_name, length) == 0) {
                return 1;
            }
            descriptor = *(void **)descriptor;
        }
        return 0;
    }
    if (exception->type_name == NULL) {
        return 0;
    }
    if (strcmp(exception->type_name, type_name) == 0) {
        return 1;
    }
    return strcmp(type_name, "Exception") == 0;
}

void lox_throw(void *instance, const char *type_name, const char *message,
               int32_t line) {
    LoxTryFrame *frame = lox_current_try;
    if (frame == NULL) {
        fflush(stdout);
        fprintf(stderr, "Unhandled exception: %s\n[line %" PRId32 "]\n",
                message != NULL ? message : type_name, line);
        fflush(stderr);
        exit(70);
    }
    frame->exception.type_name = type_name;
    frame->exception.instance = instance;
    frame->exception.message = message;
    frame->exception.line = line;
    longjmp(frame->env, 1);
}

void lox_rethrow(void *exception_pointer, int32_t line) {
    LoxException *exception = exception_pointer;
    lox_throw(exception->instance, exception->type_name, exception->message, line);
}

void lox_raise_current(int32_t line) {
    LoxTryFrame *frame = lox_current_try;
    if (frame == NULL) {
        lox_panic(line, "No exception to re-raise.");
    }
    lox_throw(frame->exception.instance, frame->exception.type_name,
              frame->exception.message, line);
}

void lox_panic(int32_t line, const char *message) {
    if (lox_current_try != NULL) {
        lox_throw(NULL, "LoxRuntimeError", message, line);
    }
    fflush(stdout);
    fprintf(stderr, "%s\n[line %" PRId32 "]\n", message, line);
    fflush(stderr);
    exit(70);
}

void lox_print_int(int64_t value) {
    printf("%" PRId64 "\n", value);
}

void lox_print_bool(int32_t value) {
    fputs(value ? "true\n" : "false\n", stdout);
}

void lox_print_nil(void) {
    fputs("nil\n", stdout);
}

/*
 * Formata `double` como o `repr` do Python: menor quantidade de dígitos que reconstrói
 * o mesmo bit pattern, com as convenções do CPython (`1.0`, `-0.0`, `1e-05`, `1e+16`).
 *
 * Estratégia: tenta `%.{p}e` para p = 1..17 e usa o primeiro que `strtod` reconstrói.
 * É O(17) conversões, não um algoritmo de shortest-repr dedicado (Ryu); para o L1 a
 * diferença é de microssegundos por print impresso. O contrato é validado por fuzz
 * contra `repr` em `tests/test_backend.py`.
 */
static void format_double(double value, char *out, size_t size) {
    if (value == 0.0) {
        snprintf(out, size, "%s0.0", signbit(value) ? "-" : "");
        return;
    }

    char scientific[64];
    int precision;
    for (precision = 1; precision <= 17; precision++) {
        snprintf(scientific, sizeof scientific, "%.*e", precision - 1, value);
        if (strtod(scientific, NULL) == value) {
            break;
        }
    }

    const char *cursor = scientific;
    int negative = 0;
    if (*cursor == '-') {
        negative = 1;
        cursor++;
    }

    char digits[32];
    size_t count = 0;
    digits[count++] = *cursor++;
    if (*cursor == '.') {
        cursor++;
        while (*cursor >= '0' && *cursor <= '9' && count < sizeof digits - 1) {
            digits[count++] = *cursor++;
        }
    }
    while (count > 1 && digits[count - 1] == '0') {
        count--;
    }
    digits[count] = '\0';

    int exponent = 0;
    if (*cursor == 'e' || *cursor == 'E') {
        exponent = atoi(cursor + 1);
    }

    int decpt = exponent + 1;
    char *write = out;
    size_t remaining = size;
    if (negative) {
        *write++ = '-';
        remaining--;
    }

    if (decpt <= -4 || decpt > 16) {
        snprintf(write, remaining, "%c%s%s%c%+03d", digits[0], count > 1 ? "." : "",
                 count > 1 ? digits + 1 : "", 'e', decpt - 1);
        return;
    }

    size_t used = 0;
    if (decpt <= 0) {
        /* 0.000ddd: `decpt` zeros antes dos dígitos. */
        if (used + 2 < remaining) {
            write[used++] = '0';
            write[used++] = '.';
        }
        for (int index = 0; index < -decpt && used + 1 < remaining; index++) {
            write[used++] = '0';
        }
        for (size_t index = 0; index < count && used + 1 < remaining; index++) {
            write[used++] = digits[index];
        }
    } else if ((size_t)decpt >= count) {
        /* ddd000.0: dígitos e zeros até a casa decimal. */
        size_t index;
        for (index = 0; index < count && used + 1 < remaining; index++) {
            write[used++] = digits[index];
        }
        for (; index < (size_t)decpt && used + 1 < remaining; index++) {
            write[used++] = '0';
        }
        if (used + 2 < remaining) {
            write[used++] = '.';
            write[used++] = '0';
        }
    } else {
        /* dd.ddd: ponto decimal no meio dos dígitos. */
        for (size_t index = 0; index < (size_t)decpt && used + 1 < remaining;
             index++) {
            write[used++] = digits[index];
        }
        if (used + 1 < remaining) {
            write[used++] = '.';
        }
        for (size_t index = (size_t)decpt; index < count && used + 1 < remaining;
             index++) {
            write[used++] = digits[index];
        }
    }
    write[used] = '\0';
}

static void format_float_value(double value, char *out, size_t size) {
    if (isnan(value)) {
        snprintf(out, size, "NaN");
        return;
    }
    if (isinf(value)) {
        snprintf(out, size, value < 0 ? "-inf" : "inf");
        return;
    }
    format_double(value, out, size);
}

void lox_print_float(double value) {
    char buffer[64];
    format_float_value(value, buffer, sizeof buffer);
    fputs(buffer, stdout);
    fputc('\n', stdout);
}

/* Aloca uma LoxStr ASCII (números, booleanos, "nil") dentro da arena. */
static LoxStr *string_from_ascii(const char *data, size_t length) {
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *copy = (char *)(result + 1);
    memcpy(copy, data, length);
    copy[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = (int64_t)length;
    result->data = copy;
    return result;
}

void *lox_str_from_int(int64_t value) {
    char buffer[32];
    int length = snprintf(buffer, sizeof buffer, "%" PRId64, value);
    return string_from_ascii(buffer, (size_t)length);
}

void *lox_str_from_double(double value) {
    char buffer[64];
    format_float_value(value, buffer, sizeof buffer);
    return string_from_ascii(buffer, strlen(buffer));
}

void *lox_str_from_bool(int32_t value) {
    return value ? string_from_ascii("true", 4)
                 : string_from_ascii("false", 5);
}

void *lox_str_nil(void) {
    return string_from_ascii("nil", 3);
}

/* `repr` de string: aspas + escapes, como `values._quote` do interpretador. */
void *lox_str_quote(const void *pointer) {
    const LoxStr *source = pointer;
    size_t bytes = (size_t)source->byte_len;

    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes * 2 + 3);
    char *data = (char *)(result + 1);
    size_t used = 0;
    data[used++] = '"';

    for (size_t index = 0; index < bytes; index++) {
        char byte = source->data[index];
        switch (byte) {
            case '\\':
                data[used++] = '\\';
                data[used++] = '\\';
                break;
            case '"':
                data[used++] = '\\';
                data[used++] = '"';
                break;
            case '\n':
                data[used++] = '\\';
                data[used++] = 'n';
                break;
            case '\r':
                data[used++] = '\\';
                data[used++] = 'r';
                break;
            case '\t':
                data[used++] = '\\';
                data[used++] = 't';
                break;
            case '\0':
                data[used++] = '\\';
                data[used++] = '0';
                break;
            default:
                data[used++] = byte;
                break;
        }
    }

    data[used++] = '"';
    data[used] = '\0';

    result->byte_len = (int64_t)used;
    result->cp_len = source->cp_len + 2;
    result->data = data;
    return result;
}


typedef struct {
    char *data;
    size_t length;
    size_t capacity;
    const void *active[64];
    int active_depth;
} LoxBuffer;

static void buffer_init(LoxBuffer *buffer) {
    buffer->capacity = 64;
    buffer->data = lox_alloc(buffer->capacity);
    buffer->length = 0;
    buffer->active_depth = 0;
}

static void buffer_need(LoxBuffer *buffer, size_t extra) {
    if (buffer->length + extra <= buffer->capacity) {
        return;
    }
    size_t capacity = buffer->capacity;
    while (capacity < buffer->length + extra) {
        capacity *= 2;
    }
    char *data = lox_alloc(capacity);
    memcpy(data, buffer->data, buffer->length);
    buffer->data = data;
    buffer->capacity = capacity;
}

static void buffer_char(LoxBuffer *buffer, char byte) {
    buffer_need(buffer, 1);
    buffer->data[buffer->length++] = byte;
}

static void buffer_text(LoxBuffer *buffer, const char *text) {
    size_t length = strlen(text);
    buffer_need(buffer, length);
    memcpy(buffer->data + buffer->length, text, length);
    buffer->length += length;
}

static void buffer_bytes(LoxBuffer *buffer, const char *data, size_t length) {
    buffer_need(buffer, length);
    memcpy(buffer->data + buffer->length, data, length);
    buffer->length += length;
}

static void format_value(LoxBuffer *buffer, LoxValue value);

static void format_enum(LoxBuffer *buffer, const LoxEnumValue *value) {
    buffer_text(buffer, value->enum_name);
    buffer_char(buffer, '.');
    buffer_text(buffer, value->variant_name);
    if (value->count > 0) {
        buffer_char(buffer, '(');
        for (int64_t index = 0; index < value->count; index++) {
            if (index > 0) {
                buffer_text(buffer, ", ");
            }
            format_value(buffer, value->payload[index]);
        }
        buffer_char(buffer, ')');
    }
}

static void format_tuple(LoxBuffer *buffer, const LoxTuple *tuple) {
    buffer_char(buffer, '(');
    for (int64_t index = 0; index < tuple->count; index++) {
        if (index > 0) {
            buffer_text(buffer, ", ");
        }
        format_value(buffer, tuple->items[index]);
    }
    buffer_char(buffer, ')');
}

static void format_map(LoxBuffer *buffer, const LoxMap *map) {
    for (int index = 0; index < buffer->active_depth; index++) {
        if (buffer->active[index] == map) {
            buffer_text(buffer, "{...}");
            return;
        }
    }
    if (buffer->active_depth >= 64) {
        buffer_text(buffer, "{...}");
        return;
    }
    buffer->active[buffer->active_depth++] = map;
    buffer_char(buffer, '{');
    for (int64_t index = 0; index < map->count; index++) {
        if (index > 0) {
            buffer_text(buffer, ", ");
        }
        format_value(buffer, map->entries[index].key);
        buffer_text(buffer, ": ");
        format_value(buffer, map->entries[index].value);
    }
    buffer_char(buffer, '}');
    buffer->active_depth -= 1;
}

static void format_list(LoxBuffer *buffer, const LoxList *list) {
    for (int index = 0; index < buffer->active_depth; index++) {
        if (buffer->active[index] == list) {
            buffer_text(buffer, "[...]");
            return;
        }
    }
    if (buffer->active_depth >= 64) {
        buffer_text(buffer, "[...]");
        return;
    }
    buffer->active[buffer->active_depth++] = list;
    buffer_char(buffer, '[');
    for (int64_t index = 0; index < list->count; index++) {
        if (index > 0) {
            buffer_text(buffer, ", ");
        }
        format_value(buffer, list->items[index]);
    }
    buffer_char(buffer, ']');
    buffer->active_depth -= 1;
}

static void format_value(LoxBuffer *buffer, LoxValue value) {
    switch (value.tag) {
        case 0:
            buffer_text(buffer, "nil");
            break;
        case 1: {
            char text[32];
            int length = snprintf(text, sizeof text, "%" PRId64, value.payload);
            buffer_bytes(buffer, text, (size_t)length);
            break;
        }
        case 2: {
            double number;
            memcpy(&number, &value.payload, sizeof(number));
            char text[64];
            format_float_value(number, text, sizeof text);
            buffer_text(buffer, text);
            break;
        }
        case 3:
            buffer_text(buffer, value.payload ? "true" : "false");
            break;
        case 4: {
            void *quoted = lox_str_quote((const void *)value.payload);
            const LoxStr *string = quoted;
            buffer_bytes(buffer, string->data, (size_t)string->byte_len);
            break;
        }
        case 5: {
            void *descriptor = (void *)value.payload;
            const LoxStr *name = ((void **)descriptor)[2];
            buffer_bytes(buffer, name->data, (size_t)name->byte_len);
            break;
        }
        case 6: {
            void *instance = (void *)value.payload;
            void *descriptor = ((void **)instance)[0];
            const LoxStr *name = ((void **)descriptor)[2];
            buffer_bytes(buffer, name->data, (size_t)name->byte_len);
            buffer_text(buffer, " instance");
            break;
        }
        case 7:
            buffer_text(buffer, "<fn>");
            break;
        case 8: {
            const LoxRange *range = (const void *)value.payload;
            char text[128];
            int length;
            if (range->step == 1) {
                length = snprintf(text, sizeof text,
                                  "<range %" PRId64 "..%" PRId64 ">",
                                  range->start, range->end);
            } else {
                length = snprintf(
                    text, sizeof text,
                    "<range %" PRId64 "..%" PRId64 " step %" PRId64 ">",
                    range->start, range->end, range->step);
            }
            buffer_bytes(buffer, text, (size_t)length);
            break;
        }
        case 9:
            format_list(buffer, (const void *)value.payload);
            break;
        case 10:
            format_map(buffer, (const void *)value.payload);
            break;
        case 11:
            format_tuple(buffer, (const void *)value.payload);
            break;
        case 12:
            format_enum(buffer, (const void *)value.payload);
            break;
        default:
            buffer_text(buffer, "<value>");
            break;
    }
}

void lox_print_list(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_list(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

void lox_print_map(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_map(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

void lox_print_enum(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_enum(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

void *lox_str_from_enum(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_enum(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

void lox_print_tuple(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_tuple(&buffer, pointer);
    fwrite(buffer.data, 1, buffer.length, stdout);
    fputc('\n', stdout);
}

void *lox_str_from_tuple(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_tuple(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

void *lox_str_from_map(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_map(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

void *lox_str_from_list(const void *pointer) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    format_list(&buffer, pointer);
    return string_from_ascii(buffer.data, buffer.length);
}

/*
 * `//`: divisão inteira truncada em direção a zero, com wrapping de i64 em release
 * (ADR-0028). O interpretador devolve INT_MIN para INT_MIN // -1; em C e em LLVM isso
 * é UB, então o caso é resolvido explicitamente.
 */
int64_t lox_int_div(int64_t left, int64_t right, int32_t line) {
    if (right == 0) {
        lox_panic(line, "Division by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        return INT64_MIN;
    }
    return left / right;
}

/* `/`: sempre Float. Divisão por zero é erro fatal, como no interpretador. */
double lox_float_div(double left, double right, int32_t line) {
    if (right == 0.0) {
        lox_panic(line, "Division by zero not allowed");
    }
    return left / right;
}

/* `%` com Float: `fmod`, sinal do dividendo, e zero é erro (como no interpretador). */
double lox_float_mod(double left, double right, int32_t line) {
    if (right == 0.0) {
        lox_panic(line, "Modulo by zero not allowed");
    }
    return fmod(left, right);
}

/* `%`: resto truncado (sinal do dividendo), como `srem`. INT_MIN % -1 é 0. */
int64_t lox_int_mod(int64_t left, int64_t right, int32_t line) {
    if (right == 0) {
        lox_panic(line, "Modulo by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        return 0;
    }
    return left % right;
}

/* Impressão de valor boxeado `Any` (spike L6): tag + payload de 64 bits. */
void lox_print_any(int64_t tag, int64_t payload) {
    switch (tag) {
        case 0:
            lox_print_nil();
            break;
        case 1:
            lox_print_int(payload);
            break;
        case 2: {
            double value;
            memcpy(&value, &payload, sizeof(value));
            lox_print_float(value);
            break;
        }
        case 3:
            lox_print_bool(payload != 0);
            break;
        case 4:
            lox_print_str((const void *)payload);
            break;
        case 5: {
            void *descriptor = (void *)payload;
            void *name = ((void **)descriptor)[2];
            lox_print_str(name);
            fputc('\n', stdout);
            break;
        }
        case 6: {
            void *instance = (void *)payload;
            void *descriptor = ((void **)instance)[0];
            void *name = ((void **)descriptor)[2];
            lox_print_str(name);
            fputs(" instance\n", stdout);
            break;
        }
        case 7:
            printf("%s\n", (const char *)payload);
            break;
        case 8:
            lox_print_range((const void *)payload);
            break;
        case 9:
            lox_print_list((const void *)payload);
            break;
        case 10:
            lox_print_map((const void *)payload);
            break;
        case 11:
            lox_print_tuple((const void *)payload);
            break;
        case 12:
            lox_print_enum((const void *)payload);
            break;
        default:
            lox_panic(0, "Unknown Any tag");
    }
}
