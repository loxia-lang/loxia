---
title: Control flow
description: if, elif, while, for-in and ranges.
---

## if, elif, else

Conditions use truthiness: only `nil` and `false` are falsy.

<!-- run -->
```lox
fn classify(n: Int) -> String {
  if (n < 0) {
    return "negative"
  } elif (n == 0) {
    return "zero"
  } else {
    return "positive"
  }
}

print(classify(-2))
print(classify(0))
print(classify(9))
```

Braces are required. The `;` at the end of a line is optional; use it only when two
statements share a line.

## while

<!-- run -->
```lox
var i = 0
while (i < 3) {
  print(i)
  i = i + 1
}
```

## for-in and ranges

`a..b` is a half-open range of `Int` (`a` included, `b` excluded). `for` creates a new
immutable binding per iteration.

<!-- run -->
```lox
var total = 0
for n in 0..5 {
  total = total + n
}
print(total)

for ch in "aço" {
  print(ch)
}
```

`range(a, b, step)` adds a step and can count down. `for-in` also accepts `List`, `Map`
(keys in insertion order), tuples and user types with `iter()` + `next() -> T?`.

Next: [functions and closures](functions/).
