---
title: Errors and modules
description: try/except/finally, raise and import.
---

## Errors

Runtime errors are values of type `RuntimeError` (a subclass of `Exception`). `try`
catches by type; `finally` always runs. An uncaught runtime error exits with code 70.

<!-- run -->
```lox
try {
  raise RuntimeError("boom")
} except RuntimeError as e {
  print(e.message)
} finally {
  print("done")
}
```

`raise;` re-raises the current exception inside an `except` block. A `raise value` must be
an exception instance.

## Modules

A `.lx` file is a module; a directory is only a namespace. The standard library is
imported with `std.*`:

<!-- run -->
```lox
import std.fmt as fmt

print(fmt.format("{} + {} = {}", 1, 2, 3))
```

Local modules use the same syntax. With `loxia.toml`, a project can declare module roots
and `path` dependencies; deterministic resolution is part of the language contract.

## Errors as values

`Result[T, E]` is in the standard library when you prefer explicit error values over
exceptions:

```lox
import std.results as results

fn divide(a: Int, b: Int) -> Result[Int, String] {
  if (b == 0) {
    return Result.Err("division by zero")
  }
  return Result.Ok(a // b)
}
```

Next: [next steps](../next-steps/).
