# tests — suite and corpus

Scoped context for `tests/`. The root [`AGENTS.md`](../AGENTS.md) still applies; the
operational guide is the `lox-testing` skill.

## Golden cases (`tests/cases/*.lx`)

The `.lx` file carries its own expectation:

```lox
print(1 + 2)                       # expect: 3
print(inexistente);
# expect runtime error: Undefined variable 'inexistente'.
```

| Marker | Effect |
| --- | --- |
| `# expect: X` | one expected stdout line (order matters) |
| `# expect runtime error: MSG` | stderr contains MSG; exit **70** |
| `# expect error: MSG` | syntax/resolution error; exit **65** |
| `# expect exit: N` | explicit exit code |
| `# requires: rust` | skip when `cargo` is missing; own line in the top comment block, lowercase; longer timeout |

Without an error marker the case requires identical stdout, empty stderr and exit 0.
A case that needs an external toolchain declares `# requires: rust` in the leading comment
block (own line, lowercase): the golden runner and the differential skip it when `cargo` is
absent instead of failing the suite, and give it a longer timeout for the first build.
Exit codes: 65 syntax, 70 runtime, 66 file not found.

## Rules

- **Every fixed bug gets a regression case in the same commit.** If the case already existed,
  say in the commit message that it failed before the fix.
- Never adjust an expectation to make a test pass: if behavior is wrong, the code is wrong.
- Prefer a small public-API test (scanner/parser/interpreter through the CLI) over a test of
  a private helper.
- Use the existing helpers (`run`, `parse`, `ast`, `scan`) instead of duplicating setup; there
  is no global error state, so inspect `lox.reporter`/`scanner.reporter`/`parser.reporter`.
- `tests/runner.py` runs the CLI in-process (same stdout/stderr/exit contract) and compares the
  three channels; `LOX_GOLDEN_SUBPROCESS=1` forces one process per case. Use `subprocess` only
  when the test needs a real process (hash seed, signals/timeout, REPL stdin, sandbox,
  backend). `pytest -k <substring>` is the fast path; `make test-fast` uses xdist.

## Differential corpus (I1)

Every case lives in `LEVELS`, `PENDING` or `NEGATIVE` in `tests/corpus_manifest.py`:

- Promoting a case = move it from `PENDING` to `LEVELS` in the same commit, with the three
  channels green.
- A level key never shrinks; promotion is monotonic.
- `PENDING` must stay **≤ 5%** of the corpus, always with a level and a reason; `l?` is
  forbidden. A new case without backend support waits in an issue/branch instead of inflating
  `PENDING`.
- The generated status in `docs/spec/garantias.md` comes from the manifest; never copy
  numbers by hand.

## Backend tests

```bash
make test-backend               # backend only; xdist, ~40 s (needs libgc)
make test-backend TEST_JOBS=0   # backend serial, to debug one case
uv run pytest -m backend -q     # builds each manifest case; needs libgc
make test                       # everything, includes backend (serial)
```

The runtime is cached by a hash of sources/headers/compiler/flags; a backend failure is a
contract violation (I1/I4), not a flake. Do not mark it `xfail` to get green.

## Official suite

`tests/official/` is the book suite (chapters 10–13), adapted in `tests/test_official_suite.py`
(`fun`→`fn`, `//`→`#`, declared `this.x` fields, `class B < A`→`class B(A)`). It runs through
the CLI; a new documented `xfail` needs a reason in the test.
