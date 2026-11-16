---
title: std.maps
sources:
  - std/maps.lx
  - loxia/docgen.py
---

# std.maps

Helpers for `Map[String, V]`.

## API

## Functions

### `fn entries[V](m: Map[String, V]) -> List[(String, V)]`

Returns the key/value pairs in insertion order.

### `fn toList[V](m: Map[String, V]) -> List[(String, V)]`

Returns the key/value pairs in insertion order.

### `fn fromEntries[V](items: List[(String, V)]) -> Map[String, V]`

Builds a map from key/value pairs; later keys win.

### `fn merge[V](left: Map[String, V], right: Map[String, V]) -> Map[String, V]`

Merges two maps; the right-hand value wins.

### `fn pick[V](m: Map[String, V], keys: List[String]) -> Map[String, V]`

Returns a map containing only the given keys.

### `fn omit[V](m: Map[String, V], keys: List[String]) -> Map[String, V]`

Returns a map without the given keys.

### `fn mapValues[V, U](m: Map[String, V], f: fn(V) -> U) -> Map[String, U]`

Transforms each value, preserving keys and order.

### `fn filterKeys[V](m: Map[String, V], predicate: fn(String) -> Bool) -> Map[String, V]`

Keeps entries whose key satisfies `predicate`.

### `fn filterValues[V](m: Map[String, V], predicate: fn(V) -> Bool) -> Map[String, V]`

Keeps entries whose value satisfies `predicate`.

### `fn invert(m: Map[String, String]) -> Map[String, String]`

Swaps keys and values; later collisions win.

### `fn hasValue[V](m: Map[String, V], value: V) -> Bool`

Returns whether any value equals `value`.

### `fn getOr[V](m: Map[String, V], key: String, fallback: V) -> V`

Returns the value for `key`, or `fallback` when absent.
