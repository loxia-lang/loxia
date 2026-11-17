---
title: std.iter
sources:
  - std/iter.lx
  - loxia/docgen.py
---

# std.iter

Iteration helpers (`enumerate`, `zip`, `sum`, `contains`, `Step`).

## API

## Enums

### `enum Step[T]`

Envelope for iterating over elements that may be `nil`.

A user iterator declares `next() -> Step[T]?`; returning `nil` ends the iteration,
while `Step.Item(nil)` yields a nil element (ADR-0082).

#### `Item(T)`

One element; `value` may be `nil` when `T` is optional.

## Functions

### `fn enumerate[T](items: List[T]) -> List[(Int, T)]`

Returns `(index, element)` pairs in list order.

Indices start at 0 and match the positions in the input; the result has the same
length as `items`.

### `fn zip[A, B](left: List[A], right: List[B]) -> List[(A, B)]`

Pairs elements from `left` and `right`, stopping at the shorter list.

Returns a new list; the input lists are not modified.

### `fn sum(items: List[Int]) -> Int`

Returns the sum of the integers, or 0 for an empty list.

### `fn sumFloat(items: List[Float]) -> Float`

Returns the sum of the floats, or 0.0 for an empty list.

### `fn contains[T](items: List[T], item: T) -> Bool`

Returns whether `item` occurs in the list.

Uses `==`, so lists, maps and tuples compare structurally.

### `fn any[T](items: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns whether any element satisfies `predicate`.

Stops at the first match. An empty list returns `false`.

### `fn all[T](items: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns whether every element satisfies `predicate`.

Stops at the first mismatch. An empty list satisfies it vacuously.

### `fn find[T](items: List[T], predicate: fn(T) -> Bool) -> T | Nil`

Returns the first element that satisfies `predicate`, or `nil` when none matches.
