---
title: Values and bindings
description: val, var, Int, Float, String, Bool and nil.
---

## Bindings

`val` declares an immutable binding and requires an initializer. `var` is mutable and may
start as `nil`.

<!-- run -->
```lox
val name = "Loxia"
var count = 3
count = count + 1
print("${name}: ${count}")
```

Parameters are immutable by default; write `var` before a parameter if the function needs
to reassign it.

## Numbers

`Int` is a 64-bit integer; `Float` is a 64-bit float. They are distinct types. A literal
without a dot or exponent is `Int`; a literal with one is `Float`.

```lox
print(1)       # Int
print(1.0)     # Float
print(4 / 2)   # 2.0 — `/` always returns Float
print(-7 // 2) # -3 — integer division
```

There is no implicit `Float → Int` conversion. Use `as Int` when you mean it; it truncates
and fails on NaN, infinity or out-of-range values.

## Strings

Strings are UTF-8, immutable, and interpolate with `${...}`:

```lox
val who = "world"
print("hello, ${who}")
print("length = ${len(who)}")
```

`len` counts code points, not bytes. `chars(s)` returns a list of one-code-point strings.

## Booleans and nil

`true` and `false` are the only booleans. `nil` is the absence of a value. Only `nil` and
`false` are falsy; `0`, `0.0` and `""` are truthy.

<!-- run -->
```lox
print(true and false)
print(nil ?? "fallback")
print(0 == false)
```

Next: [control flow](control-flow/).
