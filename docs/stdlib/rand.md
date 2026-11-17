---
title: std.rand
sources:
  - std/rand.lx
  - loxia/docgen.py
---

# std.rand

Deterministic xorshift64* PRNG with an explicit seed.

## API

## Classes

### `class Rand`

Deterministic xorshift64* generator; the same seed yields the same sequence.

#### `var state: Int`

Internal state (never zero).

#### `fn init(seed: Int)`

Creates a generator; `seed == 0` maps to the fixed default state.

The seed is the only source of variation, so sequences are reproducible.

#### `fn reseed(seed: Int) -> Nil`

Restarts the sequence with `seed`; `0` maps to the same default as `init`.

#### `fn nextInt() -> Int`

Returns the next raw 64-bit value.

The `Int` may be negative; use `int` or `float` for bounded values.

#### `fn int(min: Int, max: Int) -> Int`

Returns an integer in `[min, max]` (inclusive).

Raises `RuntimeError` when `min > max` or when the span overflows an `Int`.

#### `fn float() -> Float`

Returns a `Float` in `[0.0, 1.0)` with 53 bits of mantissa.

#### `fn bool() -> Bool`

Returns `true` or `false` with equal probability.

## Functions

### `fn shuffle[T](items: List[T], generator: Rand) -> Nil`

Shuffles `items` in place with Fisher-Yates using `generator`.

Mutates the list and returns `nil`; the resulting order depends only on the
generator state.
