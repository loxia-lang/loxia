---
title: Builtins e kernel
sources:
  - loxia/builtins_docs.py
  - loxia_core/execution/primitives.py
  - loxia_core/execution/prelude.py
---

# Builtins and kernel

Global names and native namespaces documented from `loxia/builtins_docs.py`.
They are available without an import; `std.*` modules are documented separately.

## Global functions and namespaces

### `args() -> List[String]`

Returns the program arguments.

### `chars(s: String) -> List[String]`

Splits a string into code points.

### `charCodeAt(s: String, index: Int) -> Int`

Returns the Unicode code point at a code-point index.

### `fromCodePoint(codePoint: Int) -> String`

Builds a one-code-point string from a Unicode scalar.

### `join(parts: List[String], separator: String) -> String`

Joins strings with a separator.

### `len(value: Any) -> Int`

Returns the length of a string, list, map or tuple.

### `range(start: Int, end: Int, step: Int = 1) -> Range`

Creates a lazy integer range.

### `print(value: Any) -> Nil`

Writes the display form followed by a newline.

### `repr(value: Any) -> String`

Returns the debug representation.

### `str(value: Any) -> String`

Returns the display string.

### `substr(text: String, start: Int, end: Int) -> String`

Returns the half-open code-point slice.

### `Int`

Namespace for integer conversions.

### `Float`

Namespace for float conversions.

### `math`

Deterministic math namespace.

### `io`

Standard input/output namespace.

### `fs`

Filesystem namespace.

### `os`

Operating-system namespace.

### `time`

Time namespace (ambient).

### `Result[T, E]`

Built-in sum type with `Ok(T)` and `Err(E)`.

### `Exception`

Base class for catchable runtime errors.

### `RuntimeError`

Catchable runtime error type.

## Native module members

### `Int.parse(text: String) -> Int?`

Parses a decimal integer, returning `nil` when invalid.

### `Float.parse(text: String) -> Float?`

Parses a decimal float, returning `nil` when invalid.

### `math.abs(value: Int | Float) -> Int | Float`

Returns the absolute value.

### `math.min(a: Int | Float, b: Int | Float) -> Int | Float`

Returns the smaller value.

### `math.max(a: Int | Float, b: Int | Float) -> Int | Float`

Returns the larger value.

### `math.clamp(value: Int | Float, low: Int | Float, high: Int | Float) -> Int | Float`

Clamps a value into `[low, high]`.

### `math.floor(value: Float) -> Int`

Rounds down to an integer.

### `math.ceil(value: Float) -> Int`

Rounds up to an integer.

### `math.round(value: Float) -> Int`

Rounds to the nearest integer.

### `math.trunc(value: Float) -> Int`

Truncates toward zero.

### `math.sqrt(value: Float) -> Float`

Returns the square root.

### `io.readFile(path: String) -> String?`

Reads a UTF-8 file, returning `nil` when unreadable.

### `io.readAll() -> String`

Reads all remaining standard input.

### `io.write(text: String) -> Nil`

Writes to standard output.

### `io.writeErr(text: String) -> Nil`

Writes to standard error.

### `io.writeFile(path: String, text: String) -> Bool`

Writes a UTF-8 file.

### `io.readLine() -> String?`

Reads one line from standard input.

### `io.readUtf8(n: Int) -> String?`

Reads exactly `n` bytes of standard input as strict UTF-8; `nil` only at immediate end of input.

### `io.flush() -> Nil`

Flushes standard output and standard error.

### `fs.exists(path: String) -> Bool`

Returns whether the path exists.

### `fs.listDir(path: String) -> List[String]?`

Lists directory entries, or `nil` when unreadable.

### `os.exit(code: Int) -> Nil`

Terminates the process with an exit code.

### `os.getenv(name: String) -> String?`

Reads an environment variable.

### `time.now() -> Int`

Returns the current Unix time in milliseconds.

### `time.sleep(milliseconds: Int) -> Nil`

Sleeps for the given duration.
