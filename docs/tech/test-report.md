---
sources:
  - loxia/test_runner.py
  - loxia/test_selection.py
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
`--jobs N` (there is a regression test). The default is `min(4, CPUs)`; `--jobs 1` is the
escape hatch for tests that share process-wide resources. Durations are intentionally out
of the default payload; if they are ever added, it will be behind an explicit flag and
outside the deterministic contract.

## Selection (`--changed` and `--shard`)

`--changed[=REF]` runs only tests affected by changes since `REF` (default `HEAD`), using
`git diff` plus untracked files. The runner follows imports from each test's own directory
(the same root `loxia run` uses): if a changed `.lx` is in the transitive closure, the test
runs. A change to a non-Lox file, a deleted/missing `.lx`, or a file outside the project is
conservative and runs all tests; no changes selects zero tests (exit 5 with
`--require-tests`). Without a git repository the command exits 2.

`--shard=INDEX/TOTAL` is 1-based, validates `1 <= INDEX <= TOTAL`, and slices the already
selected, sorted file list round-robin. It applies after `--changed` and after the
`--filter`/`--only` selection; shards contain files, not individual `it` cases. Use it in
CI with a matrix `INDEX=1..TOTAL`.

## Native cache

`--native` builds one binary per file; the runner caches those executables by content
(project `.lx` files, implementation, compiler and flags). A cache hit skips compilation;
`--no-cache` forces a fresh build. The cache is invisible in the report: it never changes
order, counts, messages or exit codes, and a cache failure falls back to a normal build.

## Streaming (`--json-lines`)

`--json-lines` emits one compact JSON object per test, in the same order, followed by a
final `summary` object:

```json
{"schema_version":1,"type":"test","file":"tests/foo_test.lx","name":"soma","status":"pass","kind":"pass","message":"","location":null,"output":null}
{"schema_version":1,"type":"summary","success":false,"exit_code":1,"files":1,"tests":2,"pass":1,"fail":1,"skip":0}
```

It is mutually exclusive with `--json` (exit 2). Use it when the consumer wants to start
processing before the suite ends; the final summary is still authoritative. JSONL uses
ASCII escapes for non-ASCII text, so Unicode line separators such as U+0085 never split a
record.

## Type pre-check

Before running each file, the runner type-checks it in **gradual** mode (ADR-0142): a missing
annotation is a warning and `Any` is consistent with every type, so an unannotated suite is
not rejected. A real type error fails the file as a single `crash` result named `<path>`
whose message is the short diagnostic; the file is not executed (and, with `--native`, not
built). The pre-check always runs. It uses the same dependency flags as the
run (`--frozen`, `--offline`, `--cache-dir`).

## JUnit XML (`--junit PATH`)

`--junit` writes a JUnit report (in addition to the human/JSON output):

```xml
<testsuites name="loxia-test" tests="2" failures="1" skipped="0" time="0">
  <testsuite name="tests/foo_test.lx" tests="2" failures="1" skipped="0" time="0">
    <testcase classname="tests/foo_test.lx" name="soma" time="0"/>
    <testcase classname="tests/foo_test.lx" name="falha" time="0">
      <failure message="expected 3, got 2" type="assertion">expected 3, got 2</failure>
    </testcase>
  </testsuite>
</testsuites>
```

`time="0"` is fixed (I3); the runner does not report wall-clock time. `--capture` appends
the failing test's stdout to the `<failure>` body. `kind` becomes the `type` attribute.
The XML declaration and escaping are generated by the runner; a write error exits 2.

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
