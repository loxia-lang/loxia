---
title: Collections
description: List[T], Map[K, V] and tuples.
---

## Lists

`List[T]` is homogeneous and mutable in place. `val` freezes the binding, not the list.

<!-- run -->
```lox
val xs: List[Int] = [1, 2, 3]
xs.push(4)
print(len(xs))
print(xs[0])

for x in xs {
  print(x)
}
```

`xs[i] = value` updates an element; an out-of-range index is a runtime error. `pop()`
removes the last element.

## Maps

`Map[K, V]` preserves insertion order. Keys are `String`, `Int` or `Bool`.

<!-- run -->
```lox
val scores: Map[String, Int] = { "ada": 10, "grace": 12 }
print(scores["ada"])
print(scores.get("missing") ?? -1)

scores["linus"] = 11
for name in scores {
  print(name)
}
```

`m[k]` fails when the key is absent; `m.get(k)` returns `V?`. `m.has`, `m.remove`,
`m.keys` and `m.values` are available.

## Tuples

Tuples are immutable, structural and can be destructured. A tuple needs at least two
elements.

<!-- run -->
```lox
val pair = (10, 20)
val (first, second) = pair
print(first + second)

val nested = (1, (2, 3))
val (one, (two, three)) = nested
print(one + two + three)
```

Next: [classes, enums and match](../classes/).
