/*
 * Runtime do backend nativo do Lox.
 *
 * Só entra aqui o que o IR gerado não deve carregar: I/O, formatação e os casos de
 * borda da aritmética (divisão por zero e o INT_MIN / -1, que é UB em C e em LLVM).
 *
 * Contrato: `lox_panic` reproduz o diagnóstico do interpretador (stderr e exit 70),
 * `lox_print_*` reproduzem `stringify` + `print` (valor e '\n').
 */

#define _POSIX_C_SOURCE 200809L

#include <gc.h>
#include <dirent.h>
#include <inttypes.h>
#include <locale.h>
#include <setjmp.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

/* Hard cap do heap coletado (ADR-0074); não é configurável por ambiente. */
#define LOX_GC_MAX_HEAP_BYTES (128ull * 1024ull * 1024ull)

static void *lox_oom(size_t size);

/*
 * I3: a conversão de/para texto de `double` não pode depender do locale do processo.
 * `snprintf`/`strtod` usam LC_NUMERIC; o binário fixa em "C" no início.
 *
 * O bootstrap do GC fica aqui porque o `main` gerado chama `lox_init` antes de
 * qualquer código Lox. O Boehm descobre o topo da pilha do SO; os testes de roots
 * cobrem temporários de topo.
 */
static const char *lox_source_path = "<lox>";
static int32_t lox_argc = 0;
static char **lox_argv = NULL;

