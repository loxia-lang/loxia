---
sources:
  - loxia/test_runner.py
  - loxia/cli_args.py
  - std/test.lx
  - schema/test-report-v1.json
  - tests/test_test_runner.py
---

# Test report (`loxia test --json`)

`loxia test` runs `*_test.lx` files and aggregates the result. For humans it renders
**TAP**; with `--json` it emits the stable envelope below. The contract is additive:
new fields may appear, existing fields keep their meaning, and `schema_version` only
changes on a **breaking** change. The machine schema lives in
[`schema/test-report-v1.json`](../../schema/test-report-v1.json).

## Envelope

```json
{
  "schema_version": 1,
  "command": "test",
  "success": false,
  "exit_code": 1,
  "tests": [
    {
      "file": "tests/foo_test.lx",
      "name": "soma / inteiros",
      "status": "fail",
      "kind": "assertion",
      "message": "expected 3, got 2",
      "location": { "file": "tests/foo_test.lx", "line": 7, "column": 5 },
      "output": null
    }
  ],
  "summary": { "files": 1, "tests": 2, "pass": 1, "fail": 1, "skip": 0 }
}
```

| Field | Meaning |
| --- | --- |
| `schema_version` | `1`. Changes only on a breaking change. |
| `command` | Always `test`. |
| `success` | `exit_code == 0`. |
| `exit_code` | `0` all passed, `1` any failure, `2` runner error (path/discovery), `5` no test selected with `--require-tests`. |
| `tests[]` | Flat, in execution order (files sorted, tests in source order). Group by `file` if needed. |
| `tests[].file` | Path relative to the invocation CWD. Never absolute (I3). |
| `tests[].name` | Full name, including `describe` prefixes joined by ` / `. |
| `tests[].status` | `pass`, `fail` or `skip`. |
| `tests[].kind` | `pass`, `assertion`, `exception`, `hook`, `crash`, `timeout` or `skip`. |
| `tests[].message` | Failure/skip message. May contain newlines. |
| `tests[].location` | `{file, line, column}` of the assertion when known, or `null` when the exception has no position (ADR-0120). |
| `tests[].output` | Captured stdout of a **failing** test when `--capture` is passed; otherwise `null`. |
| `summary` | Counts; always consistent with `tests[]`. |

## Determinism

The report never carries timestamp, duration, PID, address or absolute path. `--jobs`
only changes concurrency: the order and the content are identical for `--jobs 1` and
`--jobs N` (there is a regression test). Durations are intentionally out of the default
payload; if they are ever added, it will be behind an explicit flag and outside the
deterministic contract.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every selected test passed (or a skip). |
| `1` | At least one failure, crash or timeout. |
| `2` | Runner error: invalid path or no `*_test.lx` discovered. |
| `5` | `--require-tests` was passed and nothing was selected. Without the flag the runner warns and exits `0`. |

## Protocol (internal)

`std.test` speaks two protocols:

- **TAP** (default): what `loxia run tests/foo_test.lx` prints.
- **Framed events** (`--protocol=json --token=NONCE`, used by `loxia test`):
  `start`, `result`, `discover` and `end`, each a JSON object prefixed by the nonce.
  The nonce separates control lines from the test's own stdout, so a test that prints
  `ok 1 - falso` cannot forge a result. Control lines are written with `io.write`
  (immediate flush), so the runner sees results while the file is still running.

The runner renders TAP/JSON from the events; the language-level TAP output is unchanged
when no protocol flag is present.

## Failure location

`std.test` includes `e.site` (`arquivo:linha:coluna`, ADR-0120) in the protocol event and in
the human TAP (`# at ...`); the runner maps it to `tests[].location`. The field was already
nullable in v1, so populating it was additive. `site` is the caller frame of the throw —
for `t.expect(...).toBe(...)`, the `expect` line.
