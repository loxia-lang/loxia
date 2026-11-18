# Loxia

[![CI](https://github.com/loxia-lang/loxia/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/loxia-lang/loxia/actions/workflows/ci.yml)
[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](LICENSE-MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](pyproject.toml)

**Loxia** is a small, statically checked language **descended from Lox**, with a tree-walk
interpreter that serves as the executable specification and an optional **LLVM** backend.
It is not a toy: the interpreter and the compiled binary are tested for byte-identical
stdout, stderr and exit codes on a declared corpus. The lineage is declared, not a
compatibility claim — Loxia has its own syntax, semantics and standard library.

> **Status:** 1.x, pre-public release. The language semantics are frozen; tooling and
> packaging are still moving. The project is not on PyPI yet. The specification and ADRs
> are currently in Portuguese; see [Documentation](#documentation).

## Why Loxia

- **I1 — the interpreter is the specification.** A program produces the same bytes when
  interpreted and when compiled, for the declared corpus. The tree-walk is the oracle, not
  a fallback.
- **I2 — nothing happens implicitly.** No coercion between `Int`, `Float` and `String`, no
  exotic truthiness, no surprise `nil`.
- **I3 — deterministic output.** Same input, same bytes: no addresses, timestamps, PIDs or
  absolute paths in diagnostics.
- **I4 — a clean check compiles.** If `--check` accepts a program, the backend compiles it;
  the only acceptable refusal is a declared `not supported by the backend yet` gap.
- **Two engines, one language.** Start with the interpreter, then use the optional LLVM
  backend for a native binary.
- **Batteries included.** A standard library built on a small native kernel: JSON, CSV,
  paths, files, processes, collections, hashing, property-based testing and more.

## A taste of Loxia

<!-- readme-sample -->
```lox
enum Shape {
  Circle(Float),
  Rect(Float, Float)
}

fn area(shape: Shape) -> Float {
  return match shape {
    Shape.Circle(r) => 3.14159 * r * r,
    Shape.Rect(w, h) => w * h,
  }
}

val shapes = [Shape.Circle(2.0), Shape.Rect(2.0, 3.0)]
for shape in shapes {
  print("area = ${area(shape)}")
}
```

```text
area = 12.56636
area = 6.0
```

## Status

| Area | State |
| --- | --- |
| Language semantics | 1.x frozen ([ADR-0026](docs/adr/0026-freeze-1.0.md)); no silent changes |
| Interpreter | Lox core from *Crafting Interpreters* plus Loxia's own syntax and semantics |
| Native backend | L0–L6 + T7: strings, classes, closures, containers, enums, exceptions |
| Standard library | T1–T3: `json`, `fmt`, `fs`, `io`, `proc`, `sets`, `csv`, `hash`, `property`… |
| Tooling | formatter, LSP, test runner, `fix`, `doc`, `explain`, `capabilities` |
| Packaging | first public release (1.1.0) pending |

Current version: **1.1.0**. The detailed, generated status by level is in
[`docs/spec/garantias.md`](docs/spec/garantias.md).

## Install

The first public PyPI release will be **1.1.0**. From 1.1.0 on, the command comes from the
installed package, with no clone:

```bash
pip install loxia          # or: uv tool install loxia
loxia --version
```

Until the release ships, install from the checkout:

```bash
git clone https://github.com/loxia-lang/loxia.git
cd loxia
uv sync --all-groups --extra llvm
uv run loxia --version
```

The wheel carries the interpreter, `loxia_core/std/` and the C runtime, which is what makes
`import std.*` and `--emit` work outside the clone ([ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md)).

The interpreter has no runtime dependencies. The native backend is opt-in: `--emit` needs
`llvmlite` (`uv sync --extra llvm`); `--emit=exe` also needs a C compiler and the Boehm GC
development headers (`libgc-dev` on Debian/Ubuntu, `brew install bdw-gc` on macOS).

Linux x86_64 is the CI platform. macOS and Windows are not tested; the interpreter may
work, the native backend is not promised there.

## Quick start

```bash
uv run loxia                       # REPL
uv run loxia repl                  # REPL as an explicit subcommand
uv run loxia new hello             # project scaffold (loxia.toml, .gitignore, src/main.lx, lock)
uv run loxia run hello/src/main.lx
uv run loxia hello.lx              # run a file
uv run loxia check hello.lx        # type-check only
uv run loxia build hello.lx --emit=exe -o hello
uv run loxia --version             # loxia 1.0.0
```

## CLI

`loxia` exposes subcommands; the legacy flags remain available for compatibility.

| Command | Purpose | Main flags |
| --- | --- | --- |
| `loxia run FILE` | Execute a program | `--debug`, `--stdin`, `--file-name`, `--module-path`, `--timeout`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia repl` | Interactive session (`loxia` alone does the same) | `--debug`, `--module-path`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia new NAME` | Create a project (`loxia.toml`, `.gitignore`, `src/main.lx`, `loxia.lock`) | `--name`, `--no-git`, `--json` |
| `loxia init [DIR]` | Initialize a project in an existing directory | `--name`, `--no-git`, `--json` |
| `loxia check FILE` | Type-check without running | `--watch`, `--stdin`, `--file-name`, `--module-path`, `--timeout`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia build FILE` | Build a native binary | `--emit=ll\|o\|exe`, `--output`, `--max-heap`, `--module-path`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia ast FILE` | Print the AST as an S-expression | `--stdin`, `--file-name`, `--module-path`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia fmt FILE` | Format a file (`--check` does not write) | `--check`, `--stdin`, `--file-name`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia doc FILE` | Generate Markdown/JSON from `///` | `--stdin`, `--file-name`, `--json`, `--error-format`, `--max-errors`, `--color` |
| `loxia explain CODE` | Explain a diagnostic family | `--json` |
| `loxia capabilities` | Machine-readable version, commands and limits | `--json` |
| `loxia lsp` | Language server over stdio | `--stdio` |
| `loxia test [PATH…]` | Run `*_test.lx` suites | `--filter`, `--only`, `--jobs`, `--isolate`, `--timeout`, `--fail-fast`, `--native`, `--frozen`, `--offline`, `--cache-dir`, `--json` |
| `loxia fix FILE` | Apply safe fixes (dry-run by default) | `--apply`, `--max-iterations`, `--json` |
| `loxia lock` | Write `loxia.lock` from the manifest | `--check`, `--offline`, `--cache-dir` |
| `loxia fetch` | Verify/materialize the locked dependency tree | `--offline`, `--cache-dir` |

Global compatibility flags: `--check`, `--dump-ast`, `--debug`, `--version`, `--color`.

`loxia new` writes a minimal, deterministic template and runs `git init` unless
`--no-git` is given (never inside an existing repository); `loxia init` does the same in an
existing directory and never overwrites files. Both accept `--json` for tooling.

Exit codes: `65` compilation error, `70` runtime error, `66` missing file, `2` invalid
usage, `1` for a `--check`/`lock --check` difference, `124` timeout, `130` interrupted
`--watch`. The generated binary follows the same runtime contract: `0` on success and `70`
on an uncaught runtime error.

## Packages

A project declares dependencies in `loxia.toml`; `loxia lock` writes `loxia.lock` next to
it and both are committed:

```toml
[package]
name = "app"
version = "0.1.0"

[dependencies]
acme = { path = "../acme" }
# or a pinned repository, with a full commit or a tag (never a branch):
# acme = { git = "https://github.com/acme/acme", rev = "v1.2.3" }
```

```bash
loxia lock                 # writes loxia.lock (name, origin, version, sha256)
loxia lock --check         # exit 1 if the lock is stale
loxia fetch                # verifies path deps; downloads/materializes git deps
loxia run --frozen app.lx  # resolves only from the lock; fails on drift
```

The lock pins the `sha256` of each dependency's `.lx` tree, so `--frozen` detects any
content change and `run`/`check`/`build` never touch the network. Git dependencies are
fetched by `loxia lock`/`loxia fetch` only: the lock stores the resolved commit, so a
moving tag cannot change a build. The cache lives in `.loxia/cache/` (ignored by git),
`--cache-dir` overrides it and `--offline` uses the cache only
([ADR-0104](docs/adr/0104-lock-e-frozen.md), [ADR-0105](docs/adr/0105-dependencias-git.md)).


## How it works

```text
source .lx
   │
   ├─ scanner → tokens
   ├─ parser → AST
   ├─ resolver → lexical depths
   ├─ checker (--check) → type errors before execution
   ├─ interpreter → effects
   └─ backend (--emit) → LLVM IR → object → cc → native binary
```

The interpreter is the normative specification; the backend consumes the same checker
types. This is what makes the differential corpus meaningful instead of cosmetic.

## Documentation

- **Specification:** [lexicon](docs/spec/lexico.md), [syntax](docs/spec/sintaxe.md),
  [semantics](docs/spec/semantica.md), [errors](docs/spec/erros.md) and
  [guarantees](docs/spec/garantias.md).
- **Architecture:** [`docs/tech/arquitetura.md`](docs/tech/arquitetura.md).
- **Standard library:** [`docs/stdlib/`](docs/stdlib/) (generated).
- **Documentation site:** [`site/`](site/) — Starlight build from `docs/`; run
  `make docs-dev`; publication follows the public flip.
- **Style guide:** [`docs/guia-estilo.md`](docs/guia-estilo.md).
- **Design decisions:** [`docs/adr/`](docs/adr/).
- **Roadmap:** [`TODO.md`](TODO.md) · **open ideas:** [`IDEIAS.md`](IDEIAS.md).

> **Language:** the README and the community files are in English. The specification,
> ADRs and roadmap are currently in Portuguese (pt-BR); English translation is planned in
> [`TODO.md`](TODO.md) §14.2. The public API docs (`docs/stdlib/`) are in English.

## Development

```bash
uv sync --all-groups --extra llvm   # dev environment, including the native backend
make check-fast                     # lint + format + mypy + tests (no native builds) + docs
make check                          # everything, including the native backend
make bench                          # benchmarks vs the baseline
```

`make hooks` installs the local pre-commit and commit-msg hooks. The full contribution
rules, commit convention and review checklist are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first; the project has
an admission gate for features ([ADR-0014](docs/adr/0014-identidade-e-invariantes.md)) and a
stricter gate for syntax ([ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md)). By
participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Security reports go
through [SECURITY.md](SECURITY.md), never a public issue.

## License

Loxia is licensed under **MIT OR Apache-2.0**, at your option:

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE))
- MIT license ([LICENSE-MIT](LICENSE-MIT))

Unless you explicitly state otherwise, any contribution intentionally submitted for
inclusion in this project by you, as defined in the Apache-2.0 license, shall be dual
licensed as above, without any additional terms or conditions.

## Acknowledgements

Loxia began as an implementation of *Crafting Interpreters* by Robert Nystrom; the official
test suite in [`tests/official/`](tests/official/) is adapted under its MIT license. The
native backend uses [LLVM](https://llvm.org/) through
[llvmlite](https://github.com/numba/llvmlite) and links the
[Boehm-Demers-Weiser GC](https://github.com/ivmai/bdwgc).
