# ADR-0048 — L5: ABI de métodos, descritor de classe e instância

- **Status:** accepted (L5a/L5b implementados; L5c pendente)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0008](0008-heranca-class-parens.md), [ADR-0009](0009-defaults-e-campos.md),
  [ADR-0023](0023-soundness-do-checker.md), [ADR-0031](0031-backend-nativo.md),
  [ADR-0043](0043-layout-l5-classes.md), [ADR-0044](0044-identidade-classe.md),
  [ADR-0045](0045-narrowing-representacao.md), [ADR-0046](0046-closures-celulas-l4.md),
  [ADR-0047](0047-optionais-escalares-l2-5.md), [`../../TODO.md`](../../TODO.md) §6.6
- **Implementação:** `src/backend/lower.py`, `src/backend/classes.py`,
  `runtime/runtime.c`, `tests/test_backend.py`, `tests/corpus_manifest.py`

## Contexto

O [ADR-0043](0043-layout-l5-classes.md) fixou layout, vtable e bitmap; o
[ADR-0044](0044-identidade-classe.md) fixou a identidade por objeto; o
[ADR-0045](0045-narrowing-representacao.md) fixou `storage_types`. Falta o que o codegen
precisa para materializar tudo isso **sem duplicar o `interpreter.py`**: convenção de
chamada de método, formato do descritor de classe e da instância, bound method, leitura de
campo não inicializado e a fronteira entre o L5a (classes), L5b (herança) e L5c
(referências nulas/`is`/`as`).

O L4 já tem closures `{fnptr, env, display}` e ABI `(i8* env, params...)`. O L5 deve
reusar isso em vez de criar uma segunda convenção.

## Decisão

### 1. Método = função `(i8* env, i8* this, params...)`

Todo método e `init` compila como:

```llvm
define <ret> @lox.<Classe>.<metodo>(i8* %env, i8* %this, <params>...)
```

- `env` é o ambiente de captura da classe (nulo em classe de topo; preenchido em classe
  local, L5c);
- `this` é a instância (ponteiro opaco para o layout da instância);
- `return` de método normal devolve o tipo anotado; `init` devolve `void` (o construtor
  devolve a instância).

A vtable guarda **closures de método** (`{fnptr, env, display}`), não só `fnptr`: uma
classe local pode ter métodos que capturam ambientes diferentes, e um método herdado
precisa levar o `env` da classe onde foi declarado.

Chamada virtual (incluindo `this.m()` e `obj.m()`) carrega a closure do slot da vtable,
extrai `fnptr/env`, e chama com `this`. Bound method (`obj.m` como valor) cria uma closure
`{thunk, {method_closure, this}, display="<fn m>"}`; o thunk tem assinatura
`(i8* bound_env, params...)` e chama o método com `this`.

### 2. Instância com slots uniformes de 8 bytes

Header de 16 bytes + um slot `i64` por campo:

```llvm
{ i8* class, i64 bitmap, i64 field0, i64 field1, ... }
```

- `class` aponta para o descritor; `bitmap` é o bitmap de inicialização (L5 MVP; 64
  campos no primeiro corte);
- todo campo ocupa um `i64`: `Int` direto, `Float` bitcast, `Bool` zext/trunc, referências
  (`String`, instância, classe, função) via `ptrtoint`/`inttoptr`. Isso evita depender de
  `get_abi_size` e mantém offsets fixos;
- campos `T?` escalares ocupam dois slots? **No L5a não há campo opcional**; o L5c decide
  entre dois slots ou uma célula/ponteiro. Referências `T?` são ponteiro nulo;
- campos base primeiro; a derivada anexa os seus, então o prefixo de offset é compatível
  (L5b).

O tamanho da instância é `16 + 8 * n_fields`; a alocação usa `lox_alloc_bytes`.

### 3. Descritor de classe

```llvm
{ i8* super, i64 id, i8* name, i8* vtable, i64 n_fields,
  i8* init, i64 init_min, i64 init_max }
```

- `name` é um `LoxStr*` estático (`C`) para `print`/`str`/interpolação;
- `vtable` é um array de `i8*` (closures de método) na ordem de declaração; `init` fica
  fora da vtable;
- `init` é a closure do inicializador (ou nulo); `init_min/max` existem para aridade e
  diagnóstico quando a classe é usada como valor;
- classes de topo são inicializadas quando o statement `class` executa (o slot global
  começa nulo, como funções de topo); classes locais ganham descritor em runtime (L5c);
- `id` é determinístico: ordem de declaração no topo; ordem de execução nas locais.

### 4. Construção

`C(args)` em uma classe conhecida estaticamente:

