# std — standard library

Scoped context for `std/`. The root [`AGENTS.md`](../AGENTS.md) still applies. The
operational checklist is the `lox-stdlib` skill; this file is the short version.

## What belongs here

The stdlib is **pure Lox over the kernel** ([ADR-0072](../docs/adr/0072-stdlib-batteries.md)).
If it can be written in Lox on top of `std/*` or an existing primitive, it belongs here; only
OS or representation the language cannot reach goes to the kernel
([ADR-0071](../docs/adr/0071-primitivas-de-runtime.md)). No generic FFI.

A new module does **not** add syntax. If it needs syntax, that is the ADR-0066 gate, not a
stdlib change.

## Definition of done for a module

- [ ] a real program in `examples/` (or a case) uses it — real pain, not symmetry with
      another language;
- [ ] golden case `tests/cases/std_<module>.lx` plus a clean `--check`;
- [ ] determinism declared: a function that is `ambient` is outside the I1/I3 corpus and its
      test uses fixed input;
- [ ] public doc in the module header and a generated page under `docs/stdlib/`;
- [ ] zero new syntax;
- [ ] `make check` green; `make bench` if it touches a hot path.

Docs are **generated**: run `make stdlib-docs` and `make docs-sync`; never hand-edit the page
or the index. A new module must appear in the catalog and pass `tests/test_stdlib_docs.py`.

## API shape

The hybrid model is fixed ([ADR-0016](../docs/adr/0016-api-stdlib-hibrida.md)): global builtins for
generic operations (`len`, `str`, `repr`), methods for operations on a value
(`xs.push/pop`), native namespaces for conversion (`Int.parse`, `math.*`) and free functions
for composition. Do not add a fourth shape.

## Host capability (kernel)

Each new capability needs its own ADR and fits the kernel budget (ADR-0123). Non-negotiable
rules:

- `ambient: true` for anything touching the OS/network; outside the I1/I3 corpus.
- New host error → `Result[T, OsError]`; `T?` stays only in old APIs.
- Opaque handle with explicit, idempotent `close()`; using a closed handle is a
  `RuntimeError`; **no finalizer** (Boehm is not deterministic).
- `poll` before threads; `spawn` without a shell; no C→Lox callback that can raise; no generic
  FFI.
- `net` v1 only with an IP literal, loopback when possible, no DNS/TLS (TLS is a separate ADR).
- A kernel above ~30 primitives is a sign of the wrong layer; introduce an opaque handle type
  before growing it. The budget is closed at 40 (ADR-0123) — adding one requires an ADR.

Capabilities under evaluation live in Discussions › Ideas and in the roadmap; do not ship a
speculative one.
