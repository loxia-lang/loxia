---
title: std.utf8
sources:
  - std/utf8.lx
  - loxia/docgen.py
---

# std.utf8

UTF-8 and UTF-16 widths (bytes, code units, columns).

## API

## Functions

### `fn byteLen(text: String) -> Int`

Counts the UTF-8 bytes of `text` (1..4 per code point).

### `fn utf16Len(text: String) -> Int`

Counts the UTF-16 code units of `text` (2 for code points above U+FFFF).

### `fn utf16Column(text: String, index: Int) -> Int`

Returns the UTF-16 width of the prefix of `index` code points.

`index` is clamped to 0..len(text), so negative and out-of-range values do not raise.
