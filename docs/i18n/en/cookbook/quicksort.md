---
title: Quicksort
description: Lists, indexing, push and recursion.
---

Quicksort with typed lists. The pivot is the first element; smaller and larger values go
into separate lists, and the results are concatenated by pushing.

<!-- run -->
```lox
fn quicksort(xs: List[Int]) -> List[Int] {
  if (len(xs) <= 1) {
    return xs
  }

  val pivot = xs[0]
  val smaller: List[Int] = []
  val larger: List[Int] = []

  var i = 1
  while (i < len(xs)) {
    if (xs[i] < pivot) {
      smaller.push(xs[i])
    } else {
      larger.push(xs[i])
    }
    i = i + 1
  }

  val sorted: List[Int] = quicksort(smaller)
  sorted.push(pivot)
  for x in quicksort(larger) {
    sorted.push(x)
  }
  return sorted
}

val values: List[Int] = [5, 3, 8, 1, 9, 2, 7, 4, 6]
print(quicksort(values))
```

This version allocates two lists per call and is not in-place. It is deliberately simple:
the point is to show typed lists, index access, `push`, `for-in` and recursion in one
complete program.

The same function works with the native backend:

```bash
uv run loxia build quicksort.lx --emit=exe -o quicksort
```
