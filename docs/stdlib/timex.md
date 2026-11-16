---
title: std.timex
sources:
  - std/timex.lx
  - loxia/docgen.py
---

# std.timex

UTC date/time helpers (no timezone).

## API

## Functions

### `fn daysFromCivil(year: Int, month: Int, day: Int) -> Int`

Dias desde 1970-01-01 para a data civil (algoritmo de Howard Hinnant).

### `fn civilFromDays(days: Int) -> (Int, Int, Int)`

Data civil `(ano, mês, dia)` para dias desde 1970-01-01.

### `fn iso(seconds: Int) -> String`

Formata o instante (segundos desde a época) como `YYYY-MM-DDTHH:MM:SSZ`.

### `fn parseIso(text: String) -> Int | Nil`

Lê `YYYY-MM-DDTHH:MM:SSZ` estrito; devolve `nil` se inválido.

### `fn addDays(seconds: Int, days: Int) -> Int`

Soma `days` dias ao instante `seconds`, devolvendo o novo instante.

### `fn parts(seconds: Int) -> (Int, Int, Int, Int, Int, Int)`

Decompõe o instante em `(ano, mês, dia, hora, minuto, segundo)` UTC.
