---
title: std.io
sources:
  - std/io.lx
  - loxia/docgen.py
---

# std.io

Standard input/output (ambient where it blocks).

## API

## Functions

### `fn write(text: String) -> Nil`

Writes text to stdout without a trailing newline.

### `fn writeErr(text: String) -> Nil`

Writes text to stderr without a trailing newline.

### `fn readLine() -> String | Nil`

Reads one line from stdin, returning `nil` at end of input.

### `fn readAll() -> String`

Reads all remaining stdin as text.

### `fn prompt(message: String) -> String | Nil`

Writes `message` and reads one line from stdin.
