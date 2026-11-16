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

Conta os bytes UTF-8 de `text` (1..4 por code point).

### `fn utf16Len(text: String) -> Int`

Conta as unidades UTF-16 de `text` (2 para code points acima de U+FFFF).

### `fn utf16Column(text: String, index: Int) -> Int`

Largura UTF-16 do prefixo de `index` code points; `index` é limitado a 0..len(text).
