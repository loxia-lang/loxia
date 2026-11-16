---
title: std.hash
sources:
  - std/hash.lx
  - loxia/docgen.py
---

# std.hash

Non-cryptographic hashes (FNV-1a, djb2) over UTF-8 bytes.

## API

## Functions

### `fn fnv1a32(text: String) -> Int`

FNV-1a de 32 bits (0..4294967295) dos bytes UTF-8 de `text`.

### `fn fnv1a64(text: String) -> Int`

FNV-1a de 64 bits dos bytes UTF-8; devolve o padrão de bits em i64 (pode negar).

### `fn djb2(text: String) -> Int`

djb2 de 32 bits (0..4294967295) dos bytes UTF-8 de `text`.
