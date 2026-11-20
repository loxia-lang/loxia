---
sources:
  - pyproject.toml
  - Makefile
  - .gitignore
  - coverage-baseline.toml
  - tools/coverage_ratchet.py
  - .github/workflows/ci.yml
  - tests/test_coverage_config.py
---

# Python coverage

This page is about coverage of the **implementation** (`loxia/`, `loxia_core/`), not of
Lox programs and not of language features. The feature matrix lives in
[`test-coverage.md`](test-coverage.md); Lox line coverage is not implemented.

## Running

```bash
make coverage
```

`make coverage` runs the non-backend suite under `coverage run`, combines the per-process
data files and prints a branch report. It is **measurement only**: the gate is a separate
target, `make coverage-ratchet`.

The two `--timeout` CLI tests are deselected from the coverage run: they assert a
wall-clock watchdog against an infinite loop, and the instrumentation overhead makes the
test harness's 20 s timeout fire instead. They still run in the normal unit job; excluding
them from the measurement is deliberate and does not hide a product regression.

`[tool.coverage.run]` in `pyproject.toml` sets:

- `source = ["loxia", "loxia_core"]` — tests, benchmarks and tools are not measured;
- `branch = true` — a branch that is never taken counts as uncovered;
- `parallel = true` — each process writes `.coverage.<host>.<pid>...`; `coverage combine`
  merges them;
- `patch = ["subprocess"]` — coverage is injected into Python subprocesses, which matters
  because the golden runner, `loxia test`, LSP and MCP all spawn the CLI. Native binaries
  are not Python and are outside this measurement.

`.coverage`, `.coverage.*` and `htmlcov/` are ignored by git.

## First measurement (2026-11-20)

Local run with the non-backend suite:

```text
TOTAL   20190 statements   6403 missed   8596 branches   1048 partial   65%
```

That is the baseline, not a target. The backend suite and the native runtime are excluded,
and a single number hides the important split: the parser, resolver and value types are
well covered; the checker's diagnostic branches and the host/process runtime are the
largest gaps. Use `coverage report -m` for the missing lines and
`coverage html` for the annotated source.

## Ratchet

`coverage-baseline.toml` stores an integer floor per selected module: parser, scanner,
resolver, checker, interpreter, numeric, the value objects (`list`, `map`, `class`,
`exception`, `instance`), the CLI/engine and `test_runner`. `make coverage-ratchet` runs
the measurement, converts the report to `.coverage.json` and fails when a module is below
its floor:

```bash
make coverage-ratchet   # gate (also runs in the CI "Coverage ratchet" job)
make coverage-update    # raises floors to the measured value; never lowers
```

The floors only go up (`tools/coverage_ratchet.py --update` uses `max`). A new module is
not in the baseline yet, so it does not fail; add it after triaging its gaps. There is no
global `fail-under`: a high-level percentage lets one module drop while another rises.
`make check` does not run the ratchet (it would run the suite a third time); CI does.

The selection is intentionally [the hot path and the compiler
surface](../../coverage-baseline.toml), not every file. `checker` is the most sensitive
floor: a diagnostic branch without a test fails the ratchet.