1. avalia os argumentos na ordem da linguagem;
2. confere aridade `[init_min, init_max]` e preenche defaults no call site;
3. chama a função `lox.ctor.<C>` gerada para a classe;
4. o construtor aloca a instância, grava `class`, zera o bitmap, roda os inicializadores
   constantes (marcando os bits), chama `init` (se houver) e confere os bits de todos os
   campos sem inicializador, na ordem base→derivada;
5. campo faltante vira `lox_panic` com `Field 'x' must be initialized.`.

Defaults em `init` são preenchidos no call site **quando a classe é chamada por nome**.
Classe como valor dinâmico (`val K = C; K()`) fica para o L5c; até lá, é 65 explícito. A
alternativa (descriptor de defaults em runtime) fica para um follow-up, como no L4.

### 5. Campo: leitura, escrita e bitmap

- Ler campo declarado carrega o bit; bit 0 → `lox_panic("Undefined property 'x'.")` no
  token do nome. É necessário porque o checker aceita `print this.x` antes da primeira
  atribuição e o tree-walk falha em runtime.
- Escrever campo:
  - objeto não-instância → `Only instances have fields.`;
  - campo não declarado → `Undefined field 'x'.`;
  - `val` fora de `init` → `Can't assign to immutable field 'x'.`;
  - `val` dentro de `init`: primeira atribuição permitida (bit 0), segunda falha; `var`
    sempre permitida.
- Inicializadores constantes rodam no construtor; `init` roda depois. O bitmap não é
  removido pelo checker no MVP (ADR-0043).

### 6. `this`, campos e métodos

- `this` é ligado pelo método ao argumento `this`; acesso a campo é `gep` no slot fixo;
- `this.m()` e `obj.m()` passam pela vtable (despacho virtual a partir do L5b);
- `obj.campo` tem prioridade sobre método (como no tree-walk);
- `print`/`str`/`repr`/interpolação: classe → `C`; instância → `C instance`; bound method →
  `<fn m>`; tudo determinístico e sem endereço.

### 7. Escopo por fase

- **L5a** (implementado): classes de topo, campos/bitmap, métodos/`this`/`init`, bound
  methods, `print` de classe/instância, construção por nome.
- **L5b** (implementado): herança/vtable/`super`, `init` herdado, prefixo de campos,
  despacho virtual e `super.init`.
- **L5c** (parcial): campos/parâmetros/retornos `String?`/instância `T?` e igualdade já
  funcionam; `?.` com receptor opcional, classes locais e `is`/`as` de classe continuam
  65. O `nil_aware` completo depende de união/`Any` e fica no L6.
- **L6**: exceções/`except`, genéricos, `Any`, enums/match.

## Consequências

### Positivas

- Uma ABI só para função/método; bound methods reusam a closure do L4.
- Vtable de closures resolve captura de classe local sem tabela paralela.
- Slots `i64` uniformes simplificam offsets, bitmap, `print` e a herança por prefixo.
- O bit de inicialização impede leitura de lixo e reproduz o erro do tree-walk.

### Negativas / custos

- Todo campo ocupa 8 bytes, inclusive `Bool`; memória maior que o layout teórico.
- Leitura de campo tem uma checagem de bitmap (custo por acesso).
- A vtable guarda closures (3 ponteiros por método) em vez de só fnptr.
- Classe como valor dinâmico e defaults de método ficam limitados no L5a.
- 64 campos por bitmap; classes maiores precisam de bitmap multiword (L5b/L6).

### Neutras

- `init` fora da vtable, como no ADR-0043.
- Classes de topo usam descritor em runtime, não estático em `.rodata`; a ordem e o id são
  determinísticos.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `this` dentro do `env` | exigiria montar/ligar env por chamada e complicaria o thunk de bound method |
| vtable só de fnptr + env por classe | métodos herdados/locais podem ter envs diferentes; precisaria tabela paralela |
| campos com offsets tipados via target data | mais fiel ao layout teórico, mas exige `get_abi_size`/alinhamento e complica o MVP |
| sem checagem de bitmap na leitura | nativo imprimiria lixo/zero onde o tree-walk falha |
| defaults de `init` em descriptor runtime | adia classes como valor com defaults; evita maquinário agora |

## Como verificar

- `tests/test_backend.py`: diferencial de `classes`, `class_fields`, `class_initializer`,
  `class_this`, `class_bound_method`, `fields_val_var`, `typed_functions` no L5a.
- Casos de erro: campo não inicializado lido no `init`, `val` reatribuído, campo desconhecido
  e objeto não-instância, com a mesma mensagem/linha do interpretador.
- `make check` verde; nenhum teste L0–L4/L2.5 regride.

## Critérios para revisitar

- Se classes com mais de 64 campos aparecerem, bitmap multiword ou array de bytes.
- Se o custo da checagem de bitmap doer, provar inicialização no checker e remover checks.
- No L5c, decidir a representação de campos `T?` (dois slots × ponteiro/célula).
