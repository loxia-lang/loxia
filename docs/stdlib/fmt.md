---
title: std.fmt
sources:
  - std/fmt.lx
  - loxia/docgen.py
---

# std.fmt

Locale-free formatting helpers (templates, padding, numbers, byte sizes).

## API

## Functions

### `fn format(template: String, ...values: Any) -> String`

Replaces each `{}` placeholder with the next value rendered by `str`.

`{{` and `}}` produce literal braces. Raises `RuntimeError` for a malformed
placeholder (such as a lone `{` or `}`) or when the number of values does not match
the number of placeholders.

### `fn pad(text: String, width: Int, fill: String = ...) -> String`

Left-pads `text` to `width` using repeated `fill`.

`fill` must be exactly one code point. Text that is already at least `width` long is
returned unchanged. A negative width or a multi-character fill raises `RuntimeError`.

### `fn commas(value: Int) -> String`

Formats an integer with `,` thousands separators.

Negative values keep a leading `-`; the sign itself is never grouped. `commas(0)` is
`"0"` and the output is independent of locale.

### `fn fixed(value: Float, digits: Int) -> String`

Formats a finite `Float` with exactly `digits` decimal places.

Rounds with `math.round` and pads the fraction with zeros. `digits` must be in
0..15 and the value must be finite; otherwise `RuntimeError` is raised. With
`digits == 0` the result has no decimal point.

### `fn percent(value: Float, digits: Int = ...) -> String`

Formats a value as a percentage with `digits` decimal places.

Multiplies by 100, formats with `fixed` and appends `%`, so the same digit and
finiteness rules apply.

### `fn bytes(value: Int) -> String`

Formats a byte count with a binary unit (`B`, `KiB`, `MiB`, `GiB` or `TiB`).

Scales by 1024 and uses one decimal place above `B`. Negative input raises
`RuntimeError`; `bytes(0)` is `"0 B"`.
