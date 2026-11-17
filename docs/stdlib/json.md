---
title: std.json
sources:
  - std/json.lx
  - loxia/docgen.py
---

# std.json

RFC 8259 JSON with insertion-ordered objects and a 16-level nesting cap.

## API

## Functions

### `fn parse(text: String) -> Any`

Parses RFC 8259 JSON text into Loxia values.

Accepts `null`, booleans, numbers, strings, arrays and objects. A number without a
fraction or exponent stays `Int` when it fits, otherwise it becomes `Float`;
non-finite values are rejected. Objects preserve key order and a repeated key keeps
the last value. Invalid input (bad escapes, trailing characters, nesting deeper than
16) returns `nil`; a valid JSON `null` also returns `nil`.

### `fn stringify(value: Any) -> String`

Serializes a Loxia value as compact JSON.

Supports `nil`, `Bool`, `Int`, `Float`, `String`, `List[Any]` and
`Map[String, Any]`. `Int` is emitted without a decimal point and `Float` with one;
a non-finite float raises `RuntimeError`. Object keys keep insertion order, and any
other type raises `RuntimeError`.

### `fn pretty(value: Any, indent: Int = ...) -> String`

Serializes a Loxia value as indented JSON.

Uses `indent` spaces per nesting level and the same value rules as `stringify`.
`indent <= 0` falls back to compact output. Non-empty containers are always broken
across lines; empty ones render as `[]` or `{}`.
