# ADR-0138 — Remoção do `for` C-style

- **Status:** accepted (breaking; implementado em 2026-11-23)
- **Data:** 2026-11-23
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0007](0007-ranges-e-iteracao.md) (`for-in` e ranges),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate e orçamento),
  [ADR-0026](0026-freeze-1.0.md) (freeze da 1.0), [`../spec/sintaxe.md`](../spec/sintaxe.md)
- **Implementação:** `loxia_core/frontend/parser.py`, `loxia/formatter/printer.py`,
  `tests/cases/for.lx`, `tests/cases/errors/for_c_style_removed.lx`,
  `tests/test_formatter_v2.py`, `tests/test_interpreter.py`

## Contexto

O `for (init; cond; incr) s` é o único `for` que o Loxia herdou do livro. Ele nunca teve
nó de AST: o parser desaçucara para bloco + `while`, com o incremento no fim do corpo
([`sintaxe.md`](../spec/sintaxe.md)). O `for-in` (`for x in expr`) e o `while` cobrem os
mesmos casos, e o `std/` usa apenas essas duas formas.

Essa desugarização já cobrava um preço no formatter, que precisava reconstruir o `for`
C-style a partir do bloco sintético. Com a chegada de `break`/`continue`, o preço sobe:
`continue` precisa executar o incremento antes de rechecar a condição, e um `Continue`
dentro do corpo desaçucarado pularia o incremento. Resolver isso exigiria um campo interno
`While.increment` ou um nó `For` novo — complexidade que só existe para manter uma forma
redundante.

O dono do projeto decidiu remover a forma agora, como mudança breaking, em vez de mantê-la
e arcar com a semântica especial de `continue`. O `for` continua existindo como `for-in`.

## Decisão

1. A gramática perde `for (init; cond; incr) s`. Permanece apenas:

   ```ebnf
   forStmt → "for" IDENTIFIER "in" expression statement ;
   ```

2. O parser reconhece `for (` e emite um diagnóstico dirigido:

   ```text
   C-style 'for' was removed; use `for x in range(n)` or a `while` loop.
   ```

   Não é um erro genérico de “expect identifier”: a mensagem ensina a migração.

3. Não há nó novo de AST nem mudança de runtime: o C-style nunca existiu como nó. O
   backend, o checker e o interpreter não ganham caminho específico.

4. `for` continua sendo keyword por causa do `for-in`; o orçamento de keywords não muda.
   A remoção não é uma economia de orçamento — é uma redução de superfície e de
   complexidade de controle de fluxo.

5. A mudança é **breaking**: entra em `CHANGELOG.md` como quebra, com `!` no
   commit/PR e `BREAKING CHANGE:`; a release que a carrega é a próxima major (2.0).

## Migração

| Antes | Depois |
| --- | --- |
| `for (var i = 0; i < n; i = i + 1) { ... }` | `for i in 0..n { ... }` |
| `for (var i = a; i < b; i = i + step) { ... }` | `for i in range(a, b, step) { ... }` |
| `for (var i = 0; i < len(xs); i = i + 1) { ... }` | `for i in 0..len(xs) { ... }` |
| `for (;;) { ... }` | `while (true) { ... }` |
| init/update com mais de um passo | `while` com o init antes e o update no fim do corpo |

`for i in 0..n` é half-open; para incluir `n`, use `0..=n` ([ADR-0097](0097-ranges-inclusivos.md)).

## Consequências

- **Positivas:** uma única forma de laço contado (`for-in`); formatter perde a
  reconstrução heurística de `for (;;)`; `break`/`continue` passam a ter apenas `while` e
  `for-in` como alvos, o que remove o caso `continue` + incremento do backend.
- **Negativas:** quebra programas 1.x que usavam C-style; exige migração e uma major.
  A familiaridade C/Java/JS é perdida; quem precisa do formato C escreve `while`.
- O suíte oficial do livro não usa C-style; só um caso do corpus e testes do formatter
  precisam mudar.
- `while (true)` continua sendo o loop infinito canônico; `break`/`continue` entram na
  slice seguinte e tornam esse padrão realmente utilizável.

## Alternativas rejeitadas

| Alternativa | Por quê |
| --- | --- |
| Manter e adicionar `While.increment` | Mantém uma forma redundante e um campo interno só para o `continue`; foi a opção anterior, descartada pelo dono. |
| Manter e adicionar um nó `For` | Mais honesto que o campo, mas é um refactor maior para preservar uma forma que o `for-in` cobre. |
| Depreciar na 1.x e remover na 2.0 | Adia a decisão e mantém o custo de formatter/`continue` por mais tempo; o dono preferiu remover já. |
| Rejeitar `continue` em C-style for | Cria uma exceção semântica invisível e não resolve a falta de `continue`. |
| Manter `for (;;)` sem `break` | O loop infinito já é `while (true)`; sem `break` o C-style é ainda menos útil. |

## Como verificar

- `tests/cases/for.lx` passa a usar `for i in 0..3` e continua no `l2` diferencial.
- `tests/cases/errors/for_c_style_removed.lx` fixa a mensagem e o exit 65.
- `tests/test_formatter_v2.py` não tem mais caso C-style; o formatter não reconstrói
  `for (;;)`.
- `tests/test_interpreter.py::test_while_and_for_in_loops` cobre o substituto.
- `make check` verde; `make oracle-update` e `make grammar` regenerados.
