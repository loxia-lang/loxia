# ADR-0054 — L6d: tuplas boxeadas

- **Status:** accepted (tuplas básicas; `Any`/`is`/`as` de tupla e `for-in` de tupla pendentes)
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0052](0052-l6-listas.md), [ADR-0053](0053-l6-mapas.md)
- **Implementação:** [`loxia_core/backend/lower_tuples.py`](../../loxia_core/backend/lower_tuples.py),
  [`runtime/runtime.c`](../../runtime/runtime.c)

## Decisão

- Tupla é `LoxTuple {count, items}` na arena, com elementos boxeados e aridade fixa.
- O backend usa os tipos dos elementos publicados pelo checker para (des)boxear.
- Literal, índice, `len`, `==`/`!=`, `print`/`str`/`repr` e destructuring
  `val/var (a,b) = t` funcionam, inclusive aninhados.
- Igualdade é estrutural e promove números (`(1,"a") == (1.0,"a")`).
- Destructuring usa a anotação `(Int,String)` ou os tipos inferidos do literal.

## Limitações

- `is`/`as` com tupla, `Any` contendo tupla e `for-in` sobre tupla ainda são 65; entram na
  fatia de `Any`/narrowing.
- `tuple_iteration.lox` continua `PENDING`.

## Consequências

Casos promovidos: `tuples` e `tuple_destructure`.
