---
sources:
  - loxia_core/backend/control_ir/**
  - loxia_core/backend/lower.py
  - loxia_core/backend/lower_base.py
  - loxia_core/backend/lower_exceptions.py
  - loxia_core/backend/lower_enums.py
  - loxia_core/backend/lower_class_codegen.py
  - loxia_core/backend/lower_functions.py
  - tests/test_control_ir.py
  - tests/test_control_ir_docs.py
---

# Control IR

Backend-internal control graph used by the LLVM lowering. It records **blocks, phi,
terminators and the cleanup depth** while the `llvmlite` builder runs; it is not a public
IR, it is not serialized and it does not replace the future THIR. The decision and its
trade-offs are in [ADR-0153](../adr/0153-ir-de-controle-desenho.md).

The implementation is transient: it lives in the Python backend (F1-F4) and is
reimplemented for the self-hosted compiler. What is durable is the model: the invariants,
the cleanup matrix and the lifecycle below.

## What it is not

- Not a THIR: it has no types, bindings or desugaring. It consumes values already lowered.
- Not an instruction IR: expressions keep emitting directly through `llvmlite`; only
  control is modelled.
- Not an optimizer: it preserves the edges the lowering asks for.
- Not a public contract: no serialization, no stable API and no `--dump-ir` in F1.

## Model

`loxia_core/backend/control_ir/` has four pieces: `model.py` (the graph), `builder.py`
(the target adapter), `verify.py` (C1-C7) and `dump.py` (deterministic S-expression).

| Node | Role | Terminator? |
| --- | --- | --- |
| `ControlFunction` | owns the blocks of one target function, in creation order | - |
| `Block` | basic block with phi nodes, one terminator and its cleanup depth | no |
| `Phi` | merge of one value per predecessor | no |
| `Br` | unconditional branch | yes |
| `CondBr` | conditional branch with two successors | yes |
| `Ret` | return with an optional value | yes |
| `Unreachable` | path that does not continue (raise/panic) | yes |

Values are opaque handles to the target. `match` lowers to a chain of `CondBr` plus a
`Phi`; there is no pattern/switch node in F1.

Every assignment to `Lowerer.builder` is wrapped by `ControlIRBuilder`. Control operations
(`branch`, `cbranch`, `ret`, `ret_void`, `unreachable`, `phi`) are recorded; everything else
is forwarded to the `llvmlite` builder, so arithmetic, calls, loads and stores stay direct.
`ControlIR.new_block` is used by the migrated lowerers (exceptions, `match`, class codegen)
so blocks are registered at creation instead of only when first observed.

## Invariants

`verify_function` runs on the model before emission. A violation is an internal compiler
error (`ControlIRError`), never a user-facing `not supported by the backend yet`.

| ID | Rule | Failure it prevents |
| --- | --- | --- |
| C1 | Every block has exactly one terminator, recorded and emitted. | Invalid LLVM / implicit fallthrough. |
| C2 | Every successor belongs to the function; the entry has no predecessors. | Branch to a foreign/unknown block. |
| C3 | Every phi has one incoming per predecessor, no duplicates. | Missing or swapped phi value. |
| C4 | A used value is defined in a block that dominates the use; for phi, it dominates the corresponding predecessor. | Use before definition / wrong value. |
| C5 | The cleanup depth is balanced at the end of the function. | `finally` skipped or run twice. |
| C6 | A value does not cross a cleanup boundary outwards (definition depth ≤ use depth). | Reading a value after its region was unwound. |
| C7 | Block labels and phi labels are unique; block order is the creation order, covered by the deterministic dump test. | Nondeterministic `.ll` / binary (I3). |

C8 (token/span of the error site) is policed by the existing diagnostics and differential
tests, not by the structural verifier: the model deliberately does not carry language
spans. The cleanup behaviour itself is covered by the differential corpus, including
[`try_return_cleanup.lx`](../../tests/cases/try_return_cleanup.lx),
[`break_finally.lx`](../../tests/cases/break_finally.lx),
[`try_finally_scope.lx`](../../tests/cases/try_finally_scope.lx) and
[`try_continue_cleanup.lx`](../../tests/cases/try_continue_cleanup.lx).

## Cleanup

The lowering keeps the lexical `CleanupContext` stack; the control IR tracks its depth and
the verifier checks that it ends at zero. `CleanupContext.unwound` prevents a context that
was already consumed by `_run_cleanups` from decrementing the depth twice when the lexical
`_pop_cleanup` runs later.

| Exit | Regions that run | Then |
| --- | --- | --- |
| normal end of `try` | the current `try` | `br end` |
| `return` | all regions up to the function | `ret` |
| `break` | only regions opened inside the loop | `br loop.end` |
| `continue` | only regions opened inside the loop | `br loop.cond` |
| `raise` | up to the handler/function | rethrow/throw |
| `return` inside `finally` | only outer regions (never itself) | `ret` |
| `raise` inside `finally` | only outer regions | new raise |
| `finally` completes with a pending action | the current `finally` is already emitting (no re-entry) | pending action resumes |

The model exposes `push_cleanup`, `pop_cleanup` and `unwind_to`. The lowering calls
`push_cleanup`/`pop_cleanup` through the lexical cleanup contexts and reduces the depth as
`_run_cleanups` walks them, which is enough for C5 to catch unbalanced paths. `unwind_to` is
available for a future explicit unwind cut.

## Recipes

`try/finally` with `return`:

```lox
fn f() -> Int {
  try {
    return 1
  } finally {
    print("cleanup")
  }
}
```

The return value is materialized before the unwind (C6); the cleanup runs once; the `ret`
happens after it. If the `finally` returns, its terminator wins and only outer regions run.

`match` with a result phi:

```lox
val label = match k {
  0 => "zero"
  _ => "other"
}
```

Both arms branch to `match.end`, which receives one `Phi` with one incoming per predecessor.
An arm that terminates contributes no incoming and no edge.

## Verification and tests

- `tests/test_control_ir.py`: one case per C1-C7 (valid and invalid), deterministic dump,
  `verify_all` raising with function/block context.
- `tests/test_control_ir_docs.py`: every model node appears in the table above.
- `make test-backend`: differential corpus, including the cleanup cases; I1 must hold.
- `--emit=ll`: labels/order may change when a construct migrates, but must be deterministic;
  program stdout/stderr/exit must not change.

## Lifecycle

- **F1 (now)**: Python implementation, used by exceptions, `match` and class codegen.
- **F2**: THIR changes the lowering input, not the control IR. THIR is a tree; control stays
  here. The THIR gets its own spec/snapshot; this page stays internal.
- **F3**: the interpreter/oracle freezes as THIR eval; the control IR does not change because
  it belongs to the compiler path.
- **F4**: the compiler is rewritten in Loxia; the LLVM builder provides blocks/phi and the
  compiler keeps the cleanup discipline. This page is the porting input, then the Python
  implementation is frozen/archived with the rest of the backend (ADR-0149, G5).
- **Never**: public spec, serialization, versioning or a stable API.

## Further reading

- [ADR-0153](../adr/0153-ir-de-controle-desenho.md) — the design, alternatives and costs.
- [ADR-0065](../adr/0065-hir-lite-controle.md) — the trigger.
- [ADR-0149](../adr/0149-motores-primarios-thir-e-congelamento.md) — THIR, engines and the
  freeze plan.
- [Architecture](arquitetura.md) — where the module sits.
