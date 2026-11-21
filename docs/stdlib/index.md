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
| [`std.asserts`](asserts.md) | Explicit failures for tests and contracts. Every helper raises `RuntimeError`. |
| [`std.bytes`](bytes.md) | Byte buffers: incremental Builder, comparison and big/little-endian helpers. |
| [`std.cli`](cli.md) | Deterministic command-line parsing from a declarative spec. |
| [`std.collections`](collections.md) | Stack, Queue, Deque and PriorityQueue, backed by lists. |
| [`std.contracts`](contracts.md) | Design by contract as a library: precondition, postcondition and invariant checks. |
| [`std.convert`](convert.md) | Text conversions (integer/float/bool, Base64, hex) over UTF-8 bytes. |
| [`std.csv`](csv.md) | RFC 4180 CSV parsing and serialization, with CRLF output. |
| [`std.documents`](documents.md) | Full-sync document store: opaque URIs, versions and text, without JSON or I/O. |
| [`std.fmt`](fmt.md) | Locale-free formatting helpers (templates, padding, numbers, byte sizes). |
| [`std.framing`](framing.md) | `Content-Length` framing over an injected byte reader; stdin/stdout only at the edge. |
| [`std.fs`](fs.md) | File reading and writing. Ambient: outside the I1 corpus. |
| [`std.hash`](hash.md) | Non-cryptographic hashes (FNV-1a, djb2) over UTF-8 bytes. |
| [`std.io`](io.md) | Standard input/output. The read functions are ambient where they block. |
| [`std.iter`](iter.md) | Iteration helpers (`enumerate`, `zip`, `sum`, `contains`, `Step`). |
| [`std.json`](json.md) | RFC 8259 JSON with insertion-ordered objects and a 16-level nesting cap. |
| [`std.jsonrpc`](jsonrpc.md) | JSON-RPC 2.0 envelopes: validation, construction, error codes and `Map` messages. |
| [`std.lists`](lists.md) | Generic list combinators; every function leaves the input unchanged. |
| [`std.log`](log.md) | Leveled logging to stderr, without timestamps. |
| [`std.maps`](maps.md) | Helpers for `Map[String, V]` that preserve insertion order. |
| [`std.numeric`](numeric.md) | Integer number theory and population statistics. |
| [`std.paths`](paths.md) | Lexical POSIX path helpers; no filesystem access. |
| [`std.proc`](proc.md) | Processes, streams and `poll` (POSIX, ambient: outside I1/I3). |
| [`std.property`](property.md) | Deterministic property-based testing with generators, shrinking and seeds. |
| [`std.rand`](rand.md) | Deterministic xorshift64* PRNG with an explicit seed. |
| [`std.results`](results.md) | Combinators for `Result[T, E]`. |
| [`std.sets`](sets.md) | `Set[T]` backed by `Map[Any, Bool]`, preserving insertion order. |
| [`std.strings`](strings.md) | UTF-8 text operations over code points, not bytes or UTF-16 units. |
| [`std.test`](test.md) | Mini test harness with TAP output, hooks, matchers and a recorder. |
| [`std.timex`](timex.md) | UTC date/time helpers over integer epoch milliseconds; no timezones. |
| [`std.utf8`](utf8.md) | UTF-8 and UTF-16 widths (bytes, code units, columns). |

## Builtins

See [builtins.md](builtins.md).
