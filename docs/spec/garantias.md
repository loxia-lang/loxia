---
sources:
  - tests/corpus_manifest.py
  - tests/test_backend.py
  - tests/test_determinism.py
  - loxia_core/backend/**
  - runtime/**
  - loxia_core/semantics/checker.py
---

# Guarantees — what the language promises

This page is the **contract** with whoever uses the language (or builds tooling on top of
it). It does not describe syntax or semantics — that is in
[lexicon](lexico.md), [syntax](sintaxe.md), [semantics](semantica.md) and
[errors](erros.md). Here live the promises that survive new features.

The decisions behind these guarantees are in
[ADR-0014](../adr/0014-identidade-e-invariantes.md) (I1–I3),
[ADR-0059](../adr/0059-i4-check-limpo-compila.md) (I4) and
[ADR-0074](../adr/0074-gc-boehm-e-contrato-de-memoria.md) (memory; it replaces
[ADR-0060](../adr/0060-orcamento-de-memoria.md)).

## The four guarantees

| # | Guarantee | Status |
| --- | --- | --- |
| **I1** | Same program, same result: the interpreter **is** the specification | 🟡 covers the declared corpus (table below) |
| **I2** | Nothing happens implicitly | ✅ holds today |
| **I3** | Observable determinism: same input ⇒ same bytes | ✅ holds today and is tested in CI |
| **I4** | Clean `--check` ⇒ the backend compiles (or refuses only the declared gap) | ✅ holds today and is tested in CI |

### I1 — Executable equivalence

The tree-walk is the **normative definition** of the language. Every program in the declared
corpus must produce the **same stdout (bytes)**, the **same stderr** and the **same exit code**
in both engines; if they diverge, the bug is in the backend.

The corpus is the entire conformance corpus, **annotated and classified by level** in
`tests/corpus_manifest.py`. Each case is in `LEVELS` (the backend compiles and agrees),
`PENDING` (the `--check` passes, the backend still refuses with **65** and the message
`... is not supported by the backend yet.`), `NEGATIVE` (fails on purpose in the `--check`)
or `COMPILE_ERRORS` (also fails on purpose in the `--check`, but is never executed: it is
covered by the structured diagnostics snapshot). A case only enters `LEVELS` when the three
channels match; promotion is monotonic and the differential test never compares against a
hand-written expectation. The `PENDING` list is public: it is the honest record of what is
missing, not a secret.

<!-- levels:start -->
| Level | Cases that compile and agree (I1) |
| --- | --- |
| `l0` | 4 |
| `l1` | 7 |
| `l2` | 20 |
| `l2.5` | 4 |
| `l3` | 14 |
| `l4` | 12 |
| `l5` | 30 |
| `l6` | 98 |
| `k0` | 2 |
| `t1` | 6 |
| `t2` | 22 |
| `t3` | 7 |
| `t4` | 3 |
| `t7` | 3 |

**232 cases** across 14 levels compile and agree; **1 in `PENDING`** (`bytes_method_value` (l6)); **7 negative** on purpose.
<!-- levels:end -->

Levels not yet implemented reject with an **explicit compilation error**
(exit 65), never with silent lowering.

The comparison is per channel: when stdout and stderr go to the **same** descriptor
(`2>&1`), the interleaving order of the two outputs is not part of the guarantee.

There is no promise that interpreted and compiled code have the same **speed**
or the same memory consumption. The same observable result includes **stderr byte for byte**,
so the runtime stack trace is also identical in both engines
([ADR-0089](../adr/0089-stack-trace-de-runtime.md)).

#### Engine layers: core, ambient and native-only

I1 covers **core**: features whose semantics both engines implement and that are in the
corpus. Two other layers are declared, and neither promises equivalence
([ADR-0128](../adr/0128-contrato-de-motores.md)):

| Layer | Promise | Runs on | Refusal |
| --- | --- | --- | --- |
| **core** | I1 + I3, in the corpus | interpreter and native | — |
| **ambient** | outside I1/I3; fixed-input tests | wherever the host allows | denied by `--sandbox` when it is a host capability |
| **native-only** | no equivalence promise; binary semantics only | `--emit=exe` | **the interpreter refuses at compile time** |

The three labels are a **projection of two independent axes**: determinism (`ambient`) and
engine support (`native_only`). A capability may be native-only and ambient at the same time
(a thread) or native-only and deterministic (pure SIMD); the label only decides the display,
never the promise.

A native-only capability is **refused**, never silently different:

```
error[E3021]: `sqlite.createFunction` is not supported by the interpreter; build with `--emit=exe`.
```

The refusal is a compilation error (exit 65), points at the call site and happens before any
execution. `loxia check` is engine-agnostic and accepts every layer; `run`/REPL refuse
native-only, and `build` only refuses the declared backend gap (`E4001`, I4). The layer of
every public primitive is published by `loxia capabilities --json`.

#### Stack budget ([ADR-0077](../adr/0077-limite-de-pilha.md))

The binary and the tree-walk count **Lox activations** (function, method, lambda, `init` and
constructor) against the same limit: **10,000 calls**. Call 10,001 is `R1015`
(`Stack overflow.`), exit 70, catchable by `try`/`except RuntimeError`, with the position of the
callee's declaration and the stack trace of the active frames. Native calls and built-in
exception constructors do not count. Constructor + `init` count as two activations.

- The binary reserves a 128 MiB stack soft limit (`setrlimit`) before running; the
  declared budget is 64 MiB. On platforms with a smaller hard limit, the limit is clamped.
- The tree-walk raises `sys.setrecursionlimit` to 500,000 (internal budget, not a
  contract).
- Above 10,000 calls the error is deterministic and the trace is trimmed (5 innermost + 5
  outermost + elision), with no address/time in the output.

#### Memory budget ([ADR-0074](../adr/0074-gc-boehm-e-contrato-de-memoria.md), [ADR-0087](../adr/0087-heap-cap-e-self-hosting.md))

The binary uses a conservative **Boehm GC**, with a **default hard cap of 512 MiB** of collected
heap (ADR-0074 set 128 MiB; ADR-0087 raised the default). Exceeding the cap is `exit 70`
+ `Out of memory.` on stderr, without a traceback, and the ceiling does **not** depend on the
environment.

- The build can choose another ceiling with `--max-heap=SIZE` (only `--emit=exe`; default `512M`,
  range `32M..8G`). The value is embedded in the binary; it is neither an env var nor a runtime flag.
- **I1 covers programs whose peak live memory fits in 64 MiB**. Above that, the
  program is outside the corpus: it may run (up to the cap), but there is no guarantee of result
  or of failure point. Self-hosting is declared outside I1 until its own corpus exists.
- The interpreter has **no** ceiling (Python GC) and can run programs that the binary
  refuses — the asymmetry is declared.
- Because Boehm is conservative, the **exact point** at which a program above the cap overflows
  is not deterministic: false roots depend on the stack and on ASLR. What is stable is the
  channel, the message and the exit code. Programs that print before overflowing do not have the
  stdout prefix covered by I1.
- **Native module allocations are outside this cap.** The Rust regex engine allocates outside
  Boehm: its contract is per compiled program (`size_limit` 10 MiB, `max_prog_size` 100,000
  and `delegate_dfa_size_limit` 2 MiB in `Mode.Full`; ADR-0131 §2.1), not a total byte budget.
  A variable lookbehind whose reverse DFA needs more than the 2 MiB cache fails with the
  stable `size` kind instead of growing. Close regex handles to release the memory.

#### Monomorphization budget ([ADR-0063](../adr/0063-orcamento-monomorfizacao.md))

The native backend monomorphizes generics; each specialization costs code. Per compilation:

- at most **256** specialized functions and **256** specialized class layouts;
- generic type nesting up to **8** constructors;
- a mangled generic name up to **1024 bytes**.

Exceeding any limit is a declared backend gap, not a type error: exit 65, code `E4003`, and
no partial object/binary. The checker still accepts the program and the tree-walk is
unaffected. The initial limits were validated against the corpus and a synthetic nesting
case (max 15 functions/4 classes/depth 1 in the corpus; the ceiling costs ~1.2 MiB and
~0.33 s locally); see [`bench/README.md`](../../bench/README.md).

### I2 — Nothing happens implicitly

No conversion, coercion, truncation, rounding, truthiness or fallback happens
without being written in the code.

```lox
print(1 + 2.0)      # 3.0  — Int -> Float promotion, arithmetic only
print(1 + "1")      # error — no coercion between number and string
print(4 / 2)        # 2.0  — `/` is always Float
print(-7 // 2)      # -3   — truncated
print(1 == 1.0)     # true — numeric equality with promotion
print(1 == "1")     # false — different types are never equal
if ("") { print("empty is truthy") }  # prints: only nil and false are falsy
print((nil ?? 0))   # 0    — `??` replaces nil only
print(3.9 as Int)   # 3    — explicit cast, truncated
```

In **storage** there is no promotion: `val x: Float = 2`, `x = 2`, `f(2)` and `return 2` in a
`-> Float` function are type errors; write `2.0` or `2 as Float`
([ADR-0059](../adr/0059-i4-check-limpo-compila.md)).

If you want the conversion, it is written: there is no "the compiler sorts it out".

### I3 — Observable determinism

Same input + same flags ⇒ **same bytes** of output and of diagnostics. This holds for
stdout, stderr, exit code and `--dump-ast`. The following are forbidden in the output: memory
address, PID, timestamp, absolute path, `set`/`dict` order, locale and directory order.

The 1.0 prelude does not read the clock or other ambient inputs: `clock` was removed
([ADR-0026](../adr/0026-freeze-1.0.md)). The **ambient functions** declared in
[ADR-0072](../adr/0072-stdlib-batteries.md) §5 — `args`, `os.getenv`, `time.now`,
`time.sleep`, `std.fs`, `std.io` reads, `std.proc`/`process.*` and kernel
file opening — are explicitly **outside** this guarantee and the differential corpus; they
have their own test with fixed input. `std.fs.listDir` sorts entries by byte precisely so as
not to leak the directory order.

**Streaming (not I3, it is an I/O contract):** `io.write`/`io.writeErr` flush on every
call in both engines, and `io.flush()` forces both channels. `print` follows the stdio
buffer (block on a pipe, line on a tty) — as in the oracle. Without the flush, a process that
reads another's output (pipe, JSONL, MCP, LSP) hangs waiting for bytes that stay in the buffer
([ADR-0094](../adr/0094-kernel-io-flush-e-read-utf8.md)); the
`test_io_write_flush_antes_de_bloquear_no_stdin` test polices this, because the byte comparison
at the end of the process does not distinguish "flushed" from "flushed on exit".

The implemented `math.*` is deterministic: `abs`, `min`, `max`, `clamp`, `floor`, `ceil`,
`round`, `trunc` and `sqrt`. `log`, `exp`, `sin`, `cos`, `tan` and `pow` depend on libm and
stay **outside** 1.0/I3 ([ADR-0029](../adr/0029-conversoes-math.md)). `--debug` changes
overflow behavior by design; the guarantee holds for the same flags.

```bash
./lox program.lx > a.txt 2>&1   # twice, on different machines/flags
./lox program.lx > b.txt 2>&1
cmp a.txt b.txt                   # identical
```

The wording of an error message **may change between versions**; the exit code does not
(`65` compilation, `70` runtime). Diagnostic **codes** are stable and never
reused ([ADR-0075](../adr/0075-diagnosticos-estruturados.md)); the output is sorted
by `(file, offset, code)`, deduplicated, limited by `--max-errors` and the displayed path
is always relative. The JSON carries `schema_version`.

### I4 — Clean `--check` ⇒ it compiles

Every program that passes `--check` compiles. The **only** acceptable refusal in lowering is the
gap already declared and classified:

```
... is not supported by the backend yet.
```

Any other error after a clean check is an I4 violation. The checker is the **source of
truth** for types; the backend consumes the published types and does not invent its own rule.

```bash
uv run main.py --check prog.lx      # exit 0 …
uv run main.py --emit=exe prog.lx   # … so this compiles (or refuses only "not supported")
```

It is the operational corollary of I1: without it, the same program could give `2` in the
interpreter and a type error in the compiler, with the user receiving two contradictory
diagnostics ([ADR-0059](../adr/0059-i4-check-limpo-compila.md)).

## Design principles

They are not testable guarantees like I1–I4: they are the criteria that guide syntax, type
and stdlib decisions. What is still aspirational is marked.

1. **No noise** — optional `;`, `elif`, one-line body; the syntax should not require
   ceremony for the common case.
2. **Expressions first** — almost everything produces a value; `if`/`match`/block as an
   expression stayed **outside 1.0** ([ADR-0026](../adr/0026-freeze-1.0.md)); ternary and `??` cover the
   common case.
3. **Immutable by default** — `val`/`var` implemented; parameters are immutable and `var x`
   unlocks mutation. Arguments in [ADR-0005](../adr/0005-val-var-imutabilidade.md).
4. **Optional types, not ceremony** — annotate only where it helps; in `--check` local
   inference already exists and parameters/return remain signed. Inferring a parameter without
   an annotation was postponed; see [ADR-0020](../adr/0020-assinaturas-explicitas.md).
5. **Fail early and clearly** — spans, caret and stack trace exist today
   ([ADR-0075](../adr/0075-diagnosticos-estruturados.md),
   [ADR-0089](../adr/0089-stack-trace-de-runtime.md)).
6. **Predictable** — no implicit coercion, no `nil` surprise; that is I2.
7. **Identity = invariants, not features** — the contract is
   [ADR-0014](../adr/0014-identidade-e-invariantes.md); every feature goes through the admission
   gate.

## How this is verified

- [`tests/test_determinism.py`](../../tests/test_determinism.py) runs cases with
  different `PYTHONHASHSEED` and requires byte-for-byte equality (I3), besides forbidding
  volatile data.
- [`tests/test_backend.py`](../../tests/test_backend.py) compiles each manifest case and
  compares stdout/stderr/exit with the interpreter (I1), sweeps the corpus requiring that a
  clean check never becomes a type error (I4) and documents the memory budget.
- The golden cases in `tests/cases/` pin down the I2 refusals (mixed coercion, `nil`
  surprise, division by zero, promotion in storage).
- `tests/test_docs_consistency.py` prevents this page from falling behind the
  manifest and the CLI.

## What is **not** promised

- **Speed.** The tree-walk is the oracle, not the final product; benchmarks serve to
  detect regression, not to compete with Rust.
- **Message wording between versions.** Only the exit code (and, in the future, the diagnostic
  code) is stable.
- **Compatibility with book Lox.** The language diverged on purpose
  (`val`/`var`, `Int`/`Float`, `class B(A)`); there is no compatibility mode.
- **ABI, bytecode or object format stability.** They do not exist yet, and when they
  exist they will not be a public contract in the first version.
- **Timing.** Nothing promises when a `nil`/object is freed, nor finalization order —
  precisely so as not to break I1.
- **Native-only capabilities under `run`/REPL.** They are refused at compile time
  (`E3021`); there is no interpreted fallback and no promise that the interpreter can run
  every program ([ADR-0128](../adr/0128-contrato-de-motores.md)).
- **Programs above the memory budget** in the binary (default hard cap of 512 MiB and
  I1 up to 64 MiB of live memory) and **above 10,000 Lox calls** (R1015 is the limit).

## Revisit

If a guarantee turns out to be impossible for a feature, that is **not** resolved by
loosening the text silently: a new ADR says what stops applying and why
(see [ADR-0014](../adr/0014-identidade-e-invariantes.md), "How to verify").
