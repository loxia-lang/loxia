---
title: std.numeric
sources:
  - std/numeric.lx
  - loxia/docgen.py
---

# std.numeric

Integer number theory and statistics.

## API

## Functions

### `fn gcd(left: Int, right: Int) -> Int`

Returns the non-negative greatest common divisor.

### `fn lcm(left: Int, right: Int) -> Int`

Returns the non-negative least common multiple.

### `fn isPrime(value: Int) -> Bool`

Returns whether an integer is prime.

### `fn primes(limit: Int) -> List[Int]`

Returns all primes up to `limit`.

### `fn factorial(value: Int) -> Int`

Returns `value!`; negative input raises `RuntimeError`.

### `fn powMod(base: Int, exponent: Int, modulus: Int) -> Int`

Returns `base ** exponent (mod modulus)`.

### `fn digitSum(value: Int) -> Int`

Returns the sum of decimal digits.

### `fn isEven(value: Int) -> Bool`

Returns whether the integer is even.

### `fn isOdd(value: Int) -> Bool`

Returns whether the integer is odd.

### `fn sign(value: Int) -> Int`

Returns -1, 0 or 1 according to the sign.

### `fn mean(values: List[Int]) -> Float | Nil`

Returns the arithmetic mean, or `nil` for an empty list.

### `fn median(values: List[Int]) -> Float | Nil`

Returns the median, or `nil` for an empty list.

### `fn mode(values: List[Int]) -> Int | Nil`

Returns the most frequent value, or `nil` for an empty list.

### `fn variance(values: List[Int]) -> Float | Nil`

Returns the population variance, or `nil` for an empty list.

### `fn stddev(values: List[Int]) -> Float | Nil`

Returns the population standard deviation, or `nil` for an empty list.

### `fn roundTo(value: Float, digits: Int) -> Float`

Rounds to `digits` decimal places.

### `fn toBase(value: Int, base: Int) -> String`

Formats an integer in base 2..36.

### `fn fromBase(text: String, base: Int) -> Int | Nil`

Parses an integer in base 2..36, returning `nil` when invalid.
