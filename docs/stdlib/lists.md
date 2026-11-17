---
title: std.lists
sources:
  - std/lists.lx
  - loxia/docgen.py
---

# std.lists

Generic list combinators; every function leaves the input unchanged.

## API

## Functions

### `fn isEmpty(xs: List[Any]) -> Bool`

Returns `true` when the list has no elements.

### `fn length(xs: List[Any]) -> Int`

Returns the number of elements; equivalent to `len(xs)`.

### `fn map[T, U](xs: List[T], f: fn(T) -> U) -> List[U]`

Applies `f` to each element and returns the results in order.

The result has the same length as `xs`; the input list is not modified.

### `fn filter[T](xs: List[T], predicate: fn(T) -> Bool) -> List[T]`

Returns the elements for which `predicate` is true.

Preserves the original order and calls `predicate` once per element.

### `fn each[T](xs: List[T], action: fn(T) -> Nil) -> Nil`

Calls `action` for each element in order and returns `nil`.

Intended for side effects; the input list is not modified.

### `fn fold[T, U](xs: List[T], initial: U, f: fn(U, T) -> U) -> U`

Folds the list left to right starting from `initial`.

The accumulator type `U` may differ from the element type `T`.

### `fn any[T](xs: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns true when at least one element satisfies `predicate`.

Stops at the first match; an empty list returns `false`.

### `fn all[T](xs: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns true when every element satisfies `predicate`.

Stops at the first mismatch; an empty list satisfies it vacuously.

### `fn none[T](xs: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns true when no element satisfies `predicate`.

Equivalent to `not any(xs, predicate)`.

### `fn findIndex[T](xs: List[T], predicate: fn(T) -> Bool) -> Int`

Returns the index of the first element satisfying `predicate`, or -1.

### `fn contains[T](xs: List[T], value: T) -> Bool`

Returns whether the list contains `value`.

Uses `==`, so lists, maps and tuples compare structurally.

### `fn indexOf[T](xs: List[T], value: T) -> Int`

Returns the first index where `value` occurs, or -1.

### `fn reverse[T](xs: List[T]) -> List[T]`

Returns a new list in reverse order without modifying the input.

### `fn take[T](xs: List[T], count: Int) -> List[T]`

Returns up to `count` elements from the start.

A zero or negative `count` yields `[]`; a `count` larger than the list yields a copy
of the whole list.

### `fn drop[T](xs: List[T], count: Int) -> List[T]`

Returns the list without its first `count` elements.

A negative `count` is treated as 0, so the whole list is returned.

### `fn slice[T](xs: List[T], start: Int, end: Int) -> List[T]`

Returns the half-open range `[start, end)`.

Indices are clamped: negatives become 0, `end < start` yields `[]`, and `end` beyond
the list length is clamped to `len(xs)`.

### `fn sum(xs: List[Int]) -> Int`

Returns the sum of all integers, or 0 for an empty list.

### `fn first[T](xs: List[T]) -> T | Nil`

Returns the first element, or `nil` when empty.

### `fn last[T](xs: List[T]) -> T | Nil`

Returns the last element, or `nil` when empty.

### `fn find[T](xs: List[T], predicate: fn(T) -> Bool) -> T | Nil`

Returns the first element that satisfies `predicate`, or `nil` when none matches.

### `fn reduce[T](xs: List[T], f: fn(T, T) -> T) -> T | Nil`

Reduces the list left to right using the first element as the accumulator.

Returns `nil` for an empty list. `f` receives `(accumulator, next)`.

### `fn count[T](xs: List[T], predicate: fn(T) -> Bool) -> Int`

Returns how many elements satisfy `predicate`.

### `fn min[T](xs: List[T]) -> T | Nil`

Returns the smallest element using `<`, or `nil` when empty.

### `fn max[T](xs: List[T]) -> T | Nil`

Returns the largest element using `>`, or `nil` when empty.

### `fn getOr[T](xs: List[T], index: Int, fallback: T) -> T`

Returns the element at `index`, or `fallback` when out of range.

Negative indices are out of range; there is no wrap-around.

### `fn sort[T](xs: List[T], compare: fn(T, T) -> Int) -> List[T]`

Returns a new list sorted by `compare`.

`compare(a, b)` returns a negative number when `a` comes first, zero for ties and a
positive number otherwise. The merge sort is stable and does not mutate the input.

### `fn sortNatural[T](xs: List[T]) -> List[T]`

Returns a new list sorted by natural ordering (`<=`).

Stable merge sort requiring `T: Ord`; the input list is not modified.

### `fn zip[T, U](xs: List[T], ys: List[U]) -> List[(T, U)]`

Pairs elements from both lists, stopping at the shorter one.

### `fn flatten[T](xs: List[List[T]]) -> List[T]`

Concatenates a list of lists into a new flat list, preserving order.

### `fn flatMap[T, U](xs: List[T], f: fn(T) -> List[U]) -> List[U]`

Maps each element to a list with `f` and concatenates the results.

### `fn unique[T](xs: List[T]) -> List[T]`

Returns the elements without duplicates, preserving first-occurrence order.

Uses structural equality and does not mutate the input.

### `fn chunk[T](xs: List[T], size: Int) -> List[List[T]]`

Splits the list into consecutive chunks of at most `size` elements.

The last chunk may be shorter. A `size` of 0 or less returns `[]`; each chunk is a
new list.

### `fn partition[T](xs: List[T], predicate: fn(T) -> Bool) -> (List[T], List[T])`

Splits the list into `(matching, rest)`.

Both lists preserve the original order, and `predicate` is called once per element.
