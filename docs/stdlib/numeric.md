---
title: std.numeric
sources:
  - std/numeric.lx
  - loxia/docgen.py
---

# std.numeric

Integer number theory and population statistics.

## API

## Functions

### `fn gcd(left: Int, right: Int) -> Int`

Returns the non-negative greatest common divisor.

Signs are ignored and `gcd(0, 0)` is 0.

### `fn lcm(left: Int, right: Int) -> Int`

Returns the non-negative least common multiple.

Returns 0 when either argument is 0; a large product can wrap like any `Int` product.

### `fn isPrime(value: Int) -> Bool`

Returns whether the integer is prime.

Values below 2 are not prime; 2 is prime and larger even numbers are rejected early.

### `fn primes(limit: Int) -> List[Int]`

Returns all primes up to and including `limit`, in ascending order.

`limit < 2` yields `[]`.

### `fn factorial(value: Int) -> Int`

Returns `value!`.

Negative input raises `RuntimeError`; an overflowing result wraps like any `Int`
product.

### `fn powMod(base: Int, exponent: Int, modulus: Int) -> Int`

Returns `base ** exponent` modulo `modulus`.

`modulus` must be positive and `exponent` non-negative, otherwise `RuntimeError` is
raised. A negative `base` is normalized before the modular arithmetic.

### `fn digitSum(value: Int) -> Int`

Returns the sum of the decimal digits.

The sign is ignored, so `digitSum(-42)` is 6; `digitSum(0)` is 0.

### `fn isEven(value: Int) -> Bool`

Returns whether the integer is even. Negative values follow the same parity rule.

### `fn isOdd(value: Int) -> Bool`

Returns whether the integer is odd. Negative values follow the same parity rule.

### `fn sign(value: Int) -> Int`

Returns -1, 0 or 1 according to the sign.

### `fn mean(values: List[Int]) -> Float | Nil`

Returns the arithmetic mean as `Float`, or `nil` for an empty list.

### `fn median(values: List[Int]) -> Float | Nil`

Returns the median as `Float`, or `nil` for an empty list.

A copy is sorted, so the input list is not modified. For an even length the two
middle values are averaged.

### `fn mode(values: List[Int]) -> Int | Nil`

Returns the most frequent value, or `nil` for an empty list.

Ties keep the value that first reaches the highest count in list order.

### `fn variance(values: List[Int]) -> Float | Nil`

Returns the population variance, or `nil` for an empty list.

Divides by n, not by n-1.

### `fn stddev(values: List[Int]) -> Float | Nil`

Returns the population standard deviation, or `nil` for an empty list.

Square root of `variance`.

### `fn roundTo(value: Float, digits: Int) -> Float`

Rounds to `digits` decimal places.

Negative digits are allowed and round to tens, hundreds and so on, because the scale
is `10.0 ** digits`.

### `fn toBase(value: Int, base: Int) -> String`

Formats an integer in base 2..36 using lowercase digits.

Negative values keep a leading `-`; an invalid base raises `RuntimeError`.

### `fn fromBase(text: String, base: Int) -> Int | Nil`

Parses an integer in base 2..36, returning `nil` when invalid.

Accepts an optional `+`/`-` and lowercase or uppercase digits. An invalid base raises
`RuntimeError`; invalid digits or an empty string return `nil`.
