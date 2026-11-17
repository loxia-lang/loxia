---
title: Why Loxia?
description: A small language with explicit contracts, deterministic output and two engines.
---

Loxia is not trying to be the biggest language. It is trying to be a **small language with
explicit contracts** — and to make those contracts executable.

## I1 — the interpreter is the specification

The tree-walk interpreter is the normative definition of the language. The optional LLVM
backend is tested against it: for the declared corpus, the same program must produce the
same stdout, stderr and exit code when interpreted and when compiled, byte for byte.

That changes how features are designed. A construct that cannot be reproduced by the
backend is either lowered carefully or explicitly refused with
`not supported by the backend yet`; it is never generated "approximately".

## I2 — nothing happens implicitly

There is no implicit coercion between `Int`, `Float`, `String` and `Bool`. `1 + 2.0` is a
runtime error in the interpreter and a type error in the checker, not a silent promotion.
Truthiness is limited to `nil` and `false`; `0`, `0.0` and `""` are truthy.

This is more verbose in a few places and much easier to reason about in the places that
matter: serialization, comparison, maps and the native ABI.

## I3 — deterministic output

Same input, same bytes. Diagnostics do not contain addresses, PIDs, timestamps, absolute
paths or hash iteration order. The test suite polices the output of both engines.

Determinism is also why the standard library avoids locale-dependent formatting and
transcendental math. When an operation is inherently ambient (files, processes, stdin), it
is marked as such and kept out of the differential corpus.

## I4 — a clean check compiles

If `--check` accepts a program, the native backend must compile it. The only acceptable
refusal is a declared lowering gap. The checker is the single source of types; the backend
does not invent a second type system.

## Two engines, one language

Use the tree-walk interpreter for development, REPL sessions and diagnostics. Use the
LLVM backend when you need a native binary. You do not need two languages, two module
systems or two standard libraries.

## What Loxia is not

- Not a replacement for a general-purpose systems language.
- Not a bytecode VM or a JIT; the interpreter is deliberately the specification.
- Not a framework: the standard library is batteries, not a platform.
- Not finished. The semantics are frozen, but tooling, packaging and the docs site are
  still evolving.

The [reference](../reference/) is the normative source; the [roadmap](https://github.com/loxia-lang/loxia/blob/main/TODO.md)
records what is deliberately out of scope.
