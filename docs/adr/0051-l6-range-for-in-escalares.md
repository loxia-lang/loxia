# ADR-0051 — L6a: Range, `for-in` e operações escalares restantes

- **Status:** accepted (primeira fatia do L6; containers/tuplas/Any/enums/exceções pendentes)
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0031](0031-backend-nativo.md), [ADR-0047](0047-optionais-escalares-l2-5.md),
  [ADR-0050](0050-monomorfizacao-t7.md), [`../../TODO.md`](../../TODO.md) §6
- **Implementação:** [`loxia_core/backend/lower_range.py`](../../loxia_core/backend/lower_range.py),
  [`runtime/containers.c`](../../runtime/containers.c), [`loxia_core/backend/lower.py`](../../loxia_core/backend/lower.py)

## Contexto

O L6 começa pelas operações que não dependem de containers: `Range` como valor,
`for-in` sobre Range/String e as operações escalares que ficaram para o L6 (`**`, bits,
shifts, `as` numérico). Elas fecham casos do corpus sem decidir a representação de
`List`/`Map`.

## Decisão

- `Range` é um ponteiro para `LoxRange {start, end, step}` na arena; `print`, `str` e
  igualdade estrutural usam funções do runtime.
- `for i in range` é lowering direto para um laço com `alloca` do índice, condição
  dependente do sinal do step e corpo no escopo do laço. `for c in "..."` usa
  `lox_str_len`/`lox_str_char_at` (code points UTF-8).
- `**`: `Int ** Int` usa `lox_int_pow` (wrapping, expoente negativo é panic); os demais
  casos numéricos chamam `pow` de C.
- Bits (`& | ^ ~`) são IR direto sobre `i64`; shifts usam `lox_shift`, que valida
  `0..63` e implementa `<<`, `>>` aritmético e `>>>` lógico.
- `Int as Float` é `sitofp`; `Float as Int` passa por `lox_float_to_int`, que rejeita
  NaN/Inf/fora do range i64.
- `Int.parse`/`Float.parse`/`math.*` e `chars` continuam 65 explícito: dependem das
  decisões de containers/`Any` ou de uma tabela de nativas que ainda não existe.

## Consequências

- Casos promovidos: `range_value`, `for_in`, `one_line_block`, `optional_semicolons`,
  `bitwise`, `bitwise_precedence`, `exponentiation`.
- `for_in_capture` e `var x: Int;` continuam `PENDING`: exigem célula nova por iteração e
  representação de variável que começa `nil`, decisões da fatia de containers/unificação.
- A ABI existente não muda; Range é um valor ponteiro novo.