void lox_init(const char *source_path, int32_t argc, char **argv) {
    lox_source_path = source_path;
    lox_argc = argc;
    lox_argv = argv;
    setlocale(LC_NUMERIC, "C");
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
typedef struct {
    int64_t byte_len;
    int64_t cp_len;
    const char *data;
    int32_t *cp_offsets; /* cache preguiçoso; NULL até o primeiro acesso aleatório */
} LoxStr;

static LoxStr *string_from_ascii(const char *data, size_t length);
static LoxStr *string_from_bytes(const char *data, size_t length,
                                 int64_t code_points);
void lox_panic(int32_t line, int32_t column, const char *code,
               const char *message);

/* Heap coletado (ADR-0074): o Boehm é o único alocador; sem free manual. */
static void *lox_oom(size_t size) {
    (void)size;
    lox_panic(0, 0, "R1000", "Out of memory.");
    return NULL;
}

static void *lox_alloc(size_t size) {
    void *pointer = GC_MALLOC(size > 0 ? size : 1u);
    if (pointer == NULL) {
        lox_panic(0, 0, "R1000", "Out of memory.");
    }
    return pointer;
}

/* Bloco sem ponteiros (bytes de string, buffers de formatação). */
static void *lox_alloc_atomic(size_t size) {
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

/* Layout espelhado de `_CLASS_DESC`/`_INTERFACE_ENTRY` (ADR-0080, fase B2). */
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
    result->cp_offsets = NULL;
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
    result->cp_offsets = NULL;
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
        lox_panic(0, 0, "R1014", "range() step can't be zero.");
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

/* ADR-0017: só String, Int e Bool são chaves; o interpretador é o oráculo. */
static void lox_map_check_key(int64_t tag, int32_t line, int32_t column) {
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


int64_t lox_float_to_int(double value, int32_t line, int32_t column);

int64_t lox_math_abs_int(int64_t value) {
    return value < 0 ? (int64_t)(0u - (uint64_t)value) : value;
}

double lox_math_abs_float(double value) {
    return fabs(value);
}

double lox_math_sqrt(double value) {
    return sqrt(value);
}

int64_t lox_math_floor(double value, int32_t line, int32_t column) {
    return lox_float_to_int(floor(value), line, column);
}

int64_t lox_math_ceil(double value, int32_t line, int32_t column) {
    return lox_float_to_int(ceil(value), line, column);
}

int64_t lox_math_round(double value, int32_t line, int32_t column) {
    return lox_float_to_int(round(value), line, column);
}

int64_t lox_math_trunc(double value, int32_t line, int32_t column) {
    return lox_float_to_int(trunc(value), line, column);
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
    char *copy = lox_alloc_atomic(size + 1);
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

/* Checagem de tipo de runtime para `is`/`as` (ADR-0075).
 *
 * O lowering serializa o tipo alvo numa string compacta e o matcher percorre
 * listas, mapas e tuplas com os mesmos acessores do runtime. A árvore é
 * cacheada por ponteiro de string (o global de cada sítio de `is`/`as`).
 *
 * Gramática: A=Any, X=never, N=nil, B=Bool, I=Int, F=Float, S=String,
 * R=Range, L<T>=List, M<K,V>=Map, T<T1,...>=Tuple, U<T1|...>=Union,
 * E<id>=enum, C<id>=classe.
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

static LoxTypeCache *lox_type_cache = NULL;

static LoxTypeDesc *lox_type_desc_new(void) {
    LoxTypeDesc *desc = lox_alloc(sizeof(LoxTypeDesc));
    desc->kind = 0;
    desc->a = NULL;
    desc->b = NULL;
    desc->count = 0;
    desc->items = NULL;
    return desc;
}

static const char *lox_parse_type(const char *cursor, LoxTypeDesc *desc) {
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

static LoxTypeDesc *lox_type_parse_cached(const char *text) {
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

/* Descritor de classe: [super, id, nome, ...]. A instância guarda o descritor
 * no primeiro campo; a herança é a cadeia de `super`. */
static int lox_class_id_matches(const void *descriptor, int64_t id) {
    while (descriptor != NULL) {
        const int64_t *words = descriptor;
        if (words[1] == id) {
            return 1;
        }
        descriptor = *(const void *const *)descriptor;
    }
    return 0;
}

static int lox_type_matches_desc(int64_t tag, int64_t payload,
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
    case 6: { /* instância */
        const void *instance = (const void *)payload;
        return lox_class_id_matches(*(const void *const *)instance,
                                    type->count);
    }
    case 9: { /* lista */
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
    case 10: { /* mapa */
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
    case 11: { /* tupla */
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
    default:
        return 0;
    }
}

int lox_type_matches_str(int64_t tag, int64_t payload, const char *text) {
    return lox_type_matches_desc(tag, payload, lox_type_parse_cached(text));
}

/* `chars(s)[i]`: i é índice em code points, não em bytes. */
static int64_t utf8_cp_offset(const LoxStr *string, int64_t index) {
    if (index < 0 || index > string->cp_len) {
        lox_panic(0, 0, "R1007", "String index out of bounds.");
    }
    if (string->cp_offsets == NULL && string->cp_len >= 64) {
        int32_t *offsets = lox_alloc_atomic(
            (size_t)(string->cp_len + 1) * sizeof(int32_t));
        const unsigned char *data = (const unsigned char *)string->data;
        size_t offset = 0;
        int64_t position = 0;
        offsets[0] = 0;
        while (position < string->cp_len) {
            unsigned char byte = data[offset];
            offset += byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                       : (byte & 0xF0) == 0xE0 ? 3 : 4;
            position += 1;
            offsets[position] = (int32_t)offset;
        }
        ((LoxStr *)string)->cp_offsets = offsets;
    }
    if (string->cp_offsets != NULL) {
        return string->cp_offsets[index];
    }
    const unsigned char *data = (const unsigned char *)string->data;
    size_t offset = 0;
    for (int64_t position = 0; position < index; position++) {
        unsigned char byte = data[offset];
        offset += byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                   : (byte & 0xF0) == 0xE0 ? 3 : 4;
    }
    return (int64_t)offset;
}

void *lox_str_char_at(const void *pointer, int64_t index) {
    const LoxStr *string = pointer;
    int64_t offset = utf8_cp_offset(string, index);
    const unsigned char *data = (const unsigned char *)string->data;
    unsigned char byte = data[offset];
    size_t length = byte < 0x80 ? 1 : (byte & 0xE0) == 0xC0 ? 2
                     : (byte & 0xF0) == 0xE0 ? 3 : 4;
    return string_from_bytes((const char *)data + offset, length, 1);
}

void *lox_substr(const void *pointer, int64_t start, int64_t end) {
    const LoxStr *string = pointer;
    if (start < 0 || end < start) {
        lox_panic(0, 0, "R1007", "String index out of bounds.");
    }
    int64_t begin = utf8_cp_offset(string, start);
    int64_t finish = utf8_cp_offset(string, end);
    size_t length = (size_t)(finish - begin);
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *data = (char *)(result + 1);
    memcpy(data, string->data + begin, length);
    data[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = end - start;
    result->data = data;
    result->cp_offsets = NULL;
    return result;
}

void *lox_join(const void *parts_pointer, const void *separator_pointer) {
    const LoxList *parts = parts_pointer;
    const LoxStr *separator = separator_pointer;
    size_t bytes = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        const LoxValue *item = &parts->items[index];
        if (item->tag != 4) {
            lox_panic(0, 0, "R1006", "join() expects List[String].");
        }
        bytes += (size_t)((const LoxStr *)item->payload)->byte_len;
        if (index + 1 < parts->count) {
            bytes += (size_t)separator->byte_len;
        }
    }
    LoxStr *result = lox_alloc(sizeof(LoxStr) + bytes + 1);
    char *data = (char *)(result + 1);
    size_t used = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        const LoxStr *item = (const LoxStr *)parts->items[index].payload;
        memcpy(data + used, item->data, (size_t)item->byte_len);
        used += (size_t)item->byte_len;
        if (index + 1 < parts->count) {
            memcpy(data + used, separator->data, (size_t)separator->byte_len);
            used += (size_t)separator->byte_len;
        }
    }
    data[used] = '\0';
    result->byte_len = (int64_t)used;
    result->cp_len = 0;
    for (int64_t index = 0; index < parts->count; index++) {
        result->cp_len += ((const LoxStr *)parts->items[index].payload)->cp_len;
        if (index + 1 < parts->count) {
            result->cp_len += separator->cp_len;
        }
    }
    result->data = data;
    result->cp_offsets = NULL;
    return result;
}

static int64_t utf8_decode(const unsigned char *data, size_t *length) {
    unsigned char byte = data[0];
    if (byte < 0x80) {
        *length = 1;
        return byte;
    }
    if ((byte & 0xE0) == 0xC0) {
        *length = 2;
        return ((int64_t)(byte & 0x1F) << 6) | (data[1] & 0x3F);
    }
    if ((byte & 0xF0) == 0xE0) {
        *length = 3;
        return ((int64_t)(byte & 0x0F) << 12) |
               ((int64_t)(data[1] & 0x3F) << 6) | (data[2] & 0x3F);
    }
    *length = 4;
    return ((int64_t)(byte & 0x07) << 18) |
           ((int64_t)(data[1] & 0x3F) << 12) |
           ((int64_t)(data[2] & 0x3F) << 6) | (data[3] & 0x3F);
}

int64_t lox_char_code_at(const void *pointer, int64_t index) {
    const LoxStr *string = pointer;
    if (index < 0 || index >= string->cp_len) {
        lox_panic(0, 0, "R1000", "charCodeAt() index out of bounds.");
    }
    int64_t offset = utf8_cp_offset(string, index);
    size_t length = 0;
    return utf8_decode((const unsigned char *)string->data + offset, &length);
}

void *lox_from_code_point(int64_t code_point) {
    if (code_point < 0 || code_point > 0x10FFFF ||
        (code_point >= 0xD800 && code_point <= 0xDFFF)) {
        lox_panic(0, 0, "R1006", "Invalid Unicode code point.");
    }
    char bytes[4];
    size_t length;
    if (code_point < 0x80) {
        bytes[0] = (char)code_point;
        length = 1;
    } else if (code_point < 0x800) {
        bytes[0] = (char)(0xC0 | (code_point >> 6));
        bytes[1] = (char)(0x80 | (code_point & 0x3F));
        length = 2;
    } else if (code_point < 0x10000) {
        bytes[0] = (char)(0xE0 | (code_point >> 12));
        bytes[1] = (char)(0x80 | ((code_point >> 6) & 0x3F));
        bytes[2] = (char)(0x80 | (code_point & 0x3F));
        length = 3;
    } else {
        bytes[0] = (char)(0xF0 | (code_point >> 18));
        bytes[1] = (char)(0x80 | ((code_point >> 12) & 0x3F));
        bytes[2] = (char)(0x80 | ((code_point >> 6) & 0x3F));
        bytes[3] = (char)(0x80 | (code_point & 0x3F));
        length = 4;
    }
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *data = (char *)(result + 1);
    memcpy(data, bytes, length);
    data[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = 1;
    result->data = data;
    result->cp_offsets = NULL;
    return result;
}


int64_t lox_int_pow(int64_t base, int64_t exponent, int32_t line,
                    int32_t column) {
    if (exponent < 0) {
        lox_panic(line, column, "R1006",
                  "Negative exponent not allowed for integer power.");
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

int64_t lox_shift(int64_t value, int64_t count, int32_t kind, int32_t line,
                  int32_t column) {
    if (count < 0 || count > 63) {
        lox_panic(line, column, "R1006",
                  "Shift count must be between 0 and 63.");
    }
    if (kind == 0) {
        return (int64_t)((uint64_t)value << (uint64_t)count);
    }
    if (kind == 1) {
        return value >> (uint64_t)count;
    }
    return (int64_t)((uint64_t)value >> (uint64_t)count);
}

int64_t lox_float_to_int(double value, int32_t line, int32_t column) {
    if (isnan(value) || isinf(value) || value < -9223372036854775808.0 ||
        value >= 9223372036854775808.0) {
        lox_panic(line, column, "R1011", "Can't cast value to Int.");
    }
    return (int64_t)value;
}


/* Exceções do L6j: frames de try, throw e cleanup mínimo (ADR-0062). */
typedef struct {
    const char *type_name;
    void *instance;
    const char *message;
    int32_t line;
    int32_t column;
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
    frame->exception.column = 0;
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

static void lox_print_prefix(int32_t line, int32_t column, const char *code) {
    if (line > 0 && column > 0) {
        fprintf(stderr, "%s:%" PRId32 ":%" PRId32 ": error[%s]: ",
                lox_source_path, line, column, code);
    } else if (line > 0) {
        fprintf(stderr, "%s:%" PRId32 ": error[%s]: ", lox_source_path, line, code);
    } else {
        fprintf(stderr, "error[%s]: ", code);
    }
}

void lox_throw(void *instance, const char *type_name, const char *message,
               int32_t line, int32_t column) {
    LoxTryFrame *frame = lox_current_try;
    if (frame == NULL) {
        fflush(stdout);
        lox_print_prefix(line, column, "R1010");
        if (message != NULL) {
            fprintf(stderr, "Unhandled exception: %s: %s\n", type_name, message);
        } else {
            fprintf(stderr, "Unhandled exception: %s\n", type_name);
        }
        fflush(stderr);
        exit(70);
    }
    frame->exception.type_name = type_name;
    frame->exception.instance = instance;
    frame->exception.message = message;
    frame->exception.line = line;
    frame->exception.column = column;
    longjmp(frame->env, 1);
}

void lox_rethrow(void *exception_pointer, int32_t line, int32_t column) {
    LoxException *exception = exception_pointer;
    lox_throw(exception->instance, exception->type_name, exception->message, line,
              column);
}

void lox_raise_current(int32_t line, int32_t column) {
    LoxTryFrame *frame = lox_current_try;
    if (frame == NULL) {
        lox_panic(line, column, "R1014", "No exception to re-raise.");
    }
    lox_throw(frame->exception.instance, frame->exception.type_name,
              frame->exception.message, line, column);
}

void lox_panic(int32_t line, int32_t column, const char *code,
               const char *message) {
    if (lox_current_try != NULL) {
        lox_throw(NULL, "RuntimeError", message, line, column);
    }
    fflush(stdout);
    lox_print_prefix(line, column, code);
    fprintf(stderr, "%s\n", message);
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
    return string_from_bytes(data, length, (int64_t)length);
}

static LoxStr *string_from_bytes(const char *data, size_t length,
                                 int64_t code_points) {
    LoxStr *result = lox_alloc(sizeof(LoxStr) + length + 1);
    char *copy = (char *)(result + 1);
    memcpy(copy, data, length);
    copy[length] = '\0';
    result->byte_len = (int64_t)length;
    result->cp_len = code_points;
    result->data = copy;
    result->cp_offsets = NULL;
    return result;
}

const char *lox_str_data(const void *pointer) {
    return ((const LoxStr *)pointer)->data;
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

/* Materializa a mensagem C de um panic como LoxStr para `except ... as e`. */
void *lox_str_from_cstr(const char *data) {
    if (data == NULL) {
        return lox_str_nil();
    }
    return string_from_ascii(data, strlen(data));
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
    buffer->data = lox_alloc_atomic(buffer->capacity);
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
    char *data = lox_alloc_atomic(capacity);
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

/* `str`/interpolação de valor boxeado `Any`: mesma formatação de `print` dinâmico. */
void *lox_str_from_any(int64_t tag, int64_t payload) {
    if (tag == 4) {
        return (void *)payload;
    }
    LoxBuffer buffer;
    buffer_init(&buffer);
    LoxValue value;
    value.tag = tag;
    value.payload = payload;
    format_value(&buffer, value);
    return string_from_ascii(buffer.data, buffer.length);
}

/*
 * `//`: divisão inteira truncada em direção a zero, com wrapping de i64 em release
 * (ADR-0028). O interpretador devolve INT_MIN para INT_MIN // -1; em C e em LLVM isso
 * é UB, então o caso é resolvido explicitamente.
 */
int64_t lox_int_div(int64_t left, int64_t right, int32_t line,
                    int32_t column) {
    if (right == 0) {
        lox_panic(line, column, "R1002", "Division by zero not allowed");
    }
    if (left == INT64_MIN && right == -1) {
        return INT64_MIN;
    }
    return left / right;
}

/* `/`: sempre Float. Divisão por zero é erro fatal, como no interpretador. */
double lox_float_div(double left, double right, int32_t line,
                     int32_t column) {
    if (right == 0.0) {
        lox_panic(line, column, "R1002", "Division by zero not allowed");
    }
    return left / right;
}

/* `%` com Float: `fmod`, sinal do dividendo, e zero é erro (como no interpretador). */
double lox_float_mod(double left, double right, int32_t line,
                     int32_t column) {
    if (right == 0.0) {
        lox_panic(line, column, "R1002", "Modulo by zero not allowed");
    }
    return fmod(left, right);
}

/* `%`: resto truncado (sinal do dividendo), como `srem`. INT_MIN % -1 é 0. */
int64_t lox_int_mod(int64_t left, int64_t right, int32_t line,
                    int32_t column) {
    if (right == 0) {
        lox_panic(line, column, "R1002", "Modulo by zero not allowed");
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
            lox_panic(0, 0, "R1000", "Unknown Any tag");
    }
}


/* Kernel 13.2 (ADR-0071): SO e representação. */
static int64_t utf8_code_points(const char *data, size_t length) {
    int64_t count = 0;
    for (size_t index = 0; index < length; index++) {
        unsigned char byte = (unsigned char)data[index];
        if ((byte & 0xC0) != 0x80) {
            count += 1;
        }
    }
    return count;
}

void *lox_args(void) {
    void *list = lox_list_new();
    for (int32_t index = 1; index < lox_argc; index++) {
        const char *argument = lox_argv[index];
        size_t length = strlen(argument);
        lox_list_push(list, 4, (int64_t)string_from_bytes(
            argument, length, utf8_code_points(argument, length)));
    }
    return list;
}

void lox_io_write(const void *pointer) {
    const LoxStr *text = pointer;
    fwrite(text->data, 1, (size_t)text->byte_len, stdout);
}

void lox_io_write_err(const void *pointer) {
    const LoxStr *text = pointer;
    fwrite(text->data, 1, (size_t)text->byte_len, stderr);
}

void *lox_io_read_file(const void *pointer) {
    const LoxStr *path = pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    FILE *file = fopen(path_copy, "rb");
    if (file == NULL) {
        return NULL;
    }
    LoxBuffer buffer;
    buffer_init(&buffer);
    char chunk[4096];
    size_t read;
    while ((read = fread(chunk, 1, sizeof chunk, file)) > 0) {
        buffer_bytes(&buffer, chunk, read);
    }
    fclose(file);
    return string_from_bytes(buffer.data, buffer.length,
                             utf8_code_points(buffer.data, buffer.length));
}

int32_t lox_io_write_file(const void *path_pointer, const void *text_pointer) {
    const LoxStr *path = path_pointer;
    const LoxStr *text = text_pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    FILE *file = fopen(path_copy, "wb");
    if (file == NULL) {
        return 0;
    }
    size_t written = fwrite(text->data, 1, (size_t)text->byte_len, file);
    int ok = written == (size_t)text->byte_len;
    if (fclose(file) != 0) {
        ok = 0;
    }
    return ok ? 1 : 0;
}

void *lox_io_read_line(void) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    int byte;
    while ((byte = fgetc(stdin)) != EOF && byte != '\n') {
        buffer_char(&buffer, (char)byte);
    }
    if (byte == EOF && buffer.length == 0) {
        return NULL;
    }
    if (buffer.length > 0 && buffer.data[buffer.length - 1] == '\r') {
        buffer.length -= 1;
    }
    return string_from_bytes(buffer.data, buffer.length,
                             utf8_code_points(buffer.data, buffer.length));
}

void *lox_io_read_all(void) {
    LoxBuffer buffer;
    buffer_init(&buffer);
    char chunk[4096];
    size_t read;
    while ((read = fread(chunk, 1, sizeof chunk, stdin)) > 0) {
        buffer_bytes(&buffer, chunk, read);
    }
    return string_from_bytes(buffer.data, buffer.length,
                             utf8_code_points(buffer.data, buffer.length));
}

int32_t lox_fs_exists(const void *path_pointer) {
    const LoxStr *path = path_pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    struct stat info;
    return stat(path_copy, &info) == 0 ? 1 : 0;
}

static int compare_dir_names(const void *left, const void *right) {
    const char *a = *(const char *const *)left;
    const char *b = *(const char *const *)right;
    return strcmp(a, b);
}

/*
 * Lista ordenada por byte (equivale à ordem de code point em UTF-8), sem "." e "..",
 * para não vazar a ordem do diretório (I3). Devolve NULL quando não é um diretório
 * legível — a stdlib traduz para nil.
 */
void *lox_fs_list_dir(const void *path_pointer) {
    const LoxStr *path = path_pointer;
    char *path_copy = lox_alloc_atomic((size_t)path->byte_len + 1);
    memcpy(path_copy, path->data, (size_t)path->byte_len);
    path_copy[path->byte_len] = '\0';
    DIR *dir = opendir(path_copy);
    if (dir == NULL) {
        return NULL;
    }
    size_t count = 0;
    size_t capacity = 8;
    char **names = lox_alloc(sizeof(char *) * capacity);
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        const char *name = entry->d_name;
        if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0) {
            continue;
        }
        if (count == capacity) {
            size_t grown_capacity = capacity * 2;
            char **grown = lox_alloc(sizeof(char *) * grown_capacity);
            memcpy(grown, names, sizeof(char *) * count);
            names = grown;
            capacity = grown_capacity;
        }
        size_t length = strlen(name);
        char *copy = lox_alloc_atomic(length + 1);
        memcpy(copy, name, length + 1);
        names[count] = copy;
        count += 1;
    }
    closedir(dir);
    qsort(names, count, sizeof(char *), compare_dir_names);
    void *list = lox_list_new();
    for (size_t index = 0; index < count; index++) {
        size_t length = strlen(names[index]);
        lox_list_push(list, 4, (int64_t)string_from_bytes(
            names[index], length, utf8_code_points(names[index], length)));
    }
    return list;
}

void lox_os_exit(int64_t code) {
    if (code < 0 || code > 255) {
        lox_panic(0, 0, "R1006", "os.exit() expects a code between 0 and 255.");
    }
    fflush(stdout);
    fflush(stderr);
    exit((int)code);
}

void *lox_os_getenv(const void *name_pointer) {
    const LoxStr *name = name_pointer;
    char *name_copy = lox_alloc_atomic((size_t)name->byte_len + 1);
    memcpy(name_copy, name->data, (size_t)name->byte_len);
    name_copy[name->byte_len] = '\0';
    const char *value = getenv(name_copy);
    if (value == NULL) {
        return NULL;
    }
    size_t length = strlen(value);
    return string_from_bytes(value, length, utf8_code_points(value, length));
}

int64_t lox_time_now(void) {
    struct timespec timestamp;
    timespec_get(&timestamp, TIME_UTC);
    return (int64_t)timestamp.tv_sec * 1000 +
           (int64_t)(timestamp.tv_nsec / 1000000);
}

void lox_time_sleep(int64_t milliseconds) {
    if (milliseconds < 0) {
        lox_panic(0, 0, "R1006", "time.sleep() expects a non-negative duration.");
    }
    struct timespec duration;
    duration.tv_sec = (time_t)(milliseconds / 1000);
    duration.tv_nsec = (long)((milliseconds % 1000) * 1000000);
    while (nanosleep(&duration, &duration) == -1) {
        /* interrupção por sinal: continua o restante */
    }
}
