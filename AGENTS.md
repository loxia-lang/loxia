# AGENTS.md — working context for AI agents

This file is **versioned and reviewed like code**. It is the canonical context for any
agent (Claude Code, Codex, Cursor, DSH, …) working on the repository; the human-facing
version of most rules is [`CONTRIBUTING.md`](CONTRIBUTING.md). Personal notes, bug history
and design opinions live in `NOTAS.local.md` (gitignored) — that file is a notebook, not a
rule source.

`tests/test_agents_docs.py` checks this file: the skill table matches `.dsh/skills/`, the
version example matches `loxia.__version__`, and every relative link resolves. Section
numbers are anchors used by the skills; do not renumber casually.

---

## 1. What this project is

**Loxia** — a tree-walking interpreter in Python and a **Lox** dialect born in *Crafting
Interpreters* (Part II / jlox). It is the book's Lox plus deliberate divergences: `val`/`var`
([ADR-0005](docs/adr/0005-val-var-imutabilidade.md)), separate `Int`/`Float`
([ADR-0006](docs/adr/0006-int-float-separados.md)), ranges/`for-in`
([ADR-0007](docs/adr/0007-ranges-e-iteracao.md)), `class B(A)`
([ADR-0008](docs/adr/0008-heranca-class-parens.md)), defaults/fields
([ADR-0009](docs/adr/0009-defaults-e-campos.md)), `--check`
([ADR-0010](docs/adr/0010-tipagem-estatica.md)), `fn`/`elif`/optional `;`
([ADR-0011](docs/adr/0011-fn-elif-ponto-e-virgula.md)), comments/`//`/`**`/bits
([ADR-0012](docs/adr/0012-comentarios-divisao-potencia-bits.md)) and
ternary/`??`/`?.`/escapes ([ADR-0013](docs/adr/0013-ternario-nil-aware-escapes.md)).

Medium-term goal: become its own language. (1) fluid syntax — optional `;`, `fn`,
`val`/`var`, interpolation, `?.`, `??`, `for x in`, `match`; (2) optional static typing with
inference — annotations where they help, argument checking against declared/unified types;
(3) LLVM backend in Python (`llvmlite`, optional extra) — **L0–L6 + T7 done**, contracts in
[ADR-0031](docs/adr/0031-backend-nativo.md), [ADR-0046](docs/adr/0046-closures-celulas-l4.md),
[ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md) and
[ADR-0048](docs/adr/0048-abi-classes-l5.md).

Order: finish the book → stabilize semantics → syntax/types → compile.

**Status is not duplicated here.** The plan is [`docs/roadmap.md`](docs/roadmap.md) (read
**Now** before proposing work); the generated corpus status is
[`docs/spec/garantias.md`](docs/spec/garantias.md); shipped behavior is
[`docs/spec/`](docs/spec/).

**Vocabulary — three spellings, three layers** ([ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md)):
**Loxia** is the language/product/package (the brand), **Lox** is the book dialect and the
normative oracle (the tree-walk), and **`Lox*`/`lox.`** are inherited names (`LoxClass`,
`LoxCallable`, `LoxRuntimeError`, `lox.ctor.*`) that are **not** to be renamed. Practical
consequence: the language-level runtime error is `RuntimeError`, but the Python class
carrying it stays `loxia_core/diagnostics/errors.py::LoxRuntimeError`. Do not "fix" that
asymmetry: they are different layers. Canonical source suffix: **`.lx`**
(`SOURCE_SUFFIX` in `loxia_core/loader/loader.py`).

---

## 2. Identity contract — read before proposing anything

The language is **not** defined by features (all are borrowed; see
[`docs/roadmap.md`](docs/roadmap.md) and [ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md)).
It is defined by four invariants ([ADR-0014](docs/adr/0014-identidade-e-invariantes.md),
[`docs/spec/garantias.md`](docs/spec/garantias.md)):

