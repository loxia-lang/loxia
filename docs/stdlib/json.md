---
title: std.json
sources:
  - std/json.lx
  - loxia/docgen.py
---

# std.json

RFC 8259 JSON with insertion-ordered objects and a 16-level nesting cap.

## API

## Enums

### `enum JsonResult`

Result of `parseResult`: the parsed value or the reason the text is invalid.

It is not a `Result[Any, String]` because the checker refuses to instantiate a type
variable with `Any` (`E3011`); the enum carries the same information and can become a
`Result` if that restriction is lifted.

#### `Ok(Any)`

_No documentation._

#### `Err(String)`

_No documentation._

## Functions

### `fn parse(text: String) -> Any`

Parses RFC 8259 JSON text into Loxia values.

Accepts `null`, booleans, numbers, strings, arrays and objects. A number without a
fraction or exponent stays `Int` when it fits, otherwise it becomes `Float`;
non-finite values are rejected. Objects preserve key order and a repeated key keeps
the last value. Invalid input (bad escapes, trailing characters) returns `nil`; a
valid JSON `null` also returns `nil`. Use `parseResult` when the caller must
distinguish malformed text from a valid `null`.

### `fn parseResult(text: String) -> JsonResult`

Parses JSON text, preserving the difference between `null` and invalid text.

Returns `JsonResult.Ok(nil)` for the JSON literal `null` and `JsonResult.Err(message)`
for malformed input. Nesting is not capped (the reader uses an explicit stack,
ADR-0158). The message is the same one `parse` used to hide and never contains a
path, timestamp or address.

### `fn isOk(result: JsonResult) -> Bool`

Returns `true` when `result` came from a valid JSON text.

Exists because an enum type exported by a module cannot be named in another module's
annotations; callers use these helpers instead of writing a typed wrapper function.

### `fn value(result: JsonResult) -> Any`

Returns the parsed value, or `nil` when the text was invalid.

### `fn error(result: JsonResult) -> String | Nil`

Returns the error message, or `nil` when the text was valid.

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
