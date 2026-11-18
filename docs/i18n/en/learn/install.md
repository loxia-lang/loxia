---
title: Install and run
description: Get a Loxia checkout, open the REPL and run your first program.
---

## Requirements

- Python 3.13
- For the native backend only: a C compiler, `llvmlite` and the Boehm GC development
  headers (`libgc-dev` on Debian/Ubuntu, `brew install bdw-gc` on macOS).
- Optional: [`uv`](https://docs.astral.sh/uv/) for a source checkout.

The interpreter itself has no runtime dependencies.

## Install

```bash
pip install loxia          # or: uv tool install loxia
loxia --version
```

## From source

```bash
git clone https://github.com/loxia-lang/loxia.git
cd loxia
uv sync --all-groups --extra llvm
uv run loxia --version
```

## The REPL

```bash
loxia
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
loxia hello.lx
```

## Check without running

```bash
loxia check hello.lx
```

`--check` runs the static checker. A clean check is a promise that the native backend can
compile the program, unless the program uses a declared lowering gap.

## Native binary

```bash
loxia build hello.lx --emit=exe -o hello
./hello
```

Next: [values and bindings](../values/).
