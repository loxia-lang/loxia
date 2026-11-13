# ADR-0030 — Tuplas: sintaxe escolhida, implementação pós-1.0

- **Status:** accepted (pós-1.0); sintaxe e semântica **implementadas** na v1 pelo
  [ADR-0036](0036-tuplas-implementacao.md). `for-in`/`is` seguem adiados.
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0007](0007-ranges-e-iteracao.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [ADR-0021](0021-tipos-de-funcao.md),
  [ADR-0026](0026-freeze-1.0.md), [`../../TIPOS.md`](../../TIPOS.md),
  [`../../TODO.md`](../../TODO.md) §11, [`../../IDEIAS.md`](../../IDEIAS.md)

## Contexto

Funções no Lox devolvem um valor. Múltiplos valores hoje exigem uma classe ou uma lista
heterogênea (`List[Any]`). Tupla resolve isso de forma estrutural, mas adiciona:

- tipo novo (`TupleTy`) e unificação com generics;
- literal e ambiguidade com agrupamento `(expr)`;
- indexação e destructuring;
- layout/ABI no backend e igualdade/stringify.

O freeze da 1.0 não inclui tuplas. A sintaxe precisa ser decidida agora para não inventar
um dialeto depois, mas a implementação fica para depois do backend/1.0.

## Decisão

### Sintaxe

```lox
val par: (Int, String) = (1, "a")
print par[0]
val (n, s) = par

fn divmod(a: Int, b: Int) -> (Int, Int) {
  return (a // b, a % b)
}
```

- Literal: `(a, b)`; tipo: `(A, B)`. Parênteses continuam agrupamento quando não há
  vírgula.
- **Sem unit `()` e sem 1-tuple `(x,)`** na primeira versão: evita trailing comma, unidade
  e ambiguidade com parênteses. Tuplas têm 2+ elementos.
- Acesso: `t[0]`, `t[1]`, ...; reusa a indexação existente, sem `.0` no lexer/parser.
- Destructuring: `val (a, b) = t`; `var` destructuring fica para depois.
- Elementos imutáveis; `var t = ...` pode reatribuir o binding, mas `t[0] = x` é erro.
- `==` estrutural; `str`/`repr` formatam `(1, "a")`; `len(t)` funciona.
- `for x in t` e `is (A, B)` ficam para depois (heterogêneo/checagem de elementos).
- Tipos de função podem retornar/receber tuplas; generics podem usar `(T, U)`.

### Implementação (quando entrar)

1. `TupleTy(items)` no `ty.py` e unificação.
2. `TupleLiteral`/`TupleType` no AST/parser; precedência de vírgula em chamadas.
3. Indexação com literal constante (tipo exato) ou índice dinâmico (união dos elementos,
   com bounds em runtime).
4. Destructuring no `val` (checker/definição).
5. Runtime: tuple Python imutável, `stringify`/igualdade/`len`.
6. Backend: layout fixo, monomorfização e retorno múltiplo.

## Consequências

- A sintaxe não entra no freeze; não há código nem teste até a decisão de implementar.
- `val (a, b) = t` exige um nó de destructuring ou um caminho especial no `var`.
- O backend não precisa de tuplas para o MVP; a ausência dói menos que `math`/casts.
- Se tuplas entrarem antes do backend, o layout fica congelado cedo; por isso a ordem
  escolhida é pós-1.0/backend.

## Alternativas rejeitadas

- `[a, b]`: já é lista homogênea.
- `t.0`: exige número após `.` no lexer/parser e não reusa indexação.
- `a, b` sem parênteses: ambíguo em chamadas/return/declarações.
- Unit/1-tuple: pouco valor no MVP e mais regras.
- Classes/`Pair`: verboso e não estrutural.
