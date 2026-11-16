---
title: Standard library
sources:
  - std/*.lx
  - loxia/builtins_docs.py
---

# Standard library

Reference generated from `///` in `std/*.lx` and the builtins registry.

## Modules

| Module | Summary |
| --- | --- |
| [`std.asserts`](asserts.md) | Assertions that raise `RuntimeError` on failure. |
| [`std.cli`](cli.md) | Deterministic command-line parsing. |
| [`std.convert`](convert.md) | Text conversions (integer/float/bool, Base64, hex). |
| [`std.csv`](csv.md) | RFC 4180 CSV parsing and serialization. |
| [`std.fmt`](fmt.md) | Formatting helpers (templates, padding, numbers, byte sizes). |
| [`std.fs`](fs.md) | File reading/writing (ambient: outside I1). |
| [`std.io`](io.md) | Standard input/output (ambient where it blocks). |
| [`std.json`](json.md) | RFC 8259 JSON with insertion-ordered objects. |
| [`std.lists`](lists.md) | Generic list combinators. |
| [`std.maps`](maps.md) | Helpers for `Map[String, V]`. |
| [`std.numeric`](numeric.md) | Integer number theory and statistics. |
| [`std.paths`](paths.md) | Lexical POSIX path helpers. |
| [`std.proc`](proc.md) | Processes, streams and `poll` (POSIX, ambient). |
| [`std.results`](results.md) | Combinators for `Result[T, E]`. |
| [`std.sets`](sets.md) | `Set[T]` backed by `Map[Any, Bool]`. |
| [`std.strings`](strings.md) | UTF-8 text operations over code points. |
| [`std.test`](test.md) | Mini-harness de testes (TAP, `Suite`, matchers, `Recorder`). |
| [`std.utf8`](utf8.md) | UTF-8 and UTF-16 widths (bytes, code units, columns). |

## Builtins

See [builtins.md](builtins.md).
