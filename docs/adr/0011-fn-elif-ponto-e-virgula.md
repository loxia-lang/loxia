# ADR-0011 — `fn`, `elif` e `;` opcional

- **Status:** accepted
- **Data:** 2026-11-11
- **Atualizado por:** [ADR-0067](0067-desambiguacao-sintatica.md) — operador pode iniciar a
  linha dentro de `()`, `[]` e `{}` de expressão; `fn` é opcional em método.
- **Relacionados:** [`../../TODO.md`](../../TODO.md) §1,
  [`../spec/sintaxe.md`](../spec/sintaxe.md), [`../spec/lexico.md`](../spec/lexico.md),
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `loxia_core/frontend/token_type.py`, `loxia_core/frontend/keywords.py`, `loxia_core/frontend/parser.py`,
  `loxia_core/frontend/ast_printer.py`; testes em `tests/test_parser.py`, `tests/test_scanner.py` e
  `tests/cases/optional_semicolons.lox` / `elif.lox` / `return_newline.lox` /
  `operator_line.lox`

## Contexto

A sintaxe ainda tinha três ruídos do Lox do livro: `fun` em vez de `fn`, `else if`
obrigatório e `;` em toda linha. O objetivo da linguagem própria (§1 do TODO) é reduzir
ruído sem criar ambiguidade. A mudança é só de sintaxe: a AST e a semântica não mudaram
(com exceção do `return` sozinho na linha, que já era o caso sem valor).

## Decisão

### 1. `fn` no lugar de `fun`

`fn` vira a palavra-chave; `fun` deixa de ser reservada e passa a ser um identificador
comum. Não há alias: duas grafias para a mesma declaração só aumentariam a superfície.
O dump da AST usa `(fn ...)`.

### 2. `elif`

`elif (cond) { ... }` é **açúcar sintático** para `else if (cond) { ... }`, produzindo o
mesmo `If` aninhado. Parênteses na condição continuam obrigatórios (a remoção de parênteses
é outra decisão). `else if` continua funcionando; `elif` não pode iniciar um statement
fora de um `if`.

### 3. `;` opcional no fim da linha

O `;` termina statements e campos, mas é opcional quando o próximo token começa em outra
linha ou no EOF. Duas instruções na mesma linha ainda exigem `;`:

```lox
val a = 1
print a
val b = 1; val c = 2
```

Regras de continuação (parser-level, sem inserir tokens no scanner):

- operador binário/infixo só continua a expressão se estiver na **mesma linha** do
  operando esquerdo. Na prática: quebre a linha **depois** do operador.
- `=` de atribuição também precisa estar na mesma linha do alvo.
- chamada com `(` precisa começar na mesma linha do callee; quebrar antes de `.` é
  permitido (encadeamento de propriedades).
- `return` sozinho no fim da linha devolve `nil`; o valor precisa estar na mesma linha.
- `else`/`elif` podem vir em linha nova depois do bloco.
- campos de classe seguem a mesma regra do `;` opcional.

## Consequências

### Positivas

- Menos ruído no caso comum; o `;` continua disponível para uma linha com várias
  instruções.
- Sem ASI “mágica” no scanner: a decisão fica explícita no parser, com regra previsível.
- `fn` e `elif` deixam a sintaxe mais próxima do alvo do `TODO.md` §1.
- Nenhum nó novo de AST: `elif` vira `If` aninhado e `;` some do stream.

### Negativas / armadilhas

- `val x = 1` seguido de `-2` na linha seguinte são **dois statements**, não
  `1 - 2`. Para subtrair, o `-` precisa terminar a linha anterior ou estar entre
  parênteses.
- `foo` em uma linha e `(1)` na seguinte **não** é chamada; é um statement `foo` seguido de
  uma expressão agrupada. Para chamar, o `(` fica na mesma linha.
- `return` seguido de valor em outra linha devolve `nil` (regra de Go); não é possível
  quebrar entre `return` e o valor.
- `fun` como identificador pode surpreender quem vem da versão anterior; não há aviso de
  compatibilidade.
- O `;` opcional não é inserido dentro de headers de `for`: os `;` do cabeçalho continuam
  obrigatórios.

### Neutras

- O scanner não mudou (só o mapa de keywords); o parser ganhou `_match_inline` e o
  tratamento de `elif`.
- A ASTPrinter passou a imprimir `(fn ...)`.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Inserir `SEMICOLON` no scanner em todo fim de linha | quebra headers (`if (x)` + corpo na linha seguinte) e chamadas multi-linha; exigiria muitas exceções |
| ASI completa estilo JavaScript | regras sutis (`(`/`[` no começo da linha) e difícil de explicar; o parser-level é mais simples |
| Manter `fun` como alias de `fn` | duas grafias, keywords e mensagens ambíguas; migração é pequena |
| `elif` sem parênteses | mistura com a decisão pendente de parênteses em `if`; fica para outra mudança |
| Usar `else if` só | mais ruído e não era o pedido |

## Como verificar

- `tests/cases/optional_semicolons.lox` — statements, campos e `for-in` sem `;`;
- `tests/cases/elif.lox` — `elif` na mesma linha e em linha nova;
- `tests/cases/return_newline.lox` — `return` sozinho devolve `nil`;
- `tests/cases/operator_line.lox` — operador no começo da linha não continua;
- `tests/cases/same_line_semicolon.lox` — `;` ainda necessário na mesma linha;
- `tests/test_parser.py` — `elif`, newline, `return`, operador e campo;
- `tests/test_scanner.py` — keywords `fn`/`elif` e `fun` como identificador;
- `make check`.

Critério para revisar: se `;` opcional virar inserção léxica, se parênteses de `if`
saírem, ou se `fn` ganhar corpo de expressão.
