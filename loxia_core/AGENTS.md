# loxia_core — engine internals

Scoped context for the Python engine. The root [`AGENTS.md`](../AGENTS.md) still applies;
this file adds the rules that only matter inside `loxia_core/`.

## Layers

The dependency direction is a contract, not a suggestion:

```
diagnostics, frontend      (base)
thir                       may import base only (contract between checker and engines)
loader                     may import base + bundle
execution                  may import base
semantics                  may import base + execution + thir
backend                    may import anything in loxia_core
loxia_core                 NEVER imports loxia/ (the tooling layer)
```

Policed by `tests/test_package_layers.py`. One declared exception:
`frontend/ast_printer.py` imports `execution.values` (the debug dump formats dynamic values).
Any new upward edge needs a reason and an entry in that test's `ALLOWED` set — not a comment
buried in the diff.

Canonical module map: [`docs/tech/arquitetura.md`](../docs/tech/arquitetura.md).

## AST and visitors

- Nodes are `@dataclass(frozen=True, eq=False)` and inherit from `Expr`/`Stmt`. Identity is
  the key used by the resolver; do not switch to structural equality.
- Every node needs: a `Visitor` protocol method, `accept`, a parser production and an
  `AstPrinter.visit_*`. mypy strict catches a missing visitor; the dump and the LSP will not
  forgive a missing printer method.
- The AST is manual and guarded ([ADR-0117](../docs/adr/0117-ast-manual-e-cobertura-de-visitantes.md));
  do not generate it without a new ADR.

## Backend control flow

- Lowering control goes through [`control_ir/`](backend/control_ir) (ADR-0153): blocks, phi,
  terminators and cleanup depth. `Lowerer.builder` is wrapped by `ControlIRBuilder`; new code
  uses `ControlIR.new_block`/`ControlIRBuilder` instead of calling `llvm_ir.append_block` or
  `builder.phi` directly.
- `tests/test_control_ir.py` covers C1-C7 and `tests/test_control_ir_docs.py` keeps the
  reference table complete. The page is [`docs/tech/control-ir.md`](../docs/tech/control-ir.md).
- The IR is backend-internal: do not serialize it, expose it as API or replace THIR with it.

## Diagnostics

- One `ErrorReporter` per run, injected into scanner, parser and interpreter. There is no
  global error state; never reintroduce it.
- Syntax: `reporter.error(...)` and `ParseError` (exit 65). Runtime: raise the internal
  `LoxRuntimeError(token, message)` (exit 70). In the language it surfaces as `RuntimeError`
  ([ADR-0078](../docs/adr/0078-nome-loxia-extensao-lx.md)).
- The token matters: the error site must match the backend panic site. Never use a synthetic
  line-0 token.

## Values and the numeric model

- Language values are `object` + `assert isinstance(...)` at the boundary; do not invent a
  wrapper type for `nil` (`nil` is `None`).
- `Int`/`Float` live in `execution/numeric.py`; `str`/`repr` formatting has a single source
  in `execution/values.py` (`stringify`/`repr_value`). Do not duplicate formatting.
- **`isinstance(True, int)` is `True`**: use `is_number`/`is_int`; never
  `isinstance(x, (int, float))`.
- i64 bounds live in `loxia_core/numeric_bounds.py` (leaf). The scanner imports them from
  there, not from `execution`.
- A new value type is not done until it has: truthiness in the backend, a tag/layout, runtime
  ABI, `stringify`, equality, iteration/`is`/`as` behavior where applicable and a differential
  case. Missing one is an I4 bug that `--check` cannot see.

## Names and modules

- Absolute imports only: `from loxia_core.<package>.<module> import Y`.
- A new module in `loxia_core/` must not shadow a stdlib module name
  (`tests/test_stdlib_shadowing.py`). That is why the numeric model is `numeric.py`, not
  `numbers.py`.
- `Int`, `Float`, `math` (and `Bytes`) are reserved native namespaces. Adding a reserved name
  touches `execution/prelude.py`, the checker pre-declaration and the lowering — all three.
- No `print()` debugging in `loxia_core/`; use the REPL or `--dump-ast`.

## Before you finish

`make check-fast` green, plus the layer test. If you touched semantics, the spec and an ADR
go in the same commit. If you touched the backend boundary, run `pytest -m backend` too.
