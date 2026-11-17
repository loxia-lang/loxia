---
title: std.property
sources:
  - std/property.lx
  - loxia/docgen.py
---

# std.property

Deterministic property-based testing with generators, shrinking and seeds.

## API

## Classes

### `class Gen[T]`

Value generator with a generation strategy and a shrink strategy.

#### `val generate: fn(Rand) -> T`

Produces a value from the random generator.

#### `val shrink: fn(T) -> List[T]`

Smaller candidates for `value` (an empty list means no shrinking).

#### `fn init(generate: fn(Rand) -> T, shrink: fn(T) -> List[T])`

Creates the generator from its two functions.

#### `fn sample(random: Rand) -> T`

Samples one value using `random`.

#### `fn smaller(value: T) -> List[T]`

Returns the shrink candidates for `value`.

## Functions

### `fn forAll[T](generator: Gen[T], check: fn(T) -> Nil, runs: Int = ..., seed: Int = ...) -> Nil`

Runs `check` with `runs` generated values; on failure shrinks and raises.

Stops at the first failure and raises `TestFailure` with the run number, seed,
original counterexample and shrunk value. `Skip` propagates unchanged. `seed` is
explicit, so a failing run is reproducible.

### `fn int() -> Gen[Int]`

64-bit integer generator; shrinks toward 0 and then toward the halfway point.

### `fn intRange(min: Int, max: Int) -> Gen[Int]`

Integer generator in `[min, max]`; shrinks toward `min`.

### `fn bool() -> Gen[Bool]`

`Bool` generator; shrinks `true` to `false`.

### `fn float() -> Gen[Float]`

`Float` generator in `[0.0, 1.0)`; shrinks to `0.0`.

### `fn listOf[T](element: Gen[T], maxLength: Int = ...) -> Gen[List[T]]`

List generator with length in `[0, maxLength]`; shrinks by removing elements.

Elements are drawn from `element`; shrunk lists are not shrunk element-wise.

### `fn listOfInt(element: Gen[Int], maxLength: Int = ...) -> Gen[List[Int]]`

List of `Int`; compatibility alias of `listOf`.

### `fn listOfString(element: Gen[String], maxLength: Int = ...) -> Gen[List[String]]`

List of `String`; compatibility alias of `listOf`.

### `fn stringOf(maxLength: Int = ...) -> Gen[String]`

String generator over `[a-z0-9]` with length in `[0, maxLength]`.

Shrinks by deleting one character per candidate.

### `fn oneOf[T](options: List[T]) -> Gen[T]`

Chooses one value from `options`; shrinks toward the first element.

Raises `RuntimeError` when `options` is empty.
