---
title: std.asserts
sources:
  - std/asserts.lx
  - loxia/docgen.py
---

# std.asserts

Assertions that raise `RuntimeError` on failure.

## API

## Functions

### `fn assert(condition: Bool, message: String = ...) -> Nil`

Raises `RuntimeError` with `message` when `condition` is false.

### `fn assertEq[T](actual: T, expected: T, message: String = ...) -> Nil`

Raises `RuntimeError` when the two values differ; returns `Nil` on success.

### `fn assertNotNil[T](value: T | Nil, message: String = ...) -> T`

Returns the value narrowed to a non-nil type, or raises `RuntimeError`.

### `fn fail(message: String) -> Nil`

Raises `RuntimeError` with `message` unconditionally.
