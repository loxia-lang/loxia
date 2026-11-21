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

Failure to parse an ISO-8601 UTC instant or to build a civil date.

#### `val kind: String`

Stable token: `invalidIso` or `invalidDate`.

#### `val message: String`

Detail without path/locale text.

#### `fn init(kind: String, message: String)`

Builds a failure.

## Functions

### `fn daysFromCivil(year: Int, month: Int, day: Int) -> Int`

Returns days since 1970-01-01 for a civil date.

Uses Howard Hinnant's proleptic-Gregorian algorithm. `month` is 1..12 and `day` is
1..31; invalid combinations are not rejected here (use `date` for that).

### `fn civilFromDays(days: Int) -> (Int, Int, Int)`

Returns `(year, month, day)` for days since 1970-01-01.

Inverse of `daysFromCivil` and likewise proleptic Gregorian.

### `fn isLeapYear(year: Int) -> Bool`

Returns whether `year` is a leap year in the proleptic Gregorian calendar.

### `fn daysInMonth(year: Int, month: Int) -> Int`

Returns the number of days in `month` of `year` (28..31).

`month` is expected to be 1..12; the result is undefined outside that range.

### `fn date(year: Int, month: Int, day: Int) -> Result[(Int, Int, Int), TimeError]`

Validates a civil date and returns it as `(year, month, day)`.

`year` must be 0..9999 (the formatting range), `month` 1..12 and `day` within the
month. Invalid input is `Result.Err(TimeError("invalidDate", ...))`.

### `fn iso(ms: Int) -> String`

Formats an instant (milliseconds since the epoch) as `YYYY-MM-DDTHH:MM:SSZ`.

Raises `RuntimeError` when the year falls outside 0..9999. The instant is floored
into its civil day and the milliseconds are truncated, so pre-epoch values still
format consistently (`-1` ms is `1969-12-31T23:59:59Z`).

### `fn isoMillis(ms: Int) -> String`

Formats an instant as `YYYY-MM-DDTHH:MM:SS.mmmZ`.

Like `iso`, but keeps the three millisecond digits (floored, so `-1` ms is
`1969-12-31T23:59:59.999Z`).

### `fn isoDate(ms: Int) -> String`

Formats the civil date of an instant as `YYYY-MM-DD`.

### `fn isoIn(ms: Int, offsetMinutes: Int) -> String`

Formats an instant in an explicit offset, e.g. `2024-01-01T00:00:00+03:00`.

`offsetMinutes` is `-720..840`; zero formats as `Z`. The instant is shifted before
formatting, so the civil fields are the local ones at that offset.

### `fn parts(ms: Int) -> (Int, Int, Int, Int, Int, Int)`

Splits an instant into `(year, month, day, hour, minute, second)` UTC.

Uses floor division, so instants before the epoch still produce a valid civil date;
milliseconds are dropped.

### `fn partsIn(ms: Int, offsetMinutes: Int) -> (Int, Int, Int, Int, Int, Int)`

Splits an instant into civil fields at an explicit offset.

`offsetMinutes` is `-720..840`; the returned fields are local to that offset.

### `fn weekday(ms: Int) -> Int`

Returns the ISO weekday of an instant: 1 = Monday … 7 = Sunday.

### `fn dayOfYear(ms: Int) -> Int`

Returns the day of the year of an instant: 1..365 (366 in a leap year).

### `fn addDays(ms: Int, days: Int) -> Int`

Adds `days` days of exactly 86.400.000 ms to an instant.

### `fn addMonths(ms: Int, months: Int) -> Int`

Adds calendar months to an instant, clamping the day to the target month.

The time of day is preserved. `2024-01-31 + 1 month` is `2024-02-29`, and
`2024-03-31 - 1 month` is `2024-02-29`; the operation is not invertible at month
ends (that is the price of a calendar month, not a 30-day duration).

### `fn addYears(ms: Int, years: Int) -> Int`

Adds calendar years to an instant, clamping 29 February in a non-leap year.

Equivalent to `addMonths(ms, years * 12)`.

### `fn diffDays(a: Int, b: Int) -> Int`

Returns the difference `a - b` in civil days (floor), not in 24 h periods.

### `fn parseIso(text: String) -> Int | Nil`

Parses an ISO-8601 instant string into milliseconds since the epoch.

Returns `nil` for malformed input; `parseIsoResult` preserves the cause.

### `fn parseIsoResult(text: String) -> Result[Int, TimeError]`

Parses an ISO-8601 instant, preserving the cause of a malformed input.

Accepts `YYYY-MM-DD` (midnight UTC) and
`YYYY-MM-DDTHH:MM:SS[.mmm](Z|+HH:MM|-HH:MM)`; `t`/`z` may be lowercase. The
fraction is 1..3 digits (`.5` is 500 ms) and more than three is rejected. Leap
seconds are not accepted: `second` must be 0..59. The returned instant is UTC.
