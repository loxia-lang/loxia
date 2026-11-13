# ADR-0057 — L6g: função com defaults como valor

- **Status:** accepted
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0046](0046-closures-celulas-l4.md), [ADR-0050](0050-monomorfizacao-t7.md)
- **Implementação:** [`src/backend/lower_variables.py`](../../src/backend/lower_variables.py),
  [`src/backend/lower_calls.py`](../../src/backend/lower_calls.py)

## Decisão

- `Value` e `Binding` carregam o `FunctionInfo` quando o valor é uma função conhecida.
- `val f = soma` preserva `FunctionInfo` e defaults; a chamada indireta preenche os
  defaults no call site, como a chamada direta já fazia.
- A assinatura da closure continua `(env, params...)`; nenhum thunk novo.

## Limitação

- Defaults precisam ser expressões lowering no call site (o comportamento atual do L4);
  funções genéricas como valor continuam 65.

## Consequências

`defaults_as_value.lox` promovido ao `l6`.
