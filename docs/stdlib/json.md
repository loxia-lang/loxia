---
title: std.json
sources:
  - std/json.lx
  - loxia/docgen.py
---

# std.json

RFC 8259 JSON with insertion-ordered objects.

## API

## Functions

### `fn parse(text: String) -> Any`

Parses JSON text into Loxia values, returning `nil` for invalid input.

### `fn stringify(value: Any) -> String`

Serializes a Loxia value as compact JSON.

### `fn pretty(value: Any, indent: Int = ...) -> String`

Serializes a Loxia value as JSON with `indent` spaces.
