---
title: std.sets
sources:
  - std/sets.lx
  - loxia/docgen.py
---

# std.sets

`Set[T]` backed by `Map[Any, Bool]`, preserving insertion order.

## API

## Classes

### `class Set[T]`

Mutable set backed by `Map[Any, Bool]`.

#### `val items: Map[Any, Bool]`

Backing map; keys are elements and every value is `true`.

#### `fn init()`

Creates an empty set.

#### `fn add(value: T) -> Nil`

Adds `value`; adding an existing value is a no-op that keeps its position.

#### `fn has(value: T) -> Bool`

Returns whether `value` is in the set.

#### `fn remove(value: T) -> Bool`

Removes `value`, returning whether it was present.

#### `fn len() -> Int`

Returns the number of elements.

#### `fn toList() -> List[T]`

Returns the elements as a list in insertion order.

#### `fn union(other: Set[T]) -> Set[T]`

Returns a new set with the elements of both sets.

Elements of `this` come first, followed by new elements of `other`.

#### `fn intersect(other: Set[T]) -> Set[T]`

Returns a new set with the elements present in both sets.

Order follows `this`.

#### `fn difference(other: Set[T]) -> Set[T]`

Returns a new set with the elements of `this` that are not in `other`.

Order follows `this`.

## Functions

### `fn fromList[T](values: List[T]) -> Set[T]`

Builds a set from `values`, deduplicating in first-occurrence order.
