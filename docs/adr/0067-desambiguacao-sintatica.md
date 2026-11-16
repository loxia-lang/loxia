# ADR-0067 — Desambiguação sintática: `//`, brackets, `fn` em método, união em `is`, mapa

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0011](0011-fn-elif-ponto-e-virgula.md),
  [ADR-0013](0013-ternario-nil-aware-escapes.md),
  [ADR-0025](0025-is-e-narrowing.md),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md)
- **Implementação:** `loxia_core/frontend/parser.py`; casos
  `tests/cases/division_comment_hint.lox`, `leading_operator_brackets.lox`,
  `method_fn_keyword.lox`, `is_union_parens.lox`, `is_union_needs_parens.lox`,
  `map_at_statement_start.lox`; testes em `tests/test_parser.py`

## Contexto

A análise sintática de 2026-11-13 encontrou cinco atritos concretos, todos reproduzidos
no interpretador antes da mudança:

| Atrito | Evidência antes |
| --- | --- |
| `//` é divisão, não comentário | `// comentário` na linha 1 → `Error at '//': Expect expression.` |
| operador no início da linha dentro de parênteses | `(\n 1\n + 2\n)` → `Error at '+': Expect ')' after expression.` |
| `fn` em método | `class A { fn m() {} }` → `Error at 'fn': Expect method name.` |
| união crua em `is` | `1 is Int \| y` compilava e devolvia `true` (parseado como tipo `Int \| y`) |
| mapa no início do statement | `{ "a": 1 }` → `Expect ';' after expression.` |
| bullet defasado na spec | dizia que `match` e funções anônimas não existiam |

A pergunta natural é por que o lado direito de `is` usa `|` (o token do OR bitwise) e não
`or`. A resposta é que `|` ali não é o operador bitwise: é o **construtor de união de
tipos**, o mesmo de `val x: Int | String` e de TypeScript/Scala. `or` é operador de
runtime (truthiness) e misturaria os dois níveis. O problema não é o token; é que, em
contexto de expressão, o mesmo `|` também existe como operador bitwise, então
`x is Int | y` tem duas leituras possíveis. Sem parênteses não há como decidir localmente.

## Decisão

1. **`//` onde se espera expressão** continua sendo erro de sintaxe, mas com diagnóstico
   dirigido: `Expect expression; '//' is integer division, and comments start with '#'.`
   Nenhuma mudança de gramática; `//` continua divisão inteira.
2. **Operador no início da linha dentro de `()`, `[]` e `{}` de expressão** passa a
   continuar a expressão, porque ali não existe statement novo para começar. Fora de
   brackets vale a regra do ADR-0011: o operador precisa terminar a linha. Um bloco
   (`{ ... }` de statement) é fronteira e reseta o contexto, para que `fn() { ... }`
   dentro de uma lista não transforme `-2` em subtração.
3. **`fn` é opcional antes de método** no corpo da classe: `fn m()` e `m()` produzem a
   mesma AST. A forma canônica continua sem `fn` (o corpo da classe já marca a
   declaração); a exceção existe para não surpreender quem vem de função livre.
4. **União no lado direito de `is` exige parênteses** em contexto de expressão:
   `x is (Int | String)` é válido; `x is Int | String` é erro com mensagem
   `Type unions in 'is' need parentheses: 'is (A | B)'.` Anotações (`: T | U`, `-> T | U`)
   e uniões dentro de `List[...]`/`Map[...]` continuam sem parênteses. `as` não muda:
   o parser ainda lê a união e o checker recusa (`as doesn't support union types`).
5. **Mapa no início do statement** ganha diagnóstico dirigido:
   `Unexpected ':'. Map literals can't start a statement; use 'val m = { ... }' or
   parentheses.` A gramática não muda; `{` no início do statement continua bloco.
6. **Bullet defasado da spec** é corrigido e protegido por `STALE_PHRASES` em
   `tests/test_docs_consistency.py`, para não voltar.

## Consequências

### Positivas

- As três armadilhas mais prováveis para quem vem de C agora explicam o que fazer.
- Formatar expressão longa dentro de parênteses, listas, mapas e argumentos deixa de ser
  proibido; o operador pode iniciar a linha, como em Rust/Prettier.
- `is` deixa de aceitar silenciosamente uma união que parecia OR bitwise.
- A assimetria "função livre exige `fn`, método proíbe" some.
- Nenhuma mudança semântica em runtime; tudo é parser/diagnóstico.

### Negativas / custos

- `fn` em método cria uma segunda grafia; a canônica é documentada e a AST é a mesma.
- Dentro de brackets, `a` em uma linha e `- b` na seguinte agora é subtração, não duas
  expressões. É o comportamento desejado para formatação, mas muda o erro que existia
  antes.
- `x is Int | y` que antes compilava (e podia dar `true`) agora é erro de sintaxe; é uma
  quebra deliberada de conveniência em favor de legibilidade.
- O parser ganha um estado (`_bracket_depth`) e um contexto a manter; o reset em `_block`
  é obrigatório para não vazar para statements dentro de lambdas.

### Neutras

- O diagnóstico de `as` com união continua sendo do checker, não do parser.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Trocar comentários para `//` e divisão inteira para `div`/`~/` | Quebra a herança Lox, todos os casos e a familiaridade; o problema é de mensagem, não de token. |
| Permitir operador no início da linha em qualquer lugar | Reintroduz a ambiguidade com `-2` no topo; o ganho é dentro de brackets. |
| Proibir `fn` em método e pronto | Mantém a surpresa; aceitar é uma linha de parser e não muda a AST. |
| Exigir parênteses para união em toda anotação | Ruído sem ambiguidade; anotação não tem expressão concorrente. |
| Fazer `as` também exigir parênteses | Mudaria um erro de checker em erro de parser sem necessidade; união em `as` já é recusada. |
| Deixar a spec como estava | O bullet contradizia a gramática e a suíte; spec que mente é pior que spec incompleta. |

## Como verificar

- `uv run python -m tests.runner division_comment` (exit 65, mensagem dirigida);
- `uv run python -m tests.runner leading_operator` (3, 7, 2, 7);
- `uv run python -m tests.runner method_fn` (7);
- `uv run python -m tests.runner is_union` (positivo com parênteses; negativo sem);
- `uv run python -m tests.runner map_at_statement` (exit 65, mensagem dirigida);
- `uv run pytest tests/test_parser.py` (AST de `(1\n + 2)`, união com parênteses e
  rejeição da união crua);
- `make check` (docs consistency + suíte completa).

## Referências

- [ADR-0011](0011-fn-elif-ponto-e-virgula.md) — regra do `;` opcional e operador no fim
  da linha.
- [ADR-0013](0013-ternario-nil-aware-escapes.md) — `??`/`?.` e recusa do elvis.
- [ADR-0025](0025-is-e-narrowing.md) — semântica de `is` e narrowing.
- [ADR-0066](0066-orcamento-e-gate-sintatico.md) — gate e orçamento que autorizam estas
  mudanças.