- **I1 — executable equivalence**: the tree-walk is the normative spec; interpreted and
  compiled runs must produce the same stdout/stderr/exit code, byte for byte. The differential
  test covers L0–L6 + T7 (`tests/test_backend.py`, three channels); the whole corpus only
  counts once annotated.
- **I2 — nothing happens implicitly**: no implicit coercion, no exotic truthiness, no
  surprise `nil`.
- **I3 — observable determinism**: same input ⇒ same bytes. Forbidden in output: address,
  PID, timestamp, absolute path, `set`/`dict` order. `tests/test_determinism.py` polices it;
  a failure there is a contract violation, not a flake.
- **I4 — clean check compiles**: a program that passes `--check` compiles; the only acceptable
  refusal in lowering is `not supported by the backend yet` (a gap declared in `PENDING`).
  The checker is the **single source** of types — the backend does not invent type rules.
  Policed by `test_i4_check_limpo_nunca_vira_erro_de_tipo_no_lowering`
  ([ADR-0059](docs/adr/0059-i4-check-limpo-compila.md)).

**Memory is contract**: the binary uses **Boehm GC**
([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md),
[ADR-0087](docs/adr/0087-heap-cap-e-self-hosting.md)), default **hard cap 512 MiB**
(build `--max-heap`), and I1 up to **64 MiB of live memory**; above that it is out of corpus.
`Out of memory.` is `exit 70`, but the exact failure point is not deterministic (conservative
collector). The **stack** has a separate contract
([ADR-0077](docs/adr/0077-limite-de-pilha.md)): 10,000 calls, 64 MiB budget, `R1015` /
`Stack overflow.` catchable. The interpreter has no ceiling — the asymmetry is declared, and
I1 holds **inside** the budget.

**Admission gate** (needs all four): does not violate I1–I4 · fits semantics the LLVM backend
can reproduce (or comes with a verifiable plan) · the absence genuinely hurts (not symmetry
with another language) · ships with a test that polices it. A feature that only buys surface
area is debt paid by codegen: structural `match`, extension methods, operator overloading,
named args and recoverable exceptions come after the LLVM MVP; implicit coercion never
enters. Refusing is part of the job.

**Syntax gate** ([ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md)): every syntax
addition or change needs **human approval** and four answers — does it replace an existing
spelling (or come from the stdlib)? is it locally decidable? does it fit current precedence?
does it have exactly **one** canonical form? — plus real pain, a test that polices it and a
declared LLVM impact. The agent **does not** add syntax on its own initiative; targeted
diagnostics without grammar changes do not count as a feature.

---

## 3. Layout, layers and invariants

```
source .lx
   │ Scanner           → list[Token]
   │ Parser            → list[Stmt] (frozen dataclasses)
   │ Resolver          → scope depths
   │ Checker (--check) → type errors before execution
   │ Interpreter       → effects (print, variables)
   │
   └─(--emit)→ backend: lower → llvmlite.ir → .o → cc → binary
```

| Package | Phase |
| --- | --- |
| `loxia_core/frontend/` | lexing → tokens → AST → parser; `ty.py` (annotations) and `ast_printer` |
| `loxia_core/semantics/` | `resolver` (scopes/`depth`) and the gradual `checker` |
| `loxia_core/execution/` | values, environment, objects, natives and `interpreter` |
| `loxia_core/diagnostics/` | `errors`, `error_reporter` |
| `loxia_core/loader/` | module loader (`import a.b` → `a/b.lx`), cycles (ADR-0073) |
| `loxia_core/backend/` | lowering and LLVM emission (opt-in via `--emit`) |
| `loxia/` | CLI, engine, LSP, MCP, formatter, test runner, docgen (tooling layer) |

