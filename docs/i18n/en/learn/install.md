---
title: Install and run
description: Get a Loxia checkout, open the REPL and run your first program.
---

## Requirements

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- For the native backend only: a C compiler, `llvmlite` and the Boehm GC development
  headers (`libgc-dev` on Debian/Ubuntu, `brew install bdw-gc` on macOS).

The interpreter itself has no runtime dependencies.

## From source

```bash
git clone https://github.com/loxia-lang/loxia.git
cd loxia
uv sync --all-groups --extra llvm
uv run loxia --version
```

The first public PyPI release will be **1.1.0**. Until then, use the checkout above.

## The REPL

```bash
uv run loxia
```

```text
> 1 + 2
3
> val name = "Loxia"
> "${name}!"
Loxia!
```

## Run a file

Create `hello.lx`:

<!-- run -->
```lox
print("hello from Loxia")
```

```bash
uv run loxia hello.lx
```

## Check without running

```bash
uv run loxia check hello.lx
```

`--check` runs the static checker. A clean check is a promise that the native backend can
compile the program, unless the program uses a declared lowering gap.

## Native binary

```bash
uv run loxia build hello.lx --emit=exe -o hello
./hello
```

Next: [values and bindings](../values/).
