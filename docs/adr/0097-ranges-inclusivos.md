# ADR-0097 — Ranges inclusivos (`..=`)

- **Status:** accepted (implementado em 2026-11-16)
- **Data:** 2026-11-16
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0007](0007-ranges-e-iteracao.md) (ranges e `for-in`),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate sintático),
  [ADR-0041](0041-enums-match.md)/[ADR-0082](0082-iterador-de-usuario.md) (iteração),
  [`../../IDEIAS.md`](../../IDEIAS.md) I-6
- **Implementação:** `DOT_DOT_EQUAL` no scanner/parser, `Range(inclusive=...)` no AST,
  `LoxRange.inclusive`, `lox_range_new(..., inclusive)` e `lox_range_inclusive` no runtime;
  golden `tests/cases/range_inclusive.lx` (`l2`)

## Contexto

O range atual `a..b` é **half-open** (ADR-0007): inclui `a` e exclui `b`. Para incluir `b`
o usuário escreve `a..b + 1`, que (a) não expressa intenção, (b) erra em `b == INT_MAX`
por overflow e (c) não tem forma canônica para "até o fim". O gate do ADR-0066 pedia
quatro respostas antes de adicionar sintaxe; o I-6 listou `..=` como pendência real.

## Decisão

Adicionar **`a..=b`**, range inclusivo só de `Int`, com precedência idêntica a `..` e
step 1.

### Semântica

- `a..=b` itera `a, a+1, …, b` (fim incluído); `a > b` gera range vazio.
- `..=` não tem passo: `range(a, b, step)` continua exclusivo e com passo (não há
  `range` inclusivo com passo; quem precisa combina `range` + condição explícita).
- `Range` compara `inclusive` junto de `start`/`end`/`step`: `(1..2) != (1..=2)`.
- Impressão: `<range 1..=3>`; igualdade e `for-in` respeitam a flag.
- Em `INT_MAX..=INT_MAX` o corpo roda uma vez e o laço encerra **sem** incrementar
  (guarda contra wrap): o `advance` do backend compara o valor atual com `end` antes de
  continuar quando o range é inclusivo.
- `..=` é só açúcar de iteração; não muda `len` (ranges não têm `len`) nem indexação.

### Gate sintático (ADR-0066)

1. **Substitui uma grafia existente?** Substitui o workaround `a..b + 1`, que não é
   canônico e erra no limite; `..` continua sendo o half-open.
2. **É decidível localmente?** Sim: token `..=` (três caracteres), sem ambiguidade com
   `..` nem com `...`; o parser decide no mesmo ponto de `_range`.
3. **Cabe na precedência atual?** Sim, mesmo nível de `..` (entre `&` e `shift`).
4. **Tem uma forma canônica?** Sim: `..=` é a única forma de range inclusivo; `a..b + 1`
   continua válido, mas não é a grafia recomendada.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `a..b + 1` como padrão | não expressa intenção; overflow em `INT_MAX`; sem forma canônica |
| `range(a, b, step)` inclusivo | mistura passo e inclusão; `range` é primitiva, não sintaxe |
| `a...b` (três pontos) | já é variádico/spread; colidiria |
| Só `..=` com passo opcional | passo + inclusão é raro e complica o lowering; fica fora |
| Adiar de novo | a dor é concreta (`for i in 0..n` para "até n") e o custo é baixo |

## Consequências

### Positivas

- intenção explícita e correta no limite `INT_MAX`;
- zero custo de runtime: um `int32_t` no `LoxRange` e uma comparação a mais no laço;
- `..` e `range()` não mudam (compatibilidade total).

### Negativas

- mais um token/operator na gramática e na doc;
- `Range` ganha um campo (ABI interna do runtime mudou; binários antigos não são
  relevantes, o cache é por hash de fontes);
- passo + inclusão não existe; quem precisa usa `range` com condição.

## Como verificar

- `tests/cases/range_inclusive.lx` no corpus `l2`, interpretado e compilado (I1).
- `tests/test_editor_grammar.py` cobre o token novo (`make grammar`).
- Casos: fim incluído, `start > end` vazio, `INT_MAX..=INT_MAX` uma iteração, igualdade
  distinta de `..`, `range()` inalterado.
