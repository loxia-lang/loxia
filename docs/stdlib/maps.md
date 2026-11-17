---
title: std.maps
sources:
  - std/maps.lx
  - loxia/docgen.py
---

# std.maps

Helpers for `Map[String, V]` that preserve insertion order.

## API

## Functions

### `fn entries[V](m: Map[String, V]) -> List[(String, V)]`

Returns the key/value pairs in insertion order.

Each entry is a `(key, value)` tuple; the input map is not modified.

### `fn toList[V](m: Map[String, V]) -> List[(String, V)]`

Returns the key/value pairs in insertion order.

Alias of `entries`.

### `fn fromEntries[V](items: List[(String, V)]) -> Map[String, V]`

Builds a map from `(key, value)` pairs.

Later pairs with the same key win, while the key keeps its first insertion position.

### `fn merge[V](left: Map[String, V], right: Map[String, V]) -> Map[String, V]`

Merges two maps; the right-hand value wins.

Keys keep their first insertion position and `left` is not modified.

### `fn pick[V](m: Map[String, V], keys: List[String]) -> Map[String, V]`

Returns a map containing only the named keys that exist in `m`.

Output order follows `keys`, not the input map; duplicate names are ignored.

### `fn omit[V](m: Map[String, V], keys: List[String]) -> Map[String, V]`

Returns a map without the named keys, preserving the input order.

### `fn mapValues[V, U](m: Map[String, V], f: fn(V) -> U) -> Map[String, U]`

Transforms each value with `f`, preserving keys and insertion order.

### `fn filterKeys[V](m: Map[String, V], predicate: fn(String) -> Bool) -> Map[String, V]`

Keeps entries whose key satisfies `predicate`, preserving order.

### `fn filterValues[V](m: Map[String, V], predicate: fn(V) -> Bool) -> Map[String, V]`

Keeps entries whose value satisfies `predicate`, preserving order.

### `fn invert(m: Map[String, String]) -> Map[String, String]`

Swaps keys and values; later collisions win.

Requires `Map[String, String]`. When two keys share a value, the later key becomes
the surviving key and keeps the position of the first value insertion.

### `fn hasValue[V](m: Map[String, V], value: V) -> Bool`

Returns whether any value equals `value`, using structural equality.

### `fn getOr[V](m: Map[String, V], key: String, fallback: V) -> V`

Returns the value for `key`, or `fallback` when absent.
