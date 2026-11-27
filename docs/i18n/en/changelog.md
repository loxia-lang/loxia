---
title: Changelog
description: Release notes and the history of Loxia.
---

The canonical changelog is maintained in the repository at
[`CHANGELOG.md`](https://github.com/loxia-lang/loxia/blob/main/CHANGELOG.md).

The first public release was **1.1.0**; **1.3.0** is the current release, published on
[PyPI](https://pypi.org/project/loxia/). Historical changelog entries before 1.1.0 are
written in Portuguese.

## 1.3.0

Loxia 1.3.0 adds an entry point and completes the runtime work opened after 1.2.0:

- `fn main() -> Result[T, String]` runs after the top-level statements; `Ok` exits 0 and
  `Err(msg)` prints `error[R1016]: msg` to stderr and exits 70, byte-identical in both
  engines;
- function values carry their runtime signature, so `is fn(...)`/`as fn(...)` check arity,
  parameters, defaults and return type; `Any` fields occupy two inline words in the backend;
- the language gained `break`/`continue`, `match` with literal patterns, `Bytes`, `is`/`as`
  for interfaces and the native `regex` module;
- dynamic member, index and call access on `Any` now requires narrowing (`E3025`), and class
  objects are no longer function values — both are breaking and listed in the canonical
  changelog;
- the LSP builds a cold workspace in 0.40 s (was 2.45 s for 50 files) and rechecks edits in
  ~10 ms; the MCP server gained `loxia_format` with exact `TextEdit[]`;
- the formatter 2.0 reflows calls and collections at 100 columns, and `loxia run` checks
  types before executing (`--no-check` was removed); AST JSON v2 replaces v1.

The exact notes are curated in the canonical changelog.

## 1.2.0

Loxia 1.2.0 is the first PyPI release with the MCP server:

- `loxia mcp` and `loxia-mcp` expose `loxia_check`, `loxia_run`, `loxia_ast`,
  `loxia_spec`, `loxia_explain` and `loxia_version` over MCP `2026-07-28` on stdio;
- `loxia_run` uses the sandbox profile (filesystem/process primitives denied, timeouts and
  resource limits);
- the package includes the MCP Registry manifest and the `mcp-name` marker for PyPI
  ownership verification;
- the Inspector documentation covers the modern protocol era and local checkout setup.

The exact notes are curated in the canonical changelog.

## 1.1.0

The 1.1.0 release brought the public repository, packaging, the documentation site and the
accumulated post-1.0 work to PyPI. The exact notes are curated in the canonical changelog;
the [GitHub Release](https://github.com/loxia-lang/loxia/releases/tag/v1.1.0) links the
artifacts.