**Layer rule** (policed by `tests/test_package_layers.py`): `diagnostics` and `frontend` are
the base; `loader` may import both plus the top-level `bundle` leaf; `execution` may import
the base; `semantics` may import base + execution; `backend` may import any of them;
top-level modules (`bundle`, `numeric_bounds`) are leaves; `loxia_core` **never** imports
`loxia/`. One declared exception:
`frontend/ast_printer.py` → `execution.values` (the debug dump formats dynamic values).
A new upward edge fails the gate; add an exception there only with a reason.

The canonical module map — including LSP/MCP/formatter/std/tools — is
[`docs/tech/arquitetura.md`](docs/tech/arquitetura.md). Read the scoped file before changing
a subtree:

| Subtree | Scoped context |
| --- | --- |
| `loxia_core/` | [`loxia_core/AGENTS.md`](loxia_core/AGENTS.md) |
| `runtime/` | [`runtime/AGENTS.md`](runtime/AGENTS.md) |
| `std/` | [`std/AGENTS.md`](std/AGENTS.md) |
| `tests/` | [`tests/AGENTS.md`](tests/AGENTS.md) |

### Precedence (lowest → highest)

`assignment` → `conditional` (`a if c else b`) → `coalesce` (`??`) → `or` → `and` →
`equality` → `comparison` (`< <= > >=`, `is T`) → `|` → `^` → `&` → `range` → `shift` →
`term` → `factor` (`* / // %`) → `as` (`x as T`) → `unary` → `**` → `call` → `primary`.
`call` chains `(...)`, `.property` and `?.property`; `range` is `..`; `**` is right-associative
and its right side accepts unary; bits bind tighter than comparison/equality.

### Semantics you must not get wrong

The full spec is [`docs/spec/semantica.md`](docs/spec/semantica.md); these are the ones that
cause bugs when forgotten:

- `Int` (i64) and `Float` (f64) are separate (ADR-0006). A literal without `.`/exponent is
  `Int`; `bool` is never a number.
- Promotion is only `Int → Float`; `Float → Int` is never implicit.
- `/` always returns `Float`; `//` is truncating integer division (Int only); `%` is the
  truncated remainder. Division/remainder by zero is a **runtime error**.
- `**` is right-associative; `Int` wraps on overflow (`2 ** 63` → `INT_MIN`).
- Bits (`& | ^ ~ << >> >>>`) are `Int`-only; shift count must be `0..63`; `>>` is arithmetic,
  `>>>` logical.
- Truthiness: only `nil` and `false` are falsy (`0`, `0.0`, `""` are truthy).
- `+` is number+number or string+string only; no mixed coercion.
- Equality across different types is `false`, except numbers with promotion (`1 == 1.0`);
  `NaN != NaN`.
- Strings are UTF-8; `len`/ordering are in code points; `chars(s)` is the explicit character
  access (`s[i]` does not exist); no normalization (ADR-0035).
- `a..b` is a lazy, reusable half-open `Range` of `Int`; `..=` does not exist (ADR-0007).
- `val` is immutable and needs an initializer; `var` may be empty (`nil`); fields are declared
  in the class body with `val`/`var` (ADR-0005/0009).
- Inheritance is `class B(A)`, one superclass, `super.m()` binds to the current `this`; `this`
  is implicit, there is no `self` (ADR-0008).
- No implicit coercion, ever (I2). Deterministic output, always (I3).

---

## 4. Commands

Python **3.13** (`.python-version`, `pyproject.toml`). The code uses PEP 695 generics.

```bash
uv run main.py                  # REPL
uv run main.py script.lx        # run a script
uv run python -m loxia          # same, via package
uv run main.py --version        # loxia 1.2.0
uv run main.py --dump-ast s.lx  # AST as S-expression, no execution
uv run main.py --check s.lx     # type check (does not run)
uv run main.py --debug s.lx     # check Int overflow at runtime
make test                       # full suite (includes native backend)
make test-fast                  # pytest without native/install tests, xdist (~15-20 s)
make test-backend               # native backend without slow Rust cases, xdist (~12 s)
make test-backend-all           # native backend including the slow Rust/regex cases
make smoke-backend              # one case per level, real-process path (~5 s)
make check                      # full gate: lint + format + types + tests
make check-fast                 # local loop: lint + format + types + tests + backend smoke
make bench                      # benchmarks vs baseline
uv sync --extra llvm            # enable the native backend (llvmlite)
uv run main.py --emit=ll prog.lx         # LLVM IR (inspection)
uv run main.py --emit=exe -o app prog.lx # native binary (needs libgc + cc)
```

