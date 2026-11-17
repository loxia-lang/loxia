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

Returns the 32-bit FNV-1a hash of the UTF-8 bytes of `text`.

The result is masked to 0..4294967295, so it is never negative.

### `fn fnv1a64(text: String) -> Int`

Returns the 64-bit FNV-1a hash of the UTF-8 bytes of `text`.

The result is the i64 bit pattern and may be negative; compare it as an `Int`, not
as an unsigned value.

### `fn djb2(text: String) -> Int`

Returns the 32-bit djb2 hash of the UTF-8 bytes of `text`.

The result is masked to 0..4294967295, so it is never negative.
