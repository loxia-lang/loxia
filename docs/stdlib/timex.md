---
title: std.timex
sources:
  - std/timex.lx
  - loxia/docgen.py
---

# std.timex

UTC date/time helpers over integer epoch seconds; no timezones.

## API

## Classes

### `class TimeError`

Failure to parse an ISO-8601 UTC instant.

#### `val kind: String`

Stable token: `invalidIso`.

#### `val message: String`

Detail without path/locale text.

#### `fn init(kind: String, message: String)`

Builds a parse failure.

## Functions

### `fn daysFromCivil(year: Int, month: Int, day: Int) -> Int`

Returns days since 1970-01-01 for a civil date.

Uses Howard Hinnant's proleptic-Gregorian algorithm. `month` is 1..12 and `day` is
1..31; invalid combinations are not rejected here.

### `fn civilFromDays(days: Int) -> (Int, Int, Int)`

Returns `(year, month, day)` for days since 1970-01-01.

Inverse of `daysFromCivil` and likewise proleptic Gregorian.

### `fn iso(seconds: Int) -> String`

Formats an instant (seconds since the epoch) as `YYYY-MM-DDTHH:MM:SSZ`.

Raises `RuntimeError` when the year falls outside 0..9999. The instant is floored
into its civil day, so pre-epoch values still format consistently.

### `fn parseIso(text: String) -> Int | Nil`

Parses a strict `YYYY-MM-DDTHH:MM:SSZ` string into seconds since the epoch.

Returns `nil` for malformed input; `parseIsoResult` preserves the cause.

### `fn parseIsoResult(text: String) -> Result[Int, TimeError]`

Parses an ISO-8601 UTC instant, preserving the cause of a malformed input.

Leap seconds are not accepted: `second` must be 0..59.

### `fn addDays(seconds: Int, days: Int) -> Int`

Adds `days` days to the instant `seconds` and returns the new instant.

Days are exactly 86400 seconds and there is no DST handling because the module is
UTC-only.

### `fn parts(seconds: Int) -> (Int, Int, Int, Int, Int, Int)`

Splits an instant into `(year, month, day, hour, minute, second)` UTC.

Uses floor division, so instants before the epoch still produce a valid civil date.
