---
sources:
  - pyproject.toml
  - Makefile
  - .gitignore
  - tests/test_test_runner.py
---

# Python coverage

This page is about coverage of the **implementation** (`loxia/`, `loxia_core/`), not of
Lox programs and not of language features. The feature matrix lives in
[`test-coverage.md`](test-coverage.md); Lox line coverage is not implemented.

## Running

```bash
make coverage
```

The target runs the non-backend suite under `coverage run`, combines the per-process data
files and prints a branch report. It is **measurement only**: there is no `fail-under`
yet, and the target is not part of `make check`.

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

## Why no gate yet

A gate before the baseline is understood would either fail constantly or force tests for
code that is intentionally defensive (platform-specific host paths, error branches of the
native kernel). The next step is a **ratchet** on selected modules (`checker`, `backend`,
`test_runner`) after the coverage report has been triaged, not a global percentage.
