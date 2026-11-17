---
title: std.io
sources:
  - std/io.lx
  - loxia/docgen.py
---

# std.io

Standard input/output. The read functions are ambient where they block.

## API

## Functions

### `fn write(text: String) -> Nil`

Writes `text` to stdout without a trailing newline.

Flushes immediately, so the text is visible before the next read or process exit.

### `fn writeErr(text: String) -> Nil`

Writes `text` to stderr without a trailing newline.

Flushes immediately; deterministic, but stderr is not part of the default golden
comparison.

### `fn readLine() -> String | Nil`

Reads one line from stdin, returning `nil` at end of input.

Ambient. A trailing LF or CRLF is removed. Invalid UTF-8 raises instead of returning
a replacement character.

### `fn readAll() -> String`

Reads all remaining stdin as text.

Ambient. At end of input an empty string is returned. Invalid UTF-8 raises.

### `fn prompt(message: String) -> String | Nil`

Writes `message` and reads one line from stdin.

Ambient. The message is written without a trailing newline, then `readLine` is
called; `nil` means end of input.
