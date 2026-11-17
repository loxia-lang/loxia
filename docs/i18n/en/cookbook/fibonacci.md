---
title: Fibonacci
description: Recursion, functions and a for-in loop.
---

This is the smallest complete program in the cookbook: a recursive Fibonacci function and
a loop that prints the first ten values.

<!-- run -->
```lox
fn fib(n: Int) -> Int {
  if (n < 2) {
    return n
  }
  return fib(n - 1) + fib(n - 2)
}

for i in 0..10 {
  print(fib(i))
}
```

Run it with `uv run loxia fib.lx`. The `Int` annotation is checked before execution;
`fib(30)` is fine, but exponential recursion is still exponential.

For a faster version, keep two previous values in a loop:

<!-- run -->
```lox
fn fib_fast(n: Int) -> Int {
  var a = 0
  var b = 1
  var i = 0
  while (i < n) {
    val next = a + b
    a = b
    b = next
    i = i + 1
  }
  return a
}

print(fib_fast(50))
```
