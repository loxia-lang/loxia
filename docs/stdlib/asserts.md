---
title: std.asserts
sources:
  - std/asserts.lx
  - loxia/docgen.py
---

# std.asserts

Explicit failures for tests and contracts. Every helper raises `RuntimeError`.

## API

## Functions

### `fn assert(condition: Bool, message: String = ...) -> Nil`

Raises `RuntimeError` with `message` when `condition` is false.

Intended for preconditions and invariants; on success it returns `nil` and has no
other effect.

### `fn assertEq[T](actual: T, expected: T, message: String = ...) -> Nil`

Raises `RuntimeError` when the two values differ.

Uses `!=`, so lists, maps and tuples compare structurally. The message includes
both values rendered with `str`, which keeps the failure readable in TAP output.

### `fn assertNotNil[T](value: T | Nil, message: String = ...) -> T`

Returns `value` narrowed to a non-nil type, or raises `RuntimeError`.

The return type removes the optional, so callers can keep using the value without a
second nil check. The default message is `expected a non-nil value`.

### `fn fail(message: String) -> Nil`

Raises `RuntimeError` with `message` unconditionally.

Useful for unreachable branches and for aborting a contract check with a
caller-provided message.
