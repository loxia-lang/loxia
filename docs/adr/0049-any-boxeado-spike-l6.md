# ADR-0049 — `Any` boxeado como spike do L6

- **Status:** accepted (spike; não é suporte geral a `Any`)
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0031](0031-backend-nativo.md), [ADR-0045](0045-narrowing-representacao.md),
  [ADR-0048](0048-abi-classes-l5.md), [`../../TODO.md`](../../TODO.md) §0.2
- **Implementação:** `src/backend/lower_model.py`, `lower_optionals.py`, `lower.py`,
  `runtime/runtime.c`, `tests/cases/any_box.lox`, `tests/cases/nil_aware.lox`

## Contexto

O L5 deixou `nil_aware.lox` em 65 porque o `??` de `c?.m(...)` com `"nada"` tem tipo
`Int | String`, e o backend não representava união. O L6 começa por `Any`/união, mas
antes de uma HIR ou de um sistema completo de uniões era preciso um spike pequeno:
uma representação dinâmica que fizesse esse caso e um `Any` explícito passarem, sem
comprometer a ABI do ADR-0048.

## Decisão

Adotar uma caixa **`{ i64 tag, i64 payload }`** (`ValueType.ANY`) apenas no caminho
dinâmico:

| tag | valor | payload |
| --- | --- | --- |
| 0 | `nil` | 0 |
| 1 | `Int` | i64 |
| 2 | `Float` | bits do double |
| 3 | `Bool` | 0/1 |
| 4 | `String` | `LoxStr*` |
| 5 | classe | descritor |
| 6 | instância | ponteiro da instância |
| 7 | função/método | closure |

- `UnionTy` com dois ou mais membros não-nulos, todos escalares/string, vira `ANY`.
- `Any` explícito vira `ANY`; `var x: Any = ...` boxeia, e atribuições seguintes
  reboxeiam.
- `??` cujo resultado é uma união boxeia os dois lados e devolve `ANY`.
- `print` de `ANY` chama `lox_print_any(tag, payload)`, que imprime sem endereço.
- O box é um valor de 16 bytes; não aloca no heap.
- Continua **65** para: operações/unbox implícito de `ANY`, `str`/interpolação de `ANY`,
  uniões com instância/classe/função, `as`/`is` sobre `ANY` e `Any` em campos.

## Consequências

### Positivas

- `nil_aware.lox` e um `Any` explícito básico passam no teste diferencial.
- A ABI de função/método/classe não muda; o box é um tipo de valor separado.
- Dá um ponto de medida real para decidir se HIR-lite é necessária.

### Negativas / limites

- Não é `Any` completo: não há unbox, dispatch dinâmico, igualdade nem casts.
- Um box por valor; sem otimização de escape.
- `UnionTy` só aceita escalares/string; classes e funções ficam para o L6 completo.
- `lox_print_any` conhece tags; mudá-las é mudança de ABI interna (há teste).

## Alternativas

| Alternativa | Por que não agora |
| --- | --- |
| união tipada por membro (struct por combinação) | explosão de layouts e de coerções antes de saber se precisamos |
| HIR-lite primeiro | o spike mostra que a representação cabe sem HIR; a decisão de HIR fica separada |
| manter `nil_aware` em 65 | não mede o custo real de união/`Any` |

## Critérios para revisitar

- Se `Any` precisar de igualdade/`as`/`is`, criar um caminho de unbox explícito.
- Se uniões com classe/instância/função entrarem, decidir tags e `lox_print_any`.
- Se o box aparecer em caminho quente, medir e considerar HIR/SSA ou especialização.
