---
title: std.results
sources:
  - std/results.lx
  - loxia/docgen.py
---

# std.results

Combinators for `Result[T, E]`.

## API

## Functions

### `fn isOk[T, E](result: Result[T, E]) -> Bool`

Returns true for `Result.Ok`.

### `fn isErr[T, E](result: Result[T, E]) -> Bool`

Returns true for `Result.Err`.

### `fn map[T, U, E](result: Result[T, E], transform: fn(T) -> U) -> Result[U, E]`

Transforms the success value.

### `fn mapErr[T, E, F](result: Result[T, E], transform: fn(E) -> F) -> Result[T, F]`

Transforms the error value.

### `fn unwrapOr[T, E](result: Result[T, E], fallback: T) -> T`

Returns the success value, or `fallback` for an error.

### `fn andThen[T, U, E](result: Result[T, E], transform: fn(T) -> Result[U, E]) -> Result[U, E]`

Chains a computation that returns another `Result`.

### `fn toOptional[T, E](result: Result[T, E]) -> T | Nil`

Returns the success value or `nil`.
