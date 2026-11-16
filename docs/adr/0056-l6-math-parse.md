# ADR-0056 — L6f: `math.*`, `Int.parse` e `Float.parse`

- **Status:** accepted
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0029](0029-conversoes-math.md), [ADR-0047](0047-optionais-escalares-l2-5.md)
- **Implementação:** [`loxia_core/backend/lower_math.py`](../../loxia_core/backend/lower_math.py),
  [`runtime/numeric.c`](../../runtime/numeric.c)

## Decisão

- `math.abs/min/max/clamp` usam IR direto e promoção para Float quando qualquer operando
  é Float; `floor/ceil/round/trunc/sqrt` chamam helpers C determinísticos.
- `floor/ceil/round/trunc` devolvem `Int` e passam por `lox_float_to_int`, que valida
  NaN/Inf/range.
- `Int.parse`/`Float.parse` são funções C estritas (`[+-]?d+` e a forma decimal com
  expoente), devolvem `LoxValue` nil ou o valor; o lowering constrói o `T?` `{i1,T}`.
- `math.clamp` valida `low <= high` em panic site.

## Consequências

`casts_math.lox` promovido ao `l6`; nenhuma ABI existente muda.
