# ADR-0098 — Property-based testing (`std.property`)

- **Status:** accepted (implementado em 2026-11-16)
- **Data:** 2026-11-16
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0096](0096-testes-biblioteca-e-runner.md) (`std.test`/`loxia test`),
  [ADR-0097](0097-ranges-inclusivos.md), `std.rand` (T3), [`../../IDEIAS.md`](../../IDEIAS.md) I-13
- **Implementação:** `std/property.lx`, golden `tests/cases/std_property.lx` (`t2`),
  `docs/stdlib/property.md` gerado

## Contexto

O `std.test` já tem `it/expect/skip` e o `loxia test` roda arquivos isolados. Faltava
testar **propriedades** (para todo valor gerado, a afirmação vale), e o I-13 listava
property-based como pendência. O `std.rand` (ADR-0097/T3) deu a base determinística: um
PRNG com semente explícita, sem relógio.

## Decisão

### API

```lox
from std.property import forAll, intRange
from std.test import expect

forAll(intRange(1, 100), fn(n: Int) {
  expect(n + 1 > n).toBe(true)
})
```

- `Gen[T]` guarda `generate: fn(Rand) -> T` e `shrink: fn(T) -> List[T]`.
- `forAll[T](generator, check, runs = 100, seed = 0)`: executa `check` para cada valor;
  falha vira `TestFailure` com contador de execuções, seed, contraexemplo e o menor
  contraexemplo encontrado pelo shrinking.
- Geradores: `int`, `intRange(min, max)`, `bool`, `float`, `stringOf(maxLength)`,
  `listOf[T]`, `oneOf(options)`; `listOfInt`/`listOfString` ficam como aliases.
- Shrinking limitado a 100 rodadas por falha, sempre na direção de um valor "menor"
  (0/min, lista/string menor).

> **Atualização (2026-11-16):** `listOf[T]` foi implementado e o
> [E4001](../../TODO.md) de `Gen[List[T]]` deixou de existir — o lowering propaga o
> `type_subst` para lambdas aninhadas. `listOfInt`/`listOfString` continuam como aliases
> de compatibilidade.

### Determinismo

- `seed` padrão **0**; a mensagem de falha imprime a seed para reproduzir.
- Mesma seed + mesmo `runs` + mesma propriedade ⇒ mesma sequência e mesmo contraexemplo
  nos dois motores (I1).
- Nada de timestamp, hash de processo ou ordem de `Map` no relatório.

### Integração

- `forAll` roda dentro de `suite.it`; a falha é `TestFailure` e o `loxia test` a reporta
  como `not ok` (TAP).
- `Skip` lançado pela propriedade **não** é contado como falha: `forAll` re-lança.
- Erro de runtime dentro do `check` conta como falha da propriedade (o shrinking também
  o reproduz).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Sem shrinking | O contraexemplo gerado pode ser enorme; reduzir é o que torna a falha útil. |
| Shrinking configurável por propriedade | Mais superfície; o `Gen` já carrega a estratégia. |
| Seed via `loxia test --seed` | O runner não precisa saber de propriedades; seed por `forAll` é local e reproduzível. |
| Geradores genéricos de lista (`listOf[T]`) | **Implementado** em 2026-11-16: o backend propaga o `type_subst` para lambdas aninhadas; `listOfInt`/`listOfString` ficam como aliases. |

## Consequências

### Positivas

- Falhas reproducíveis e mínimas, sem dependência de tempo.
- Reusa `std.test`/`loxia test` e o TAP existente.
- `std.rand` já estava pronto; nenhum kernel novo.

### Negativas

- Shrinking é por gerador e limitado; não é o minimalismo global do Hypothesis.
- O relatório é uma string TAP; sem integração com cobertura.

## Como verificar

- `tests/cases/std_property.lx` (`t2`): passa, falha de Int com shrink para `1` e falha
  de lista com shrink para `[]`, nos dois motores.
- `make check` verde e `docs/stdlib/property.md` gerado.