Environment rules:

- **There is no `python` here**, only `python3` (3.12 — not the official runner).
- Running from the repo root is the supported path. `PYTHONPATH=loxia_core` no longer breaks,
  but it is not needed.
- If `uv` fails with `Could not acquire lock`/`Read-only file system`, use
  `UV_CACHE_DIR=$PWD/.uv-cache uv run ...` (already gitignored).
- `.venv/` and caches are not committed; `uv.lock` **is** versioned.
- The native backend needs `libgc` (Boehm, ADR-0074) for `--emit=exe`; without it the link
  fails with an install hint. On CI the runner installs `libgc-dev`.
- The 7 runtime units are compiled once and cached under `$TMPDIR/loxia-build-<uid>/runtime-<key>/`
  (`LOX_BUILD_CACHE=<dir>` isolates the cache).

---

## 5. Conventions

- Python 3.13, **no runtime dependencies**. New libraries require a conversation.
- Absolute imports `from loxia_core.<package>.<module> import Y`; never relative and never
  without `loxia_core.`.
- AST nodes are frozen with `eq=False` (identity): the resolver uses the node as a key, like
  the book's identity `HashMap`. Do not switch to structural equality.
- Optionals are `X | None`; visitors are `visit_*`; helpers are `_snake_case`.
- Type hints everywhere — `make type` runs **mypy strict**.
- Dynamic language values: `object` + `assert isinstance(...)`.
- **`isinstance(True, int)` is `True`**: in numeric checks use
  `loxia_core.execution.numeric.is_number` (or `is_int`, which excludes `bool`); never
  `isinstance(x, (int, float))` directly.
- `Int`, `Float` and `math` are **reserved native namespaces** (not classes). `Int.parse`
  works because the checker defines `NativeModuleTy`; do not treat `Int` as a regular value.
- Interpreter messages are in English (book/tests); public docs and this file are in English;
  ADRs and `docs/log.md` are in Portuguese; the task skills are bilingual today.
- No `print()` debugging in `loxia_core/`.
- Diagnostics: one `ErrorReporter` per run, injected into scanner, parser and interpreter.
  Syntax uses `reporter.error(...)`; runtime raises the internal `LoxRuntimeError` (which
  surfaces as `RuntimeError` in the language). Never recreate global error state.
- Small, readable diffs; do not reformat a whole file for a targeted change.
- A design decision → ADR in `docs/adr/`, summary in `docs/decisoes.md` **and** an update to
  `docs/spec/` in the same commit. Open discussion stays in Discussions › Ideas or a
  `decision` issue, never in an ADR.
- Observable behavior changed → `docs/spec/` in the same commit.
- Pages declare `sources:` in front matter; corpus status is **generated** (`make docs-sync`);
  freshness triage goes to `docs/log.md`.

Commits: short Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
Never commit `NOTAS.local.md`, `__pycache__`, `.venv` or caches. `docs/roadmap.md` **is**
versioned.

Branch flow (details in the `lox-git-flow` skill): `main` is release and only receives `dev`
(or an exceptional hotfix); `dev` is long-lived integration; work starts from `dev` on
`feat/*`, `fix/*`, `docs/*`, `test/*` or `chore/*` and enters `dev` via squash PR. Release is
a `dev` → `main` PR with a merge commit, then a tag from `main`. Never commit directly to
`main`/`dev`; never delete `dev`.

---

## 6. Tests and benchmarks

