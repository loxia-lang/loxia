---
title: std.framing
sources:
  - std/framing.lx
  - loxia/docgen.py
---

# std.framing

`Content-Length` framing over an injected byte reader; stdin/stdout only at the edge.

## API

## Classes

### `class FrameFailure`

Framing failure; `kind` is stable, `message` is for humans.

Kinds: `truncated` (input ended inside a frame), `bad_header` (malformed or missing
`Content-Length`), `too_large` (header or body above the caps), `read` (the reader
raised, e.g. invalid UTF-8).

#### `val kind: String`

Stable machine-readable kind.

#### `val message: String`

Human-readable reason; never contains a path, timestamp or address.

#### `fn init(kind: String, message: String)`

Creates a failure with an explicit kind and message.

## Types

### `type Reader = fn(Int) -> String | Nil`

Reader of at most `count` bytes, never splitting a code point.

`nil` means clean end of input. A returned text has one or more code points and at
most `count` UTF-8 bytes. `std.framing.readStdin` is the stdin implementation.

## Functions

### `fn readFrame(read: Reader) -> Result[String | Nil, FrameFailure]`

Reads one frame, returning its body.

`Result.Ok(nil)` is a clean end of input at a frame boundary. Headers must be ASCII
and end with CRLF; `Content-Length` is required, unique and counts UTF-8 bytes;
`Content-Type` is accepted and ignored. The body is returned as text, still
unparsed; pair with `std.jsonrpc.decode` for JSON-RPC.

### `fn encodeFrame(text: String) -> String`

Serializes one frame: `Content-Length` counts UTF-8 bytes, then the body.

### `fn readStdin(count: Int) -> String | Nil`

Reads from stdin with `io.readUtf8`, the exact-bytes reader.

Ambient: blocks until `count` bytes or end of input. A truncated body is normalized
to `nil` (the codec reports `truncated`); invalid UTF-8 raises `RuntimeError`, which
`readFrame` turns into a `read` failure.

### `fn writeStdout(text: String) -> Nil`

Writes a complete frame to stdout and flushes it.

Ambient. `io.write` flushes on every call (ADR-0094), so a client waiting for the
response never deadlocks. Never use `print` for protocol output.
