---
title: std.jsonrpc
sources:
  - std/jsonrpc.lx
  - loxia/docgen.py
---

# std.jsonrpc

JSON-RPC 2.0 envelopes: validation, construction, error codes and `Map` messages.

## API

## Classes

### `class RpcFailure`

A JSON-RPC error: why `decode` rejected a message, or the `error` member of a
response. `code` is the JSON-RPC error code and `data` is the optional payload.

`data` is `Any` because JSON-RPC allows any JSON value; narrow it with `is`/`as`
before use (ADR-0144). Envelopes keep insertion order and never include addresses.

#### `val code: Int`

Numeric JSON-RPC error code: `-32700` parse, `-32600` invalid request,
`-32601` method not found, `-32602` invalid params, `-32603` internal.

#### `val message: String`

Human-readable reason; never contains a path, timestamp or address.

#### `val data: Any`

Optional JSON payload from `error.data`; `nil` when the member is absent or
explicitly JSON `null` (the two are not distinguishable in this field).

#### `fn init(code: Int, message: String, data: Any = ...)`

Creates a failure with an explicit code, message and optional data.

## Functions

### `fn decode(text: String) -> Result[Map[String, Any], RpcFailure]`

Parses and validates one JSON-RPC 2.0 envelope.

A request has `method` and `id`; a notification has `method` and no `id`; a response
has exactly one of `result` or `error`. `id` is `Int` or `String` in requests, and
may also be `nil` in responses. `params` is an array or an object when present.
Batches (a top-level array) and malformed JSON are reported as failures.

### `fn encode(message: Map[String, Any]) -> String`

Serializes an envelope as compact JSON, preserving key insertion order.

### `fn request(id: Any, method: String, params: Any = ...) -> Map[String, Any]`

Builds a request with `method`, an `id` and optional `params`.

`id` should be an `Int` or a `String`; builders do not validate, `decode` does.

### `fn notification(method: String, params: Any = ...) -> Map[String, Any]`

Builds a notification: `method` with no `id`.

### `fn success(id: Any, result: Any = ...) -> Map[String, Any]`

Builds a success response; `result` may be `nil` (serialized as `null`).

### `fn failure(id: Any, code: Int, message: String, data: Any = ...) -> Map[String, Any]`

Builds an error response; the `error` object carries `code`, `message` and
`data` when it is not `nil` (omitted data keeps the envelope compatible).

`data` must be JSON-representable (`nil`, `Bool`, `Int`, `Float`, `String`,
`List` or `Map`); `encode` raises `RuntimeError` otherwise.

### `fn isRequest(message: Map[String, Any]) -> Bool`

Returns `true` when the envelope is a request (has `method` and `id`).

### `fn isNotification(message: Map[String, Any]) -> Bool`

Returns `true` when the envelope is a notification (has `method` and no `id`).

### `fn isResponse(message: Map[String, Any]) -> Bool`

Returns `true` when the envelope is a response (has `result` or `error`).

### `fn hasId(message: Map[String, Any]) -> Bool`

Returns `true` when the `id` member is present (its value may be `nil`).

### `fn idOf(message: Map[String, Any]) -> Any`

Returns the `id` member, or `nil` when it is absent.

### `fn methodOf(message: Map[String, Any]) -> String | Nil`

Returns the `method` member, or `nil` when it is absent or not a string.

### `fn errorOf(message: Map[String, Any]) -> RpcFailure | Nil`

Returns the typed `error` member, or `nil` when it is absent or malformed.

`data` is preserved as `Any`; narrowing it is the caller's job (ADR-0144).