```bash
make test                              # everything (unit + golden + native backend)
make test-fast                         # without backend/install; xdist (local loop)
make test-fast TEST_JOBS=0             # serial, to debug one case
make test-backend                      # backend without slow Rust cases; xdist (~12 s)
make test-backend TEST_JOBS=0          # backend serial, to debug one case
make test-backend-all                  # backend including the slow Rust/regex cases
make smoke-backend                     # one case per level, real-process path (~5 s)
uv run pytest -m backend               # native builds only, serial
uv run pytest -k block                 # subset
uv run python -m tests.runner <filter> # golden cases without pytest
```

The backend dominates `make test`: each differential case compiles a binary and runs it, with
the oracle and the build **in the pytest process** (the binary itself in a subprocess;
[ADR-0133](docs/adr/0133-suite-rapida-in-process-e-xdist.md)). Runtime units are cached by a
hash of sources+headers/compiler/flags, so each build drops from ~0.55 s to ~0.15 s.
`make test-fast` runs the ~1.8k non-backend tests in **parallel** (`-n auto`) and skips the
wheel-install test; the loop is ~15-20 s. `make test-backend` runs the backend without the
`slow` Rust/regex cases with xdist (`-n auto`, `TEST_JOBS=0` for serial): ~12 s warm and
~13 s even with a cold crate cache. `make test-backend-all` (also `make test`, `make check`
and CI) runs the slow cases, and the first one pays the Rust crate build (~20 s).
`make smoke-backend` checks one case per level through the real-process path and is part of
`make check-fast`. `make test`/`make check`/CI stay serial. Use `make check-fast` while
iterating, `make test-backend` for native work and `make check` before committing.

Golden, official-suite and TOML-parity cases call `loxia.cli.main()` **in the pytest
process** (`tests/inprocess.py`) instead of one Python boot per case. That keeps the same
observable contract (stdout/stderr/exit code) at a fraction of the cost. Tests that need a
real process (hash seeds, signals/timeout, REPL stdin, sandbox, native backend) still use
`subprocess`; `LOX_GOLDEN_SUBPROCESS=1` forces the old golden path for debugging.

- `tests/cases/*.lx` are self-explanatory golden cases: `print(1 + 2)  # expect: 3`; errors use
  `# expect runtime error: MSG` (exit 70) or `# expect error: MSG` (exit 65).
- `tests/official/` is the Crafting Interpreters suite (chapters 10–13), adapted in
  `tests/test_official_suite.py`; 112 pass and 8 are documented `xfail`.
- `tests/runner.py` runs the CLI and compares stdout, stderr and exit code.
- There is no global error state: each `Loxia.run` creates its own reporter. In tests inspect
  `lox.reporter`, `scanner.reporter` or `parser.reporter`.
- **Every fixed bug gets a regression case in the same commit.**
- Do not adjust the expectation to make a test pass: if behavior is wrong, the code is wrong.

```bash
make bench                                  # compare against bench/baseline.json
uv run python bench/run.py --repeat 7       # more samples
make baseline                               # rewrite (only when intentional)
```

Benchmarks measure the whole process (including ~40 ms Python boot), so cases should last
>100 ms. Median of N runs; regression is >1.35× baseline. Benchmarks do **not** run on CI
(runner noise). Updating the baseline to "make it green" is forbidden.

---

## 7. Definition of Done

- [ ] Token/keyword (if any) and lexeme.
- [ ] AST node + `Visitor` + `accept`.
- [ ] Parser with a `Expect ... .` message.
- [ ] Interpreter with runtime validation.
- [ ] `AstPrinter` covers the node.
- [ ] Golden case (and a unit test when it fits).
- [ ] `make check` green (ruff + mypy strict + pytest, backend included).
- [ ] No `make bench` regression if a hot path was touched.
- [ ] `docs/roadmap.md`/help/examples updated if syntax or CLI changed.
- [ ] `docs/spec/` updated; design decision recorded in `docs/adr/` and `docs/decisoes.md`.
- [ ] Passed the [ADR-0014](docs/adr/0014-identidade-e-invariantes.md) admission gate.
- [ ] Passed the [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md) syntax gate (four
      questions, budget, human approval) — only if syntax changed.
