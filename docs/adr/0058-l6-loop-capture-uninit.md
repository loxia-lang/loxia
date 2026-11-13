# ADR-0058 — L6h: captura por iteração, variável que começa nil e índice de `Any`-tupla

- **Status:** accepted
- **Data:** 2026-11-13
- **Implementação:** [`src/backend/lower_range.py`](../../src/backend/lower_range.py),
  [`src/backend/lower_variables.py`](../../src/backend/lower_variables.py),
  [`src/backend/lower_containers.py`](../../src/backend/lower_containers.py)

## Decisão

- `for-in` capturado aloca uma **célula nova por iteração**; cada closure leva o ponteiro
  da célula daquela iteração, não um slot compartilhado.
- Variável anotada não opcional sem inicializador vira `Any` por enquanto (preserva
  `nil` até a primeira atribuição); funções mantêm o tipo `fn` com ponteiro nulo.
- Índice de `Any` faz despacho de tag para tupla em runtime; `tuple_iteration` passa a
  funcionar com narrowing do checker.

## Consequências

Casos promovidos: `for_in_capture`, `var_uninitialized_int`, `tuple_iteration`.
