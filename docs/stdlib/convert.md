---
title: std.convert
sources:
  - std/convert.lx
  - loxia/docgen.py
---

# std.convert

Text conversions (integer/float/bool, Base64, hex).

## API

## Functions

### `fn toInt(text: String) -> Int | Nil`

Parses a decimal integer, returning `nil` when invalid.

### `fn toFloat(text: String) -> Float | Nil`

Parses a decimal float, returning `nil` when invalid.

### `fn toBool(text: String) -> Bool | Nil`

Parses `true`/`false` (case-insensitive), returning `nil` when invalid.

### `fn base64Encode(text: String) -> String`

Encodes UTF-8 text as standard Base64.

### `fn base64Decode(text: String) -> String | Nil`

Decodes standard Base64, returning `nil` when invalid.

### `fn hexEncode(text: String) -> String`

Encodes UTF-8 text as lowercase hexadecimal.

### `fn hexDecode(text: String) -> String | Nil`

Decodes lowercase or uppercase hexadecimal, returning `nil` when invalid.
