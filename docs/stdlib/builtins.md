---
title: Builtins e kernel
sources:
  - loxia/builtins_docs.py
  - loxia_core/execution/primitives.py
  - loxia_core/execution/prelude.py
---

# Builtins and kernel

Global names available without an import, generated from `loxia/builtins_docs.py`.
Namespaces are read-only. `std.*` modules are documented separately.

## Global functions

### `args() -> List[String]`

Returns the program arguments.

The list excludes the program name (`argv[0]`) and contains the remaining arguments as strings, in command-line order. Ambient: it depends on how the process was launched.

### `chars(s: String) -> List[String]`

Splits a string into its Unicode code points.

Each element is a one-code-point `String`; `chars("")` is `[]`. Indices count code points, not UTF-8 bytes or UTF-16 units. A non-string argument raises `RuntimeError`.

### `charCodeAt(s: String, index: Int) -> Int`

Returns the Unicode code point at a code-point index.

`index` must be in `0..len(s)-1`; anything else raises `RuntimeError`. Astral code points (above U+FFFF) are returned as a single scalar, not as a surrogate pair.

### `fromCodePoint(codePoint: Int) -> String`

Builds a one-code-point string from a Unicode scalar.

Accepts `0..U+10FFFF` except the surrogate range `U+D800..U+DFFF`; invalid values raise `RuntimeError`.

### `join(parts: List[String], separator: String) -> String`

Joins a list of strings with a separator between elements.

Every element must be a `String`, otherwise `RuntimeError` is raised. `join([], ",")` is `""`; no separator is added at either end.

### `len(value: Any) -> Int`

Returns the length of a string, list, map or tuple.

Strings count code points (not bytes); maps count entries; tuples count positions. Any other value raises `RuntimeError`.

### `range(start: Int, end: Int, step: Int) -> Range`

Creates a lazy integer range from `start` to `end` with an explicit step.

`start`, `end` and `step` must be `Int`; `step` can be negative to iterate downwards but cannot be zero. Ranges are immutable and reusable. The two-argument form is the `start..end` operator, which is sugar for a step of 1; `range(a, b)` with two arguments is not accepted.

### `print(value: Any) -> Nil`

Writes the display form of `value` followed by a newline.

Strings are printed raw (without quotes); list, map, tuple and enum elements use their display forms, with string elements quoted. Returns `nil`.

### `repr(value: Any) -> String`

Returns the debug representation of `value`.

Strings are quoted and escaped (`\\`, `"`, newline, CR, tab and NUL); other values match `str`. Used by tests and diagnostics.

### `str(value: Any) -> String`

Returns the display form of `value`.

Strings are returned unchanged, `nil` is `"nil"`, booleans are `true`/`false`, `Int` is decimal and `Float` uses the canonical short form (`1.0`, not `1`).

### `substr(text: String, start: Int, end: Int) -> String`

Returns the half-open code-point slice `[start, end)`.

Requires `start >= 0`, `end >= start` and `end <= len(text)`; any other bound raises `RuntimeError`. `substr(s, 0, len(s))` returns a copy.

## Namespaces

### `Int`

Namespace for integer conversions.

Read-only; the only member is `Int.parse`.

#### `Int.parse(text: String) -> Int?`

Parses a decimal integer.

Accepts an optional `+`/`-` followed by ASCII digits only; whitespace, other bases and values outside the i64 range return `nil`. A non-string argument raises `RuntimeError`.

### `Float`

Namespace for float conversions.

Read-only; the only member is `Float.parse`.

#### `Float.parse(text: String) -> Float?`

Parses a decimal float.

Accepts digits with an optional fraction and exponent (`1`, `-2.5`, `1e3`). Whitespace, `NaN`, infinities and overflow return `nil`. A non-string argument raises `RuntimeError`.

### `math`

Deterministic math namespace.

No locale or host state is consulted. Functions returning `Int` (`floor`, `ceil`, `round`, `trunc`) require a finite value in i64 range and raise `RuntimeError` otherwise.

#### `math.abs(value: Int | Float) -> Int | Float`

Returns the absolute value, preserving the argument type.

An `Int` stays `Int` (under `--debug`, `abs(INT_MIN)` raises on overflow); a `Float` stays `Float`.

#### `math.min(a: Int | Float, b: Int | Float) -> Int | Float`

Returns the smaller of two numbers.

Promotes to `Float` when either argument is `Float`; any `NaN` argument makes the result `NaN`.

#### `math.max(a: Int | Float, b: Int | Float) -> Int | Float`

Returns the larger of two numbers.

Promotes to `Float` when either argument is `Float`; any `NaN` argument makes the result `NaN`.

#### `math.clamp(value: Int | Float, low: Int | Float, high: Int | Float) -> Int | Float`

Clamps `value` into the inclusive range `[low, high]`.

Requires `low <= high`; otherwise `RuntimeError` is raised. A `NaN` in any argument makes the result `NaN`; mixed `Int`/`Float` promotes to `Float`.

#### `math.floor(value: Float) -> Int`

Rounds down to an integer.

Requires a `Float`; the value must be finite and fit in i64, otherwise `RuntimeError` is raised.

#### `math.ceil(value: Float) -> Int`

Rounds up to an integer.

Requires a `Float`; the value must be finite and fit in i64, otherwise `RuntimeError` is raised.

#### `math.round(value: Float) -> Int`

Rounds to the nearest integer, with ties away from zero.

Requires a `Float`; the value must be finite and fit in i64, otherwise `RuntimeError` is raised.

#### `math.trunc(value: Float) -> Int`

Truncates toward zero.

