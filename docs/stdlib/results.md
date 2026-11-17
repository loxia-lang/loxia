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

Returns `true` for `Result.Ok` and `false` for `Result.Err`.

### `fn isErr[T, E](result: Result[T, E]) -> Bool`

Returns `true` for `Result.Err` and `false` for `Result.Ok`.

### `fn map[T, U, E](result: Result[T, E], transform: fn(T) -> U) -> Result[U, E]`

Applies `transform` to the success value; an error passes through unchanged.

The error type `E` is preserved.

### `fn mapErr[T, E, F](result: Result[T, E], transform: fn(E) -> F) -> Result[T, F]`

Applies `transform` to the error value; a success passes through unchanged.

The success type `T` is preserved.

### `fn unwrapOr[T, E](result: Result[T, E], fallback: T) -> T`

Returns the success value, or `fallback` for an error.

`fallback` is an ordinary argument, so it is evaluated before the call.

### `fn andThen[T, U, E](result: Result[T, E], transform: fn(T) -> Result[U, E]) -> Result[U, E]`

Chains a computation that itself returns a `Result`.

On success `transform` is called; on error the original error is returned unchanged.
This is the monadic bind for `Result`.

### `fn toOptional[T, E](result: Result[T, E]) -> T | Nil`

Returns the success value, or `nil` when the result is an error.

The error value is discarded; use `match` when it must be inspected.
