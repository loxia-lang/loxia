# Loxia

[![CI](https://github.com/loxia-lang/loxia/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/loxia-lang/loxia/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/loxia)](https://pypi.org/project/loxia/)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/loxia-lang/loxia/badge)](https://securityscorecards.dev/viewer/?uri=github.com/loxia-lang/loxia)
[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](LICENSE-MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](pyproject.toml)

**Loxia** is a small, statically checked language **descended from Lox**, with a tree-walk
interpreter that serves as the executable specification and an optional **LLVM** backend.
It is not a toy: the interpreter and the compiled binary are tested for byte-identical
stdout, stderr and exit codes on a declared corpus. The lineage is declared, not a
compatibility claim — Loxia has its own syntax, semantics and standard library.

> **Status:** 1.x, released. The language semantics are frozen; tooling and packaging are
> still moving. **1.2.0** is the current release, the first PyPI release with the MCP
> server. The specification is in English; the ADRs and roadmap are in Portuguese
> (pt-BR). See [Documentation](#documentation).

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
| Tooling | formatter, LSP, MCP, test runner, `fix`, `doc`, `explain`, `capabilities` |
| Packaging | on PyPI (1.1.0 and 1.2.0) |

Current version: **1.2.0**. The detailed, generated status by level is in
[`docs/spec/garantias.md`](docs/spec/garantias.md).

## Install

```bash
pip install loxia          # or: uv tool install loxia
loxia --version
```

To work on the interpreter itself, use a checkout:

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

Linux x86_64 is the supported platform for the native backend. The non-backend suite runs
on macOS (blocking) and Windows (experimental; known platform failures); the native
backend is not promised there.

## Quick start

```bash
loxia                              # REPL
loxia repl                         # REPL as an explicit subcommand
loxia new hello                    # project scaffold (loxia.toml, .gitignore, src/main.lx, lock)
loxia run hello/src/main.lx
loxia hello.lx                     # run a file
loxia check hello.lx               # type-check only
loxia build hello.lx --emit=exe -o hello
loxia --version                    # loxia 1.2.0
```

## CLI

`loxia --help` lists the commands; `loxia <command> --help` documents only that
command's flags (grouped by purpose) and examples. The legacy invocation
`loxia [flags] file.lx` remains supported: its flags are summarized at the end of
`loxia --help` under compatibility mode and map to subcommands (`--check` → `check`,
`--dump-ast` → `ast`, `--emit` → `build`).

| Command | Purpose | Main flags |
| --- | --- | --- |
| `loxia run FILE` | Execute a program (type-checks in gradual mode first; `--no-check` skips) | `--no-check`, `--debug`, `--sandbox`, `--stdin`, `--file-name`, `--module-path`, `--timeout`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia repl` | Interactive session (`loxia` alone does the same) | `--debug`, `--module-path`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia new NAME` | Create a project (`loxia.toml`, `.gitignore`, `src/main.lx`, `loxia.lock`) | `--name`, `--no-git`, `--lib`, `--json` |
| `loxia init [DIR]` | Initialize a project in an existing directory | `--name`, `--no-git`, `--lib`, `--json` |
| `loxia add NAME` | Declare a `path` or `git` dependency in `loxia.toml` | `--path`, `--git`, `--rev`, `--dry-run`, `--lock`, `--offline`, `--cache-dir`, `--module-path`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia remove NAME` | Remove a dependency from `loxia.toml` | `--dry-run`, `--lock`, `--offline`, `--cache-dir`, `--module-path`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia check FILE` | Type-check without running (`--gradual` turns a missing annotation into a warning) | `--gradual`, `--watch`, `--stdin`, `--file-name`, `--module-path`, `--timeout`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia build FILE` | Build a native binary | `--emit=ll\|o\|exe`, `--output`, `--max-heap`, `--module-path`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia ast FILE` | Print the AST (S-expression; `--format=json` requires `--file-only`) | `--file-only`, `--format=sexp\|json`, `--allow-errors`, `--typed`, `--stdin`, `--file-name`, `--module-path`, `--frozen`, `--offline`, `--cache-dir`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia fmt PATH...` | Format files and directories recursively (`--check` does not write) | `--check`, `--diff`, `--edits=json` (one file, with `--check`), `--exclude`, `--max-width`, `--stdin`, `--file-name`, `--error-format`, `--json`, `--json-lines`, `--max-errors`, `--no-progress`, `--color` |
| `loxia doc FILE` | Generate Markdown/JSON from `///` | `--stdin`, `--file-name`, `--json`, `--error-format`, `--max-errors`, `--color` |
| `loxia explain CODE` | Explain a diagnostic family | `--json` |
| `loxia capabilities` | Machine-readable version, commands and limits | `--json` |
| `loxia lsp` | Language server over stdio | `--stdio` |
| `loxia mcp` | MCP server over stdio (tools) | — |
| `loxia test [PATH…]` | Run `*_test.lx` suites (type-checked in gradual mode first; `--no-check` disables) | `--filter`, `--only`, `--jobs`, `--isolate`, `--timeout`, `--fail-fast`, `--require-tests`, `--capture`, `--changed[=REF]`, `--shard=INDEX/TOTAL`, `--native`, `--no-cache`, `--no-check`, `--frozen`, `--offline`, `--cache-dir`, `--json`, `--json-lines`, `--junit` |
| `loxia fix FILE` | Apply safe fixes (dry-run by default) | `--apply`, `--max-iterations`, `--json` |
| `loxia lock` | Write `loxia.lock` from the manifest | `--check`, `--offline`, `--cache-dir` |
| `loxia fetch` | Verify/materialize the locked dependency tree | `--offline`, `--cache-dir` |

Global flag: `--version`. Every other flag belongs to a command; run
`loxia <command> --help` for the authoritative list and the grouped descriptions.

For the self-hosted parser, `loxia ast --file-only --format=json FILE` emits the versioned
per-file AST contract v2 (`syntax` with statements/tokens/trivia plus optional `typed`)
without loading modules or mangling names; `--format=json` requires `--file-only`;
`--typed` adds checker expression types; `--allow-errors` emits the recovered tree
(`ErrorStmt`/`ErrorExpr`) and still exits 65. The contract and the frozen snapshot are in
[ADR-0129](docs/adr/0129-oraculo-do-front-end.md).

`loxia new` writes a minimal, deterministic template and runs `git init` unless
`--no-git` is given (never inside an existing repository); `loxia init` does the same in an
existing directory and never overwrites files. Both accept `--json` for tooling.

Exit codes: `65` compilation error, `70` runtime error, `66` missing file, `2` invalid
usage, `1` for a `--check`/`lock --check` difference, `124` timeout, `130` interrupted
`--watch`. The generated binary follows the same runtime contract: `0` on success and `70`
on an uncaught runtime error.

## MCP server

<!-- mcp-name: io.github.loxia-lang/loxia -->

`loxia mcp` (or the `loxia-mcp` console script) is a thin
[Model Context Protocol](https://modelcontextprotocol.io/) server over the CLI. It speaks
MCP `2026-07-28` on stdio and exposes:

- `loxia_check` — type-check a source and return the CLI JSON diagnostics;
- `loxia_run` — run a source in the sandbox profile (no filesystem/process primitives,
  timeout and resource limits);
- `loxia_ast` — parse and return the S-expression AST;
- `loxia_format` — format a source or a read-only `.lx` path, returning the text and
  exact `TextEdit[]` (optional line range and diff; never writes);
- `loxia_spec` — search the packaged language reference and stdlib;
- `loxia_explain` and `loxia_version`.

Point your client at it:

```json
{
  "mcpServers": {
    "loxia": { "command": "loxia", "args": ["mcp"] }
  }
}
```

Or let the client fetch the package from PyPI:

```json
{
  "mcpServers": {
    "loxia": {
      "command": "uvx",
      "args": ["--from", "loxia", "loxia-mcp"]
    }
  }
}
```

The MCP Registry manifest is [`server.json`](https://github.com/loxia-lang/loxia/blob/main/server.json); the PyPI package
`loxia` carries the `loxia-mcp` console script and the packaged docs index.

The server is zero-dependency; check/run/ast results are byte-identical to the CLI. See
[`docs/tech/mcp.md`](docs/tech/mcp.md) for the protocol, sandbox and limits (ADR-0112).

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
loxia add acme --path ../acme          # inserts the entry, preserving comments/order
loxia add acme --git URL --rev v1.2.3  # pinned git dependency
loxia remove acme --dry-run            # unified diff; add `--lock` to relock afterwards
loxia lock                 # writes loxia.lock (name, origin, version, sha256)
loxia lock --check         # exit 1 if the lock is stale
loxia fetch                # verifies path deps; downloads/materializes git deps
loxia run --frozen app.lx  # resolves only from the lock; fails on drift
```

`loxia add`/`remove` edit only the `[dependencies]` entry: comments, order and line
endings are preserved, the edited manifest is re-parsed before writing, and a shape the
editor does not understand (a `[dependencies.NAME]` sub-table, a dotted key) fails with
`C0004` instead of rewriting the file. Adding an already-declared dependency with the same
spec is a no-op (`"changed": false` with `--json`); with a different spec it fails. Neither
command touches the network unless `--lock` is given.

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
- **Test report:** [`docs/tech/test-report.md`](docs/tech/test-report.md) and
  [`schema/test-report-v1.json`](schema/test-report-v1.json).
- **Test coverage:** [`docs/tech/test-coverage.md`](docs/tech/test-coverage.md)
  (feature → golden/differential matrix) and
  [`docs/tech/python-coverage.md`](docs/tech/python-coverage.md) (`make coverage`).
- **Standard library:** [`docs/stdlib/`](docs/stdlib/) (generated).
- **Documentation site:** <https://loxia-lang.github.io/loxia/> — Starlight build from
  `docs/`; run `make docs-dev` for the local server.
- **Editors:** [VS Code](https://marketplace.visualstudio.com/items?itemName=loxia-lang.loxia)
  (also on [Open VSX](https://open-vsx.org/extension/loxia-lang/loxia)) — syntax
  highlighting, LSP and Run; the client lives in
  [`loxia-lang/loxia-vscode`](https://github.com/loxia-lang/loxia-vscode) and consumes the
  grammar asset attached to each release (ADR-0109).
- **Style guide:** [`docs/guia-estilo.md`](docs/guia-estilo.md).
- **Design decisions:** [`docs/adr/`](docs/adr/).
- **Roadmap:** [`docs/roadmap.md`](docs/roadmap.md) · **open ideas:**
  [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas).

> **Language:** the README, the community files and the specification are in English.
> The ADRs and the roadmap remain in Portuguese (pt-BR). The public API docs
> (`docs/stdlib/`) are in English.

## Development

```bash
uv sync --all-groups --extra llvm   # dev environment, including the native backend
make check-fast                     # lint + format + mypy + tests (no native builds) + docs
make check                          # everything, including the native backend
make coverage                       # Python branch coverage (measurement)
make coverage-ratchet               # coverage gate (selected modules)
make bench                          # benchmarks vs the baseline
```

`make hooks` installs the local pre-commit, commit-msg and pre-push hooks. The fast suite
runs on pre-push; the native backend stays in CI and in `make check`. The full contribution
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
