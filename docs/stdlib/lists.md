---
title: std.lists
sources:
  - std/lists.lx
  - loxia/docgen.py
---

# std.lists

Generic list combinators.

## API

## Functions

### `fn isEmpty(xs: List[Any]) -> Bool`

Returns true when the list has no elements.

### `fn length(xs: List[Any]) -> Int`

Returns the number of elements.

### `fn map[T, U](xs: List[T], f: fn(T) -> U) -> List[U]`

Applies `f` to each element and returns the results.

### `fn filter[T](xs: List[T], predicate: fn(T) -> Bool) -> List[T]`

Returns the elements for which `predicate` is true.

### `fn each[T](xs: List[T], action: fn(T) -> Nil) -> Nil`

Calls `action` for each element and returns `Nil`.

### `fn fold[T, U](xs: List[T], initial: U, f: fn(U, T) -> U) -> U`

Folds the list left-to-right starting from `initial`.

### `fn any[T](xs: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns true when at least one element satisfies `predicate`.

### `fn all[T](xs: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns true when every element satisfies `predicate`.

### `fn none[T](xs: List[T], predicate: fn(T) -> Bool) -> Bool`

Returns true when no element satisfies `predicate`.

### `fn findIndex[T](xs: List[T], predicate: fn(T) -> Bool) -> Int`

Returns the first matching index, or -1.

### `fn contains[T](xs: List[T], value: T) -> Bool`

Returns whether the list contains `value`.

### `fn indexOf[T](xs: List[T], value: T) -> Int`

Returns the first index of `value`, or -1.

### `fn reverse[T](xs: List[T]) -> List[T]`

Returns a new list in reverse order.

### `fn take[T](xs: List[T], count: Int) -> List[T]`

Returns the first `count` elements.

### `fn drop[T](xs: List[T], count: Int) -> List[T]`

Returns the list without its first `count` elements.

### `fn slice[T](xs: List[T], start: Int, end: Int) -> List[T]`

Returns the half-open range `[start, end)`.

### `fn sum(xs: List[Int]) -> Int`

Returns the sum of all integers.

### `fn first[T](xs: List[T]) -> T | Nil`

Returns the first element, or `nil` when empty.

### `fn last[T](xs: List[T]) -> T | Nil`

Returns the last element, or `nil` when empty.

### `fn find[T](xs: List[T], predicate: fn(T) -> Bool) -> T | Nil`

Returns the first matching element, or `nil`.

### `fn reduce[T](xs: List[T], f: fn(T, T) -> T) -> T | Nil`

Reduces the list with `f`, returning `nil` when empty.

### `fn count[T](xs: List[T], predicate: fn(T) -> Bool) -> Int`

Returns how many elements satisfy `predicate`.

### `fn min[T](xs: List[T]) -> T | Nil`

Returns the smallest element, or `nil` when empty.

### `fn max[T](xs: List[T]) -> T | Nil`

Returns the largest element, or `nil` when empty.

### `fn getOr[T](xs: List[T], index: Int, fallback: T) -> T`

Returns the element at `index`, or `fallback` when out of range.

### `fn sort[T](xs: List[T], compare: fn(T, T) -> Int) -> List[T]`

Returns a new list sorted by the comparator.

### `fn sortNatural[T](xs: List[T]) -> List[T]`

Returns a new list sorted by natural ordering.

### `fn zip[T, U](xs: List[T], ys: List[U]) -> List[(T, U)]`

Pairs elements from both lists, stopping at the shorter one.

### `fn flatten[T](xs: List[List[T]]) -> List[T]`

Concatenates a list of lists.

### `fn flatMap[T, U](xs: List[T], f: fn(T) -> List[U]) -> List[U]`

Maps each element to a list and concatenates the results.

### `fn unique[T](xs: List[T]) -> List[T]`

Returns the elements without duplicates, preserving order.

### `fn chunk[T](xs: List[T], size: Int) -> List[List[T]]`

Splits the list into chunks of at most `size` elements.

### `fn partition[T](xs: List[T], predicate: fn(T) -> Bool) -> (List[T], List[T])`

Splits the list into `(matching, rest)`.