Requires a `Float`; the value must be finite and fit in i64, otherwise `RuntimeError` is raised.

#### `math.sqrt(value: Float) -> Float`

Returns the square root as a `Float`.

Requires a `Float`. A negative argument returns `NaN` instead of raising.

### `io`

Standard input/output namespace.

`write`, `writeErr` and `flush` are deterministic; the read functions are ambient and may block.

#### `io.readFile(path: String) -> String?`

Reads a UTF-8 file into a string, or `nil` when it cannot be read.

Ambient. Invalid UTF-8 counts as unreadable (`nil`); the content is returned exactly as stored, including any trailing newline.

#### `io.readAll() -> String`

Reads all remaining standard input as text.

Ambient. At immediate end of input it returns `""`; invalid UTF-8 raises `RuntimeError`.

#### `io.write(text: String) -> Nil`

Writes `text` to standard output without a trailing newline.

Flushes immediately, so output order is observable before the next read or process exit.

#### `io.writeErr(text: String) -> Nil`

Writes `text` to standard error without a trailing newline.

Flushes immediately; stderr is not part of the default golden comparison.

#### `io.writeFile(path: String, text: String) -> Bool`

Writes `text` as UTF-8, creating or truncating the file.

Ambient. Returns `true` on success and `false` on a filesystem error; the parent directory must exist.

#### `io.readLine() -> String?`

Reads one line from standard input.

Ambient. A trailing LF or CRLF is removed; `nil` means immediate end of input. Invalid UTF-8 raises `RuntimeError`.

#### `io.readUtf8(n: Int) -> String?`

Reads exactly `n` bytes and decodes them as strict UTF-8.

Ambient. `nil` only at immediate end of input; a short read or invalid UTF-8 raises `RuntimeError`. `n` must be non-negative; `n == 0` returns `""`.

#### `io.flush() -> Nil`

Flushes standard output and standard error.

### `fs`

Filesystem namespace (ambient).

Operations read the host filesystem and are outside the I1 corpus; tests use temporary directories and never print absolute paths.

#### `fs.exists(path: String) -> Bool`

Returns whether `path` exists.

Ambient. True for files, directories and other entries the host can stat.

#### `fs.listDir(path: String) -> List[String]?`

Returns the entry names of a directory, sorted, or `nil` when unreadable.

Ambient. The sort makes the result deterministic for a given directory; `.` and `..` are not included.

### `process`

Process and stream handles for the kernel (POSIX, ambient).

Handles are opaque, 1-based `Int` ids; `0` is never a valid handle and is returned by `spawn` on failure.

#### `process.spawn(argv: List[String]) -> Int`

Starts a process without a shell.

Ambient. `argv[0]` is the program and the remaining items are its arguments; stdin/stdout/stderr are pipes. Returns a process handle, or `0` when the process cannot start.

#### `process.stdin(handle: Int) -> Int`

Returns the stream handle for a process's standard input.

Ambient. The process handle must be valid.

#### `process.stdout(handle: Int) -> Int`

Returns the stream handle for a process's standard output.

Ambient. The process handle must be valid.

#### `process.stderr(handle: Int) -> Int`

Returns the stream handle for a process's standard error.

Ambient. The process handle must be valid.

#### `process.wait(handle: Int) -> Int`

Waits for a process and returns its exit code.

Ambient. A negative code means the child was terminated by a signal; the status is cached after the first wait.

#### `process.kill(handle: Int) -> Bool`

Sends `SIGKILL` to a process.

Ambient. Returns `false` when the process already exited; records the exit status when it reaps the child.

#### `process.close(handle: Int) -> Nil`

Releases a process or stream handle.

Ambient. Does not kill a running process; after closing, any use of the handle raises `RuntimeError`.

#### `process.read(handle: Int, n: Int) -> String?`

Reads up to `n` bytes from a stream as UTF-8.

Ambient. `nil` at end of stream; an incomplete UTF-8 sequence is buffered for the next call, so a character is never split. `n` must be non-negative.

#### `process.write(handle: Int, text: String) -> Bool`

Writes all of `text` to a stream.

Ambient. Returns `false` when the other side closed the pipe.

#### `process.poll(handles: List[Int], timeoutMs: Int) -> List[Int]`

Returns the handles that are ready.

Ambient. A negative timeout waits forever and `0` is non-blocking; streams are ready when readable or at EOF, processes when they have exited. The result is deduplicated.

### `os`

Operating-system namespace.

#### `os.exit(code: Int) -> Nil`

Flushes both streams and terminates the process with `code`.

`code` must be in `0..255`; anything else raises `RuntimeError`.

#### `os.getenv(name: String) -> String?`

Returns the value of an environment variable, or `nil` when unset.

Ambient: it reads the host environment.

### `time`

Time namespace (ambient).

Functions read the host clock; they are outside the I1/I3 corpus.

#### `time.now() -> Int`

Returns the current Unix time in milliseconds.

Ambient and non-deterministic; tests must not assert an exact value.

#### `time.sleep(milliseconds: Int) -> Nil`

Suspends the current process for at least `milliseconds`.

Ambient. A negative duration raises `RuntimeError`.

## Built-in types

### `Result[T, E]`

Built-in generic sum type with `Result.Ok(value)` and `Result.Err(error)`.

Use an exhaustive `match` to inspect it, or the combinators in `std.results`.

### `Exception`

Base class for catchable runtime errors.

`except Exception as e` catches user exceptions and runtime panics converted to `RuntimeError`.

### `RuntimeError`

Catchable runtime error type, below `Exception`.

Raised by the `raise` statement and by runtime panics; the `message` field holds the diagnostic text.
