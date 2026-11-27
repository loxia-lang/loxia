---
title: std.test
sources:
  - std/test.lx
  - loxia/docgen.py
---

# std.test

Mini test harness with TAP output, hooks, matchers and a recorder.

## API

## Classes

### `class TestFailure(Exception)`

Test failure (distinct from `RuntimeError`, which is an infrastructure bug).

#### `fn init(message: String)`

Creates the failure with the message shown in the report.

### `class Skip(Exception)`

Test skipped on purpose; the runner counts it as `skip`, not as a failure.

#### `fn init(reason: String)`

Creates the skip with the given reason.

### `class Suite`

Test suite: `describe`, `it`, `report` and `done`.

#### `var total: Int`

Number of tests executed (filtered-out tests do not count).

#### `var passed: Int`

Tests that passed.

#### `var failed: Int`

Tests that failed.

#### `var skipped: Int`

Tests skipped with `skip`.

#### `var prefixes: List[String]`

Group names opened by `describe`, innermost last.

#### `var filter: String`

Substring filter read from `--filter=` in the script arguments.

#### `var only: String`

Exact test name read from `--only=` in the script arguments.

#### `var beforeHooks: List[fn() -> Nil]`

Hooks run before each `it`, in registration order.

#### `var afterHooks: List[fn() -> Nil]`

Hooks run after each `it`, in reverse registration order.

#### `var listMode: Bool`

`--list`: print `# test <name>` only, without executing (per-test isolation).

#### `var protocol: Bool`

`--protocol=json`: emit framed events instead of TAP (machine protocol).

#### `var token: String`

Nonce prefix for control lines; prevents user `print` from spoofing events.

#### `fn init()`

Creates an empty suite and reads `--filter=`/`--only=` from `args()`.

Also detects `--list`, `--protocol=json` and `--token=`.

#### `fn describe(name: String, body: fn() -> Nil) -> Nil`

Opens a group; its name prefixes every `it` and its hooks apply only here.

Hooks registered inside the body are removed when the body returns.

#### `fn beforeEach(body: fn() -> Nil) -> Nil`

Registers a hook run before each `it` in this `describe`.

#### `fn afterEach(body: fn() -> Nil) -> Nil`

Registers a hook run after each `it` in this `describe`.

#### `fn it(name: String, body: fn() -> Nil) -> Nil`

Runs a test immediately and prints `ok`/`not ok` in TAP.

Filtered tests do not run or count. A skipped test still counts in `total` but not
as passed or failed. A failure in `beforeEach`/`afterEach` is reported as a test
failure.

#### `fn skip(reason: String) -> Nil`

Skips the current test with `reason`.

Raises `Skip`, which `it` turns into a `# SKIP` line rather than a failure.

#### `fn report() -> Int`

Prints the TAP plan and summary, returning 0 (all passed) or 1 (any failure).

In protocol mode it emits the `end` event and stays silent instead.

#### `fn done() -> Nil`

Calls `report()` and exits the process with its code.

In `--list` mode it exits 0 immediately.

### `class Expectation`

Equality assertion for any value (scalar, string, list, map, tuple or dynamic `Any`).

The observed value is `Any` so `expect(x)` also accepts values that are typed
dynamically; the failure message renders both sides with `repr` (deterministic).

#### `val value: Any`

Observed value.

#### `fn init(value: Any)`

Wraps the observed value.

#### `fn toBe(other: Any) -> Nil`

Fails when `value != other`.

#### `fn notToBe(other: Any) -> Nil`

Fails when `value == other`.

### `class ListExpectation[T]`

Assertion over the elements of a list.

#### `val items: List[T]`

Observed list.

#### `fn init(items: List[T])`

Wraps the observed list.

#### `fn toContain(item: T) -> Nil`

Fails when `item` is not in the list (structural equality).

### `class StringExpectation`

Assertion over the contents of a string.

#### `val text: String`

Observed text.

#### `fn init(text: String)`

Wraps the observed text.

#### `fn contains(needle: String) -> Nil`

Fails when `text` does not contain `needle`.

### `class Recorder`

Records calls of a spy/fake: `record`, `count`, `order` and `clear`.

#### `val calls: List[String]`

Calls in registration order.

#### `fn init()`

Creates an empty recorder.

#### `fn record(name: String) -> Nil`

Records one call by name.

#### `fn count(name: String) -> Int`

Returns how many times `name` was recorded.

#### `fn order() -> List[String]`

Returns a copy of the calls in registration order.

#### `fn clear() -> Nil`

Empties the record.

## Functions

### `fn fail(message: String) -> Nil`

Fails the current test with `message`.

### `fn expect(value: Any) -> Expectation`

Wraps any value, including a dynamically typed `Any`, for `toBe`/`notToBe`.

### `fn expectGt[T](actual: T, expected: T) -> Nil`

Fails when `actual <= expected` (natural order of `T: Ord`).

### `fn expectGe[T](actual: T, expected: T) -> Nil`

Fails when `actual < expected`.

### `fn expectLt[T](actual: T, expected: T) -> Nil`

Fails when `actual >= expected`.

### `fn expectLe[T](actual: T, expected: T) -> Nil`

Fails when `actual > expected`.

### `fn expectNil[T](value: T | Nil) -> Nil`

Fails when `value` is not `nil`.

Pass a typed optional (`val x: Int? = nil`): `expectNil(nil)` is a nested optional and
the backend rejects it.

### `fn expectNotNil[T](value: T | Nil) -> T`

Fails when `value` is `nil`; returns the narrowed value.

### `fn expectList[T](items: List[T]) -> ListExpectation[T]`

Wraps a list for `toContain`.

### `fn expectString(text: String) -> StringExpectation`

Wraps a string for `contains`.

### `fn expectRaise(body: fn() -> Nil) -> String`

Runs `body` and returns the exception message; fails when nothing is raised.

Catches any `Exception`, including `Skip` and `TestFailure`.
