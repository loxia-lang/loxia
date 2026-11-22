# runtime — C runtime for generated code

Scoped context for `runtime/`. The root [`AGENTS.md`](../AGENTS.md) still applies.

## Contract first

The runtime implements contracts fixed in ADRs; changing a number here without changing the
contract is a bug:

| Contract | Where | Value |
| --- | --- | --- |
| Boehm GC, hard heap cap | ADR-0074, ADR-0087 | 512 MiB default (`--max-heap`) |
| I1 memory envelope | `docs/spec/garantias.md` | 64 MiB live |
| Call depth / stack budget | ADR-0077 | 10,000 calls / 64 MiB, `R1015` catchable |
| Class/instance layout, vtables | ADR-0048 | see `loxia_core/backend/lower_model.py` |
| Kernel capability budget | ADR-0123 | per group, closed at 40 primitives |

`loxia_core/execution/limits.py` is the Python side of the same numbers; the driver passes
them as `-D` flags. Both sides are covered by tests — change one, change the other.

## ABI and generated code

- `runtime/kernel_gen.h` is **generated** from `loxia_core/execution/primitives.py` by
  `runtime/gen_kernel.py` (`make primitives`). Never hand-edit it; a mismatch is a build
  error by design.
- Tags, layouts and optional representations are ABI: the backend, the runtime and the
  differential corpus must agree. A tag without a lowering (or the reverse) is an I4 bug.
- Panic sites use `lox_panic(line, column, code, message)` (ADR-0075). The line/column must
  be the same one the tree-walk reports — the call paren, not the callee; never 0.
- Runtime errors exit 70; `Stack overflow.` is catchable as `RuntimeError`.

## Determinism

I3 applies inside C too: no address, PID, timestamp, absolute path or hash order may reach
stdout/stderr. `tests/test_determinism.py` runs the binary and compares bytes.

## Style and safety

- All output goes through `lox_print_*` (UTF-8 correct); no stray `printf`/`fprintf`.
- Allocations go through the GC API; no raw `malloc` for language values.
- Bounds-check buffers and string lengths; a C crash is not a Lox error.
- Keep each `.c` unit focused on its domain (core, objects, strings, containers, numeric,
  kernel, proc) and declare new symbols in `lox_runtime.h`.
- Native-only capabilities must be refused by the interpreter (`E3021`, ADR-0128) and by the
  sandbox; the runtime is not the place to decide policy.

## Tests

```bash
uv run pytest -m backend -q          # builds every manifest case; needs libgc
make check                           # full gate, includes the backend
```

A new primitive or ABI change needs a differential case (three channels: stdout, stderr,
exit code) and, when it has a budget, an executable budget test.
