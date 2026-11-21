---
title: std.contracts
sources:
  - std/contracts.lx
  - loxia/docgen.py
---

# std.contracts

Design by contract as a library: precondition, postcondition and invariant checks.

## API

## Classes

### `class ContractError(Exception)`

Error raised when a precondition, postcondition or invariant is violated.

It extends `Exception`, not `RuntimeError`: a contract violation is a programming
bug and must be caught explicitly (`except ContractError`) or terminate the program.

#### `fn init(message: String)`

Creates the error with the message shown in the diagnostic.

## Functions

### `fn require(condition: Bool, message: String = ...) -> Nil`

Requires `condition`; raises `ContractError(message)` when it is false.

Use it at the top of a function or method. The default message is
`precondition failed`; prefer a message that names the function and the condition.

### `fn ensure(condition: Bool, message: String = ...) -> Nil`

Ensures `condition`; raises `ContractError(message)` when it is false.

Use it after the body computed `result`, before returning. For single-exit functions
prefer `check`, which evaluates the postcondition automatically.

### `fn checkInvariant(condition: Bool, message: String = ...) -> Nil`

Checks an invariant; raises `ContractError(message)` when it is false.

Invariants are cooperative: fields are public, so this checks only the points where
the code calls it (typically the end of `init` and the boundary of public methods).

### `fn check[T](name: String, pre: fn() -> Bool, body: fn() -> T, post: fn(T) -> Bool) -> T`

Runs `body` between `pre` and `post`, returning its result.

`pre` is evaluated before the body; when it is false, the body is not executed.
`post` receives the result and is evaluated only when the body returns normally.
If the body raises, the postcondition is not evaluated.

The `old` value is a local captured before the call; pass a closure that reads it.

### `fn checkMethod[T, R](name: String, self: T, pre: fn(T) -> Bool, body: fn(T) -> R, post: fn(T, R) -> Bool) -> R`

Like `check`, but for a method with an explicit receiver.

The receiver is passed as `self` instead of being captured as `this`; that keeps the
closure independent from the method frame and works in both engines. The predicates
take the receiver as their first parameter.

### `fn checkVoid(name: String, pre: fn() -> Bool, body: fn() -> Nil, post: fn() -> Bool) -> Nil`

Like `check`, but for a function returning `Nil`.

The postcondition takes no result parameter, which reads better for procedures and
avoids the dummy `Nil` argument that `check` would need.

### `fn checkMethodVoid[T](name: String, self: T, pre: fn(T) -> Bool, body: fn(T) -> Nil, post: fn(T) -> Bool) -> Nil`

Like `checkMethod`, but for a method returning `Nil`.
