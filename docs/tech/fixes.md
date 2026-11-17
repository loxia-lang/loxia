# Reliable fixes: who produces them, what is safe, and what is left for later

**Status:** `W1001`/`W1002` (`safe`); `E2001`/`E2002`/`E2009`/`E3002`/`E3003`/
`E3015`/`E3016`/`E3018` (`unsafe`); `E3004` (`safe` in a local function/lambda, `unsafe` in
the public API); `loxia fix` (safe-only) and `codeAction` implemented (2026-11-16).
**Decision:** [ADR-0093](../adr/0093-cli-agent-friendly-e-reparo.md) (repair schema and
protocol), [ADR-0075](../adr/0075-diagnosticos-estruturados.md) (diagnostics),
[ADR-0090](../adr/0090-lsp-escopo-e-hospedagem.md) (consumer LSP).

## Golden rule

A fix is not an editor heuristic. The producer has to be the **phase that owns the semantic
proof**:

| Layer | Role |
| --- | --- |
| Resolver | scope, declaration, capture, mutability |
| Checker | type, inference, flow |
| Parser | syntax error (almost never has an unambiguous local edit) |
| Loader | import/module (needs to prove purity) |
| **LSP / CLI / MCP / agent** | **consumer**: applies/renders, does not invent `safe` |
| `loxia fmt` | formatting, not `fixes[]` |

A fix is only `safe` when the producer can prove that the edit:

1. preserves behavior (no side effect, no removal of a possible exception);
2. does not change name resolution (scope/shadowing/capture);
3. does not change the type or the public API;
4. is atomic, deterministic and idempotent;
5. passes the test apply → reparse → `--check` → run before/after (I1).

Without proof, the most it can be is `unsafe`: useful as an editor quickfix, never applied by
`loxia fix` nor by an agent without confirmation.

## Current model

`loxia_core/diagnostics/diagnostic.py`:

```text
Applicability = safe | unsafe
Edit(span, new_text)
Fix(applicability, message, edits[])
Diagnostic(..., fixes=(Fix, ...))
```

The JSON envelope exposes `diagnostics[].fixes[]`; `span` is half-open with `offset` in UTF-8
bytes. The schema is additive (v1): `fixes: []` when there is no candidate.

## Who can be a producer

### `safe` (few and conditional)

| Code | Phase | Condition for `safe` | Risk if ignored |
| --- | --- | --- | --- |
| **W1002** unused import | Resolver/Loader | modules only have declarations (the loader rejects an executable statement) and imports are **not re-exported**; with no use as a value/type, removing the line is safe | removing an import used as a type/value or re-exported |
| **W1001** unread local | Resolver | renames the declaration to a unique `_unused_N` (does not remove it); the initializer keeps running | the new name colliding or changing shadowing (mitigated by the name set) |
| **E3004** missing annotation | Checker | **exact** type of a literal default or of equal literal `return`s, in a local function/lambda (does not change the public API); no `<error>`/type var | annotating `Any`/a wrong inferred type changes the check |

Implemented: **W1001** (rename), **W1002** (remove import; structural purity: the loader
only accepts declarations in a module and imports are not re-exported), **E3003**
(did-you-mean), **E2002** (local `val`→`var`), **E2009** (field `val`→`var`) and **E3004**
(exact annotation; `safe` only in a local function/lambda).
Module purity **is already guaranteed by the loader**: there is no way for an import to run a
top-level statement, so the residual risk is only use/re-export, covered by the conservative
scan (value + type annotation).

### `unsafe` (quickfix, never automatic)

| Code | Possible fix | Why it is not safe |
| --- | --- | --- |
| **E3003** undefined name | replace with `did you mean 'x'?` | it may be a new variable, not a typo; fuzzy suggestion |
| **E2001** duplicate variable | rename the second one + all uses (implemented) | changes which binding each use resolves to |
| **E2002** assignment to `val` | change `val`→`var` (implemented) | changes capture/mutability and behavior |
| **E2009** immutable field | change `val`→`var` on the field (implemented) | changes the API and capture semantics |
| **E3016** uninitialized field | add `= <default>` (implemented for primitives/optionals) | the default is a choice; no single default for classes |
| **E3018** return path | add `return <default>` (implemented for primitives/optionals) | the value is the author's intent |
| **E3002** arity | remove extra arguments (implemented; missing ones have no fix) | it is not known which argument is left over |
| **E3015** invalid override | rename the method (implemented) | it may be an intentional override with the wrong signature |
| **E3004** annotation in the public API | annotate with the exact type (implemented) | adds a type to the public signature; the author may want another type |

### No reliable fix

- `E3001`/`E3007` type mismatch/operands: there is no local edit that preserves the intent.
- `E1001`–`E1007`: syntax; the formatter fixes spacing, not a structural error.
- `E4001` unsupported backend: it is not a program error.
- `R1xxx`: runtime; it depends on input/state, not on a source edit.
- `C0001`: timeout; it is not source.
- E2001 with uses outside the scope or a name collision: the fix only covers the local binding and its resolved uses.
- E3004 without an exact type (parameter without a default, field without an initializer, non-literal `return` or discordant types): the annotation would be a guess.

## Initial batch

1. ✅ **W1001 `safe`**: renames the declaration to `_unused_N` (preserves the initializer).
2. ✅ **E3003 `unsafe`**: replaces the token with the candidate from `help`; `isPreferred: false`.
3. ✅ **W1002 `safe`**: removes the unused import line; structural purity of the loader.
4. ✅ **E2002/E2009 `unsafe`**: changes `val`→`var` in the local/field; never auto-applied.
5. ✅ **E2001/E3016/E3018/E3002/E3015**: rename with uses, primitive default, default
   return, removal of extra arguments and method rename.
6. ✅ **E3004**: marks `safe` in a local function/lambda and `unsafe` in the public API; only
   with a literal default or equal literal `return`s. Without an exact type, it emits no fix.

## Application

- `loxia fix` (implemented): applies only `safe`, `--apply` (dry-run by default), limit of 10 iterations,
  atomic application per fix, conflict detection and `no-progress`.
- LSP `codeAction`: shows `unsafe` as a quickfix; `safe` may be `isPreferred`.
- MCP: exposes `fixes[]`; an agent may propose edits, but only the compiler marks `safe`.
- Never: auto-apply `unsafe`, generate a fix from a message/`help` without structure,
  edit multiple files without a module map.

## Open questions

- Initializer purity is no longer needed for W1001: renaming preserves execution.
- Modules do **not** have executable statements (the loader rejects them); W1002 is structurally safe.
- Does `fixes[]` live in the `Diagnostic` (yes, current decision) or in a separate catalog by
  code? The current model avoids a second source.
- Multi-file fix (renaming a module symbol) stays out until `loxia fix` and
  `WorkspaceEdit` with a module map exist.
