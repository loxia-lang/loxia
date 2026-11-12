# ADR-0005 — `val`/`var` e imutabilidade de bindings

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TODO.md`](../../TODO.md) §1/§11,
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `src/parser.py`, `src/stmt.py`, `src/resolver.py`, `src/environment.py`,
  `src/interpreter.py`, `src/lox_function.py`, casos em `tests/cases/val_*.lox`

## Contexto

O Lox do livro só tem `var`, sempre mutável. Queremos declarações mais expressivas, com
imutabilidade como opção explícita, e essa escolha precisa conversar com os objetivos de
inferência de tipos e de codegen LLVM (SSA). A discussão completa está em
[ADR-0005](0005-val-var-imutabilidade.md).

A decisão maior: **usar `val` (imutável) e `var` (mutável), os dois**.

## Decisão

1. **Dois tipos de binding**: `val` imutável, `var` mutável. A mutabilidade é do **nome**
   (binding), não do valor: `val lista` ainda pode ter conteúdo mutável.
2. **`val` exige inicializador** (`val x;` é erro de sintaxe). `var` pode omitir e vale
   `nil`.
3. **Parâmetros são imutáveis por padrão**; `var` antes do parâmetro permite reatribuir:
   `fn f(x, var y)`. Parâmetro é `val` implícito.
4. **Sombreamento**: permitido em escopo aninhado; redeclaração no **mesmo** escopo é erro
   (comportamento atual do resolver, agora também com `val`).
5. **Locais x globais**: locais são checados em **compilação** pelo resolver (exit 65);
   globais são checados em **runtime** pelo `Environment`, que guarda a mutabilidade de
   cada binding (exit 70).
6. **Redeclaração global**: um binding imutável não pode ser redeclarado
   (`val x = 1; var x = 2;` falha em runtime). `var` global continua redeclarável; `var`
   seguido de `val` é permitido e o nome passa a ser imutável.
7. **Mensagem** de atribuição a imutável (inglês, padrão do projeto):
   `'x' is immutable; declare it with 'var' to allow assignment.`
8. **Campos de classe não entram ainda**: campos continuam dinâmicos e mutáveis; a
   mutabilidade de campos (e parâmetros opcionais/default) fica para [ADR-0009](0009-defaults-e-campos.md).

`fn` e `class` continuam criando bindings **mutáveis** (redeclaráveis/reatribuíveis) —
decisão separada, registrada como consequência em aberto.

## Consequências

### Positivas

- A intenção fica no código: `val` documenta "este nome não muda".
- Abre caminho para generalização/SSA: binding imutável pode virar valor direto no LLVM.
- Parâmetros imutáveis por padrão reduzem o estado mutável dentro de funções.
- Custo baixo agora (parser/resolver pequenos) e sem quebrar os 73 casos golden existentes:
  todo código antigo continua válido com `var`.

### Negativas / custos

- Globais imutáveis falham em **runtime** (exit 70), não em compilação; a UX não é
  uniforme com locais (mitigável no futuro com o resolver rastreando globais).
- Nenhuma imutabilidade profunda: `val lista` pode mudar de conteúdo.
- Campos de classe ainda não participam da regra.
- Funções/classes ainda são bindings mutáveis.
- `val` em inicializador de `for` é aceito, mas o incremento normal (`i = i + 1`) falha na
  imutabilidade; ainda não há erro dedicado para esse caso.

### Neutras

- `val` adiciona uma palavra-chave (17 no total) e um erro de parser novo.
- O AST ganhou `Var.mutable` e o nó `Param(name, mutable)`.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só `var` (estilo Go/Python) | menos cerimônia, mas perde a intenção e a ajuda ao checker/SSA |
| `val` mutável (nome só estético) | promete imutabilidade que não garante; pior dos dois mundos |
| `let` + `let mut` (Rust) | funciona, mas `val`/`var` é mais próximo de Kotlin/Scala e do nome "valor" |
| Imutável por padrão sem keyword (`val` implícito, `mut` para mutar) | reduz ruído, porém muda todo `var` existente e a leitura fica menos explícita |
| Checar globais também em compilação | melhor UX; exige rastrear globais no resolver e persistir no REPL (fica como evolução) |

## Como verificar

Golden cases e testes que travam o comportamento:

- `tests/cases/val_var.lox`, `val_shadowing.lox`, `val_params.lox`, `var_redeclare.lox`;
- `tests/cases/errors/assign_val_local.lox` (65), `assign_val_global.lox` (70),
  `val_without_initializer.lox` (65), `val_redeclare_global.lox` (70),
  `param_immutable.lox` (65), `val_redeclare_local.lox` (65);
- `tests/test_parser.py` (flags `mutable`, `Param`), `tests/test_resolver.py`
  (local/parâmetro imutável, global adiada), `tests/test_environment.py`
  (`define(mutable=...)`, `assign_at`) e `tests/test_interpreter.py`.

Critério para revisar: se a checagem de globais em compilação for implementada, ou se
campos/`fn`/`class` ganharem regra própria, este ADR é substituído por um novo.
