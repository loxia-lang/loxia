---
title: std.fmt
sources:
  - std/fmt.lx
  - loxia/docgen.py
---

# std.fmt

Formatting helpers (templates, padding, numbers, byte sizes).

## API

## Functions

### `fn format(template: String, ...values: Any) -> String`

Replaces `{}` placeholders in `template` with successive values.

### `fn pad(text: String, width: Int, fill: String = ...) -> String`

Pads `text` to `width` using `fill` (one character).

### `fn commas(value: Int) -> String`

Formats an integer with thousands separators.

### `fn fixed(value: Float, digits: Int) -> String`

Formats a finite float with exactly `digits` decimal places.

### `fn percent(value: Float, digits: Int = ...) -> String`

Formats a float as a percentage with `digits` decimal places.

### `fn bytes(value: Int) -> String`

Formats a byte count with a binary unit (B, KiB, MiB, ...).