- [ ] `tests/test_determinism.py` still green.
- [ ] I4 preserved: no clean `--check` program fails on a type error in `--emit`.
- [ ] `tests/test_docs_consistency.py` green.
- [ ] `make grammar` run if a keyword, operator or builtin name changed.
- [ ] Went through `lox-converge` (claim × delivery matrix) or declared in the PR what was
      left out.

---

## 8. Pitfalls that already bit us

The full bug history is in `NOTAS.local.md` (local). The permanent ones:

- The reporter is per run: at a new entry point, create an `ErrorReporter` and pass the
  **same** instance to scanner, parser and interpreter (otherwise flags diverge).
- Numeric checks: `isinstance(True, int)` is `True`; use `is_number`/`is_int`.
- `for-in` creates a new `Environment` per iteration with a `val` loop variable; do not reuse
  one environment (closures would see the last value).
- `return` at the top level is a **compile error** from the resolver (exit 65). Do not catch
  `ReturnSignal` in `interpret`; it only unwinds to the function's `call`.
- A new value type needs all of: truthiness branch in the backend, tag/layout, runtime ABI and
  `stringify`/equality/iteration. Missing one is an I4 bug that `--check` will not catch.
- Native namespace dispatch must respect local shadowing (`val fs = ...`, `val Int = ...`).
- Panic sites in C and `LoxRuntimeError` in the tree-walk must point at the **same**
  line/token (the call paren, not the callee; never a synthetic line 0).
- Host read errors are not EOF: only `0` bytes is EOF; `EISDIR` and friends are stable errors
  equal in both engines.
- Generated files (`editors/grammar`, `runtime/kernel_gen.h`, `loxia/_spec/index.json`,
  `docs/spec/garantias.md`) are regenerated, never hand-edited.

---

## 9. What **not** to do

- Do not add silent lowering: what the backend cannot represent is an **explicit** error
  (exit 65, `not supported by the backend yet`), never "roughly right" generated code.
- Do not re-infer types in the backend: the checker publishes `type_of`/instantiations; two
  sources of truth produce silent miscompiles (I4).
- Do not replace the tree-walk with bytecode "to match clox": the interpreter is the executable
  specification and the differential oracle.
- Do not copy Lox2 wholesale (C VM, GC, async, JIT). Take the **feature list**
  ([ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md)), not the architecture.
- Do not change semantics silently: open decisions become `decision` issues; closed ones
  become an ADR + `docs/decisoes.md`.
- Do not break I3: address, PID, timestamp, absolute path and hash order must not appear in
  output. `tests/test_determinism.py` is the gate — a failure there is a bug, not a flake.
- Do not break I4: if the backend needs a type rule, it belongs in the **checker**; the backend
  only refuses with `not supported by the backend yet`.
- Do not raise the memory budget silently: 512 MiB hard cap, I1 up to 64 MiB live, stack
  10,000 calls / 64 MiB; changing any requires ADR + `docs/spec/garantias.md` + test.
- Do not accept a feature that does not pass the ADR-0014 gate. Refusing is part of the work.
- Do not promise what is not tested: extending the language means extending the corpus
  (`LEVELS`/`PENDING`) in the same commit; README and `garantias.md` reflect real status.
- Do not add heavy dependencies (Lark, ANTLR, rich, …) without discussing.
- Do not implement a future stage "on the way": Part II is complete, and new work enters
  through the roadmap and the gates (ADR-0014/0066), never as a side effect.
- Do not commit a test case with a "fixed" expectation, nor a baseline updated to hide a
  regression.

---

## 10. Skills and automation

Loadable procedures (`.dsh/skills/`), for specific tasks:

