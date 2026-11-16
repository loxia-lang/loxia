# ADR-0069 — Destructuring aninhado

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0030](0030-tuplas.md), [ADR-0036](0036-tuplas-implementacao.md),
  [ADR-0059](0059-i4-check-limpo-compila.md),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md)
- **Implementação:** `loxia_core/frontend/destructuring.py` (padrões),
  `loxia_core/frontend/parser.py`, `loxia_core/execution/interpreter.py`,
  `loxia_core/semantics/{resolver,checker}.py`, `loxia_core/frontend/ast_printer.py`,
  `loxia_core/backend/{captures,lower_tuples}.py`; casos
  `tests/cases/nested_destructure.lox`, `tests/cases/errors/nested_destructure_*.lox`;
  testes em `tests/test_parser.py`, `tests/test_ast_printer.py`,
  `tests/test_interpreter.py` e `tests/test_checker.py`

## Contexto

Tuplas aninham desde o [ADR-0036](0036-tuplas-implementacao.md) (`(Int, (String, Bool))`),
mas o destructuring só aceitava nomes no primeiro nível: `val (a, (b, c)) = t` era erro de
sintaxe. Quem tinha um par dentro de um par precisava de duas linhas:

```lox
val (a, par) = t
val (b, c) = par
```

Isso é exatamente o tipo de atrito que a linguagem deve remover sem criar grafia nova: o
padrão à esquerda do `=` é a **mesma** construção recursiva do literal.

Durante a implementação apareceu um buraco anterior no I4: uma closure que captura uma
variável vinda de destructuring passava no `--check` e falhava no lowering com
`Undefined variable 'a'.` (o passe de captura ignorava `Destructure`). O caso ficou
coberto junto.

## Decisão

1. **O padrão é recursivo**: `pattern → IDENTIFIER | "(" pattern ("," pattern)+ ")"` em
   `val`/`var`. `val (a, (b, c)): (Int, (Int, String)) = (1, (2, "x"))` funciona, em
   qualquer profundidade, com a mesma anotação de tipo recursiva.
2. **Sem nova forma de escrever**: não existe `a, b = t` nem `val [a, b] = ...`; a forma
   canônica continua `val (…) = …`, agora aninhável.
3. **Erros são locais ao nível**: cada `TuplePattern` checa a aridade e o tipo do valor
   daquela posição. Mensagem unificada entre checker e interpretador (padrão primeiro):
   `Destructuring expects 2 values, found 3.`, `Can only destructure a tuple.`,
   `Can only destructure tuples, found Int.`
4. **`_` não é curinga no destructuring**: continua sendo um identificador comum (o
   `_` de `match` é outro contexto). Quem não quer o valor usa um nome.
5. **Lowering recursivo e captura corrigida**: cada nome vira slot/célula como uma
   variável normal; o passe de captura declara os nomes do padrão, então closure que os
   usa recebe célula. Sem lowering silencioso: união de tuplas ou `Any` continuam
   `not supported by the backend yet`.
6. **O tipo do literal de tupla passa a ser publicado no `_check`** quando ele é checado
   contra uma anotação — sem isso o lowering não sabia o tipo do aninhamento (mesmo
   motivo já documentado para lambda no ADR-0046).

## Consequências

### Positivas

- Uma expressão/declaração a menos no caso comum de `Map`/par dentro de par.
- Zero grafia nova, zero nível de precedência, zero regra de newline: o parser só
  recursa onde já havia `(`.
- O I4 fica mais honesto: destructuring aninhado compila igual ao interpretado, inclusive
  com closure capturando nome destruturado.
- O padrão ganha um módulo próprio (`destructuring.py`), separado dos padrões de `match`.

### Negativas / custos

- A AST `Destructure` mudou de `names: list[Token]` para `pattern`; todo consumidor
  (printer, resolver, checker, intepreter, captura, lowering) passou a recursar.
- Uma anotação de tipo recursiva é obrigatória quando o valor é `Any`; sem ela o erro é
  o mesmo de antes.
- Mensagem de aridade do `--check` mudou de ordem (`expects 2, found 3` em vez de
  `expects 3, found 2`) para bater com o runtime; um teste foi atualizado porque a
  mensagem antiga dizia o contrário do runtime.

### Neutras

- O orçamento sintático não muda: nenhuma keyword, nenhum nível, nenhuma forma de
  statement/declaração.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter só o primeiro nível | Obriga variável intermediária justamente quando a tupla aninha — que é o caso de `Map`/par. |
| Aceitar `[a, b]` para desestruturar lista | Segunda forma e semântica nova (lista é mutável); o padrão é de tupla. |
| `_` como descarte | Cria duas leituras para o mesmo token (`_` variável vs curinga); `match` já usa `_` com outro significado. |
| Resto (`(a, ...resto)`) | Precisa de tipo de "resto" e de lowering novo; não há dor demonstrada. |
| Inferir o tipo do destructuring no backend | Violaria o I4 (fonte única é o checker); o tipo é publicado por ele. |

## Como verificar

- `uv run python -m tests.runner nested` (golden do aninhamento e dos erros);
- `uv run pytest tests/test_parser.py -k nested`, `tests/test_ast_printer.py`,
  `tests/test_interpreter.py -k tuple`, `tests/test_checker.py -k tuple`;
- `uv run pytest tests/test_backend.py` (caso `nested_destructure.lox` no corpus L6,
  incluindo closure que captura nome destruturado);
- `make check`.

## Referências

- [ADR-0036](0036-tuplas-implementacao.md) — tuplas no interpretador/checker.
- [ADR-0046](0046-closures-celulas-l4.md) — células e captura por closure.
- [ADR-0059](0059-i4-check-limpo-compila.md) — checker como fonte única dos tipos.
- [ADR-0066](0066-orcamento-e-gate-sintatico.md) — gate sintático.
