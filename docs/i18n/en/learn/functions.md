---
title: Functions and closures
description: fn, typed signatures, defaults, lambdas and variadics.
---

## A function

Functions use `fn`, typed parameters and an explicit return type:

```lox
fn add(a: Int, b: Int) -> Int {
  return a + b
}
```

`return` alone returns `nil`. A function that falls off the end also returns `nil`; the
checker only requires a return on every path when the return type is not `Nil`.

## Defaults

Defaults are positional and must be constants. A caller may omit trailing arguments.

<!-- run -->
```lox
fn add(a: Int, b: Int = 1) -> Int {
  return a + b
}

print(add(2))
print(add(2, 3))
```

## Lambdas

`fn(x) => expression` is a lambda. It has a contextual type from the expected function
type; when there is no context, annotate the parameters.

<!-- run -->
```lox
val double = fn(x: Int) => x * 2
print(double(4))

val add = fn(a: Int, b: Int) => a + b
print(add(3, 5))
```

## Variadics and spread

The last parameter can collect extra arguments as a list. A final spread fills the rest at
the call site.

<!-- run -->
```lox
fn total(...xs: Int) -> Int {
  var sum = 0
  for x in xs {
    sum = sum + x
  }
  return sum
}

print(total(1, 2, 3))
```

## Closures

Functions capture their lexical environment. A closure can keep state without a class:

<!-- run -->
```lox
fn counter() -> fn() -> Int {
  var n = 0
  return fn() {
    n = n + 1
    return n
  }
}

val next = counter()
print(next())
print(next())
```

Next: [collections](collections/).
