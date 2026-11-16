---
title: std.sets
sources:
  - std/sets.lx
  - loxia/docgen.py
---

# std.sets

`Set[T]` backed by `Map[Any, Bool]`.

## API

## Classes

### `class Set[T]`

A mutable set backed by `Map[Any, Bool]`.

#### `val items: Map[Any, Bool]`

The backing map of elements.

#### `fn init()`

Creates an empty set.

#### `fn add(value: T) -> Nil`

Adds a value to the set.

#### `fn has(value: T) -> Bool`

Returns whether the set contains a value.

#### `fn remove(value: T) -> Bool`

Removes a value, returning whether it was present.

#### `fn len() -> Int`

Returns the number of elements.

#### `fn toList() -> List[T]`

Returns the elements as a list in insertion order.

#### `fn union(other: Set[T]) -> Set[T]`

Returns a new set with the elements of both sets.

#### `fn intersect(other: Set[T]) -> Set[T]`

Returns a new set with the common elements.

#### `fn difference(other: Set[T]) -> Set[T]`

Returns a new set with elements not in `other`.

## Functions

### `fn fromList[T](values: List[T]) -> Set[T]`

Builds a set from a list, deduplicating values.