| Skill | When to use |
| --- | --- |
| `lox-feature` | add/change syntax, operator, AST node or semantics |
| `lox-syntax` | propose/accept/reject syntax: four questions, budget, non-goals |
| `lox-testing` | write/fix tests, add a regression, understand golden cases and the differential corpus (I1) |
| `lox-stdlib` | done criteria for a `std/` module and host/kernel capability rules |
| `lox-bench` | measure performance, read/update the baseline, add a case |
| `lox-debug` | triage a failure, isolate a minimal case, find the guilty layer |
| `lox-docs` | keep `docs/` in step with the code: freshness (git), triage, `docs/log.md` |
| `lox-commits` | commit/PR format, DCO, splitting work |
| `lox-git-flow` | branch model (`main` release, `dev` integration, feature→dev), PR, release, hotfix |
| `lox-converge` | review a delivery before the PR: claim × implementation × test × doc, blast radius; an unresolved caveat needs an issue |
| `lox-audit` | structural audit at a milestone: one lens per round (ABI, runtime, architecture, dead code/repetition, gates) |

Automation:

- `Makefile`: `run`, `test`, `case`, `lint`, `type`, `fmt`, `check`, `docs-sync`,
  `docs-index`, `codes`, `primitives`, `grammar`, `docs-fresh`, `hooks`, `bench`, `baseline`.
- `.github/workflows/ci.yml`: ruff + mypy + pytest on push/PR.
- `pyproject.toml`: single source of config (pytest, ruff, mypy, dev deps).
- `.pre-commit-config.yaml`: local hooks running ruff and mypy on commit and the pytest suite
  on pre-push; `make hooks` installs the three hooks.

---

## 11. Where to decide what

| Question | Where |
| --- | --- |
| version history | [`CHANGELOG.md`](CHANGELOG.md) |
| next feature | [`docs/roadmap.md`](docs/roadmap.md) (Now) |
| final syntax | [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md) + roadmap |
| type inference | [`TIPOS.md`](TIPOS.md) |
| LLVM | [`docs/roadmap.md`](docs/roadmap.md) (Later) |
| what to copy from Lox2 | [ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md) |
| code architecture | [`docs/tech/arquitetura.md`](docs/tech/arquitetura.md) |
| what the language does today | [`docs/spec/`](docs/spec/) |
| what the language **promises** (I1–I4) | [`docs/spec/garantias.md`](docs/spec/garantias.md) |
| accept/reject a new feature | [ADR-0014](docs/adr/0014-identidade-e-invariantes.md) |
| add/reject **syntax** | [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md) + `lox-syntax` |
| why we decided X | [`docs/adr/`](docs/adr/) |
| decisions taken | [`docs/decisoes.md`](docs/decisoes.md) |
| open design ideas | Discussions › Ideas |
| doc freshness and coverage | [`docs/log.md`](docs/log.md) + `lox-docs` |
| how to do X | skills (§10) |

First 15 minutes for a new agent:

1. `make check` (must be green) and read **Now** in [`docs/roadmap.md`](docs/roadmap.md);
2. read [`docs/spec/garantias.md`](docs/spec/garantias.md) and §2 above: nothing enters
   without the ADR-0014 gate;
3. read the task skill (`lox-feature` for syntax, `lox-testing` for tests);
4. implement with a failing test first;
5. close with `make check` (+ `make bench` if a hot path was touched).

---

## 12. Keeping this file honest

- Change this file in the same PR that changes a command, layer or rule; reviewers check it.
- Keep it lean: invariants and gates stay here; encyclopedic detail lives in `docs/spec/`,
  `docs/tech/` and the skills, and is linked.
- The scoped files under `loxia_core/`, `runtime/`, `std/` and `tests/` carry local detail;
  this file must stay sufficient on its own for a change that crosses layers.
- `tests/test_agents_docs.py` fails when the skill table, the version example or a link drifts.
- Personal notes, bug history and opinions go to `NOTAS.local.md` — never here.
