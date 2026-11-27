# SPDX-License-Identifier: MIT OR Apache-2.0
"""Public documentation for builtins and kernel primitives (ADR-0091).

This module is the single source of truth for `docs/stdlib/builtins.md`. The
runtime behavior lives in `loxia_core/execution/natives/` (tree-walk builtins),
`loxia_core/execution/primitives.py` (kernel table) and `runtime/` (native
backend). Names and signatures are checked against `BUILTIN_NAMES` and
`PRIMITIVES` by `tests/test_stdlib_docs.py`.

Keep descriptions user-facing: contract, edge cases, errors and determinism.
Implementation notes belong in the Python/C sources, not here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinDoc:
    name: str
    signature: str
    doc: str
    kind: str = "function"
    ambient: bool = False


BUILTIN_DOCS: tuple[BuiltinDoc, ...] = (
    # ------------------------------------------------------------------
    # Global functions
    # ------------------------------------------------------------------
    BuiltinDoc(
        "args",
        "args() -> List[String]",
        "Returns the program arguments.\n\n"
        "The list excludes the program name (`argv[0]`) and contains the remaining "
        "arguments as strings, in command-line order. Ambient: it depends on how the "
        "process was launched.",
        ambient=True,
    ),
    BuiltinDoc(
        "chars",
        "chars(s: String) -> List[String]",
        "Splits a string into its Unicode code points.\n\n"
        'Each element is a one-code-point `String`; `chars("")` is `[]`. Indices '
        "count code points, not UTF-8 bytes or UTF-16 units. A non-string argument "
        "raises `RuntimeError`.",
    ),
    BuiltinDoc(
        "charCodeAt",
        "charCodeAt(s: String, index: Int) -> Int",
        "Returns the Unicode code point at a code-point index.\n\n"
        "`index` must be in `0..len(s)-1`; anything else raises `RuntimeError`. "
        "Astral code points (above U+FFFF) are returned as a single scalar, not as a "
        "surrogate pair.",
    ),
    BuiltinDoc(
        "fromCodePoint",
        "fromCodePoint(codePoint: Int) -> String",
        "Builds a one-code-point string from a Unicode scalar.\n\n"
        "Accepts `0..U+10FFFF` except the surrogate range `U+D800..U+DFFF`; invalid "
        "values raise `RuntimeError`.",
    ),
    BuiltinDoc(
        "join",
        "join(parts: List[String], separator: String) -> String",
        "Joins a list of strings with a separator between elements.\n\n"
        "Every element must be a `String`, otherwise `RuntimeError` is raised. "
        '`join([], ",")` is `""`; no separator is added at either end.',
    ),
    BuiltinDoc(
        "len",
        "len(value: Any) -> Int",
        "Returns the length of a string, list, map or tuple.\n\n"
        "Strings count code points (not bytes); maps count entries; tuples count "
        "positions. Any other value raises `RuntimeError`.",
    ),
    BuiltinDoc(
        "range",
        "range(start: Int, end: Int, step: Int) -> Range",
        "Creates a lazy integer range from `start` to `end` with an explicit step.\n\n"
        "`start`, `end` and `step` must be `Int`; `step` can be negative to iterate "
        "downwards but cannot be zero. Ranges are immutable and reusable. The "
        "two-argument form is the `start..end` operator, which is sugar for a step of "
        "1; `range(a, b)` with two arguments is not accepted.",
    ),
    BuiltinDoc(
        "print",
        "print(value: Any) -> Nil",
        "Writes the display form of `value` followed by a newline.\n\n"
        "Strings are printed raw (without quotes); list, map, tuple and enum elements "
        "use their display forms, with string elements quoted. Returns `nil`.",
    ),
    BuiltinDoc(
        "repr",
        "repr(value: Any) -> String",
        "Returns the debug representation of `value`.\n\n"
        'Strings are quoted and escaped (`\\\\`, `"`, newline, CR, tab and NUL); '
        "other values match `str`. Used by tests and diagnostics.",
    ),
    BuiltinDoc(
        "str",
        "str(value: Any) -> String",
        "Returns the display form of `value`.\n\n"
        'Strings are returned unchanged, `nil` is `"nil"`, booleans are `true`/'
        "`false`, `Int` is decimal and `Float` uses the canonical short form (`1.0`, "
        "not `1`).",
    ),
    BuiltinDoc(
        "substr",
        "substr(text: String, start: Int, end: Int) -> String",
        "Returns the half-open code-point slice `[start, end)`.\n\n"
        "Requires `start >= 0`, `end >= start` and `end <= len(text)`; any other "
        "bound raises `RuntimeError`. `substr(s, 0, len(s))` returns a copy.",
    ),
    # ------------------------------------------------------------------
    # Built-in namespaces
    # ------------------------------------------------------------------
    BuiltinDoc(
        "Int",
        "Int",
        "Namespace for integer conversions.\n\nRead-only; the only member is `Int.parse`.",
        kind="module",
    ),
    BuiltinDoc(
        "Int.parse",
        "Int.parse(text: String) -> Int?",
        "Parses a decimal integer.\n\n"
        "Accepts an optional `+`/`-` followed by ASCII digits only; whitespace, "
        "other bases and values outside the i64 range return `nil`. A non-string "
        "argument raises `RuntimeError`.",
    ),
    BuiltinDoc(
        "Float",
        "Float",
        "Namespace for float conversions.\n\nRead-only; the only member is `Float.parse`.",
        kind="module",
    ),
    BuiltinDoc(
        "Float.parse",
        "Float.parse(text: String) -> Float?",
        "Parses a decimal float.\n\n"
        "Accepts digits with an optional fraction and exponent (`1`, `-2.5`, `1e3`). "
        "Whitespace, `NaN`, infinities and overflow return `nil`. A non-string "
        "argument raises `RuntimeError`.",
    ),
    BuiltinDoc(
        "math",
        "math",
        "Deterministic math namespace.\n\n"
        "No locale or host state is consulted. Functions returning `Int` "
        "(`floor`, `ceil`, `round`, `trunc`) require a finite value in i64 range and "
        "raise `RuntimeError` otherwise.",
        kind="module",
    ),
    BuiltinDoc(
        "math.abs",
        "math.abs(value: Int | Float) -> Int | Float",
        "Returns the absolute value, preserving the argument type.\n\n"
        "An `Int` stays `Int` (under `--debug`, `abs(INT_MIN)` raises on overflow); a "
        "`Float` stays `Float`.",
    ),
    BuiltinDoc(
        "math.min",
        "math.min(a: Int | Float, b: Int | Float) -> Int | Float",
        "Returns the smaller of two numbers.\n\n"
        "Promotes to `Float` when either argument is `Float`; any `NaN` argument "
        "makes the result `NaN`.",
    ),
    BuiltinDoc(
        "math.max",
        "math.max(a: Int | Float, b: Int | Float) -> Int | Float",
        "Returns the larger of two numbers.\n\n"
        "Promotes to `Float` when either argument is `Float`; any `NaN` argument "
        "makes the result `NaN`.",
    ),
    BuiltinDoc(
        "math.clamp",
        "math.clamp(value: Int | Float, low: Int | Float, high: Int | Float) -> Int | Float",
        "Clamps `value` into the inclusive range `[low, high]`.\n\n"
        "Requires `low <= high`; otherwise `RuntimeError` is raised. A `NaN` in any "
        "argument makes the result `NaN`; mixed `Int`/`Float` promotes to `Float`.",
    ),
    BuiltinDoc(
        "math.floor",
        "math.floor(value: Float) -> Int",
        "Rounds down to an integer.\n\n"
        "Requires a `Float`; the value must be finite and fit in i64, otherwise "
        "`RuntimeError` is raised.",
    ),
    BuiltinDoc(
        "math.ceil",
        "math.ceil(value: Float) -> Int",
        "Rounds up to an integer.\n\n"
        "Requires a `Float`; the value must be finite and fit in i64, otherwise "
        "`RuntimeError` is raised.",
    ),
    BuiltinDoc(
        "math.round",
        "math.round(value: Float) -> Int",
        "Rounds to the nearest integer, with ties away from zero.\n\n"
        "Requires a `Float`; the value must be finite and fit in i64, otherwise "
        "`RuntimeError` is raised.",
    ),
    BuiltinDoc(
        "math.trunc",
        "math.trunc(value: Float) -> Int",
        "Truncates toward zero.\n\n"
        "Requires a `Float`; the value must be finite and fit in i64, otherwise "
        "`RuntimeError` is raised.",
    ),
    BuiltinDoc(
        "math.sqrt",
        "math.sqrt(value: Float) -> Float",
        "Returns the square root as a `Float`.\n\n"
        "Requires a `Float`. A negative argument returns `NaN` instead of raising.",
    ),
    BuiltinDoc(
        "io",
        "io",
        "Standard input/output namespace.\n\n"
        "`write`, `writeErr` and `flush` are deterministic; the read functions are "
        "ambient and may block.",
        kind="module",
        ambient=True,
    ),
    BuiltinDoc(
        "io.readFile",
        "io.readFile(path: String) -> String?",
        "Reads a UTF-8 file into a string, or `nil` when it cannot be read.\n\n"
        "Ambient. Invalid UTF-8 counts as unreadable (`nil`); the content is returned "
        "exactly as stored, including any trailing newline.",
        ambient=True,
    ),
    BuiltinDoc(
        "io.readAll",
        "io.readAll() -> String",
        "Reads all remaining standard input as text.\n\n"
        'Ambient. At immediate end of input it returns `""`; invalid UTF-8 raises '
        "`RuntimeError`.",
        ambient=True,
    ),
    BuiltinDoc(
        "io.write",
        "io.write(text: String) -> Nil",
        "Writes `text` to standard output without a trailing newline.\n\n"
        "Flushes immediately, so output order is observable before the next read or "
        "process exit.",
    ),
    BuiltinDoc(
        "io.writeErr",
        "io.writeErr(text: String) -> Nil",
        "Writes `text` to standard error without a trailing newline.\n\n"
        "Flushes immediately; stderr is not part of the default golden comparison.",
    ),
    BuiltinDoc(
        "io.writeFile",
        "io.writeFile(path: String, text: String) -> Bool",
        "Writes `text` as UTF-8, creating or truncating the file.\n\n"
        "Ambient. Returns `true` on success and `false` on a filesystem error; the "
        "parent directory must exist.",
        ambient=True,
    ),
    BuiltinDoc(
        "io.readLine",
        "io.readLine() -> String?",
        "Reads one line from standard input.\n\n"
        "Ambient. A trailing LF or CRLF is removed; `nil` means immediate end of "
        "input. Invalid UTF-8 raises `RuntimeError`.",
        ambient=True,
    ),
    BuiltinDoc(
        "io.readUtf8",
        "io.readUtf8(n: Int) -> String?",
        "Reads exactly `n` bytes and decodes them as strict UTF-8.\n\n"
        "Ambient. `nil` only at immediate end of input; a short read or invalid "
        "UTF-8 raises `RuntimeError`. `n` must be non-negative; `n == 0` returns "
        '`""`.',
        ambient=True,
    ),
    BuiltinDoc(
        "io.flush",
        "io.flush() -> Nil",
        "Flushes standard output and standard error.",
    ),
    BuiltinDoc(
        "fs",
        "fs",
        "Filesystem namespace (ambient).\n\n"
        "Operations read the host filesystem and are outside the I1 corpus; tests "
        "use temporary directories and never print absolute paths.",
        kind="module",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.exists",
        "fs.exists(path: String) -> Bool",
        "Returns whether `path` exists.\n\n"
        "Ambient. True for files, directories and other entries the host can stat.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.open",
        "fs.open(path: String, mode: String) -> Int",
        "Opens `path` in mode `r`, `w` or `a` and returns a 1-based handle.\n\n"
        "Ambient. `w` truncates/creates and `a` creates and appends; failure raises "
        "`RuntimeError` with a stable kind prefix (`notFound: ...`).",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.read",
        "fs.read(id: Int, n: Int) -> String?",
        "Reads at most `n` bytes from a file handle, always a complete UTF-8 prefix.\n\n"
        "Ambient. `nil` is end of file; invalid UTF-8 or a handle not open for reading "
        "raises.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.readBytes",
        "fs.readBytes(id: Int, n: Int) -> Bytes?",
        "Reads at most `n` raw bytes from a file handle, without UTF-8 validation.\n\n"
        "Ambient. `nil` is immediate end of file and `n == 0` is the empty `Bytes`; a "
        "handle not open for reading or a negative `n` raises.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.write",
        "fs.write(id: Int, text: String) -> Nil",
        "Writes all of `text` to a file handle.\n\n"
        "Ambient. A handle opened with `r`, a closed handle or a failed write raises.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.close",
        "fs.close(id: Int) -> Nil",
        "Closes a file handle; closing it again is a no-op.\n\n"
        "Ambient. An id that never existed raises.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.rename",
        "fs.rename(source: String, target: String) -> Nil",
        "Renames `source` to `target` with POSIX semantics: atomic and replacing an "
        "existing `target`.\n\n"
        "Ambient. Failure raises `RuntimeError` with a stable kind prefix "
        "(`notFound: ...`); across filesystems the kind is `crossDevice`.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.remove",
        "fs.remove(path: String) -> Nil",
        "Removes a file or symlink.\n\n"
        "Ambient. A directory is an `isDirectory` error; failure raises `RuntimeError`.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.mkdir",
        "fs.mkdir(path: String) -> Nil",
        "Creates one directory level.\n\n"
        "Ambient. An existing path is `alreadyExists`; a missing parent is `notFound`.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.stat",
        "fs.stat(path: String) -> (Int, Int, Bool)",
        "Returns `(size, mtimeMs, isDir)` for `path`, following symlinks.\n\n"
        "Ambient. `mtimeMs` is floor milliseconds since the epoch; the filesystem may "
        "have coarser resolution. Failure raises `RuntimeError`.",
        ambient=True,
    ),
    BuiltinDoc(
        "fs.listDir",
        "fs.listDir(path: String) -> List[String]?",
        "Returns the entry names of a directory, sorted, or `nil` when unreadable.\n\n"
        "Ambient. The sort makes the result deterministic for a given directory; "
        "`.` and `..` are not included.",
        ambient=True,
    ),
    BuiltinDoc(
        "process",
        "process",
        "Process and stream handles for the kernel (POSIX, ambient).\n\n"
        "Handles are opaque, 1-based `Int` ids; `0` is never a valid handle and is "
        "returned by `spawn` on failure.",
        kind="module",
        ambient=True,
    ),
    BuiltinDoc(
        "process.spawn",
        "process.spawn(argv: List[String]) -> Int",
        "Starts a process without a shell.\n\n"
        "Ambient. `argv[0]` is the program and the remaining items are its arguments; "
        "stdin/stdout/stderr are pipes. Returns a process handle, or `0` when the "
        "process cannot start.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.stdin",
        "process.stdin(handle: Int) -> Int",
        "Returns the stream handle for a process's standard input.\n\n"
        "Ambient. The process handle must be valid.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.stdout",
        "process.stdout(handle: Int) -> Int",
        "Returns the stream handle for a process's standard output.\n\n"
        "Ambient. The process handle must be valid.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.stderr",
        "process.stderr(handle: Int) -> Int",
        "Returns the stream handle for a process's standard error.\n\n"
        "Ambient. The process handle must be valid.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.wait",
        "process.wait(handle: Int) -> Int",
        "Waits for a process and returns its exit code.\n\n"
        "Ambient. A negative code means the child was terminated by a signal; the "
        "status is cached after the first wait.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.kill",
        "process.kill(handle: Int) -> Bool",
        "Sends `SIGKILL` to a process.\n\n"
        "Ambient. Returns `false` when the process already exited; records the exit "
        "status when it reaps the child.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.close",
        "process.close(handle: Int) -> Nil",
        "Releases a process or stream handle.\n\n"
        "Ambient. Does not kill a running process; after closing, any use of the "
        "handle raises `RuntimeError`.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.read",
        "process.read(handle: Int, n: Int) -> String?",
        "Reads up to `n` bytes from a stream as UTF-8.\n\n"
        "Ambient. `nil` at end of stream; an incomplete UTF-8 sequence is buffered for "
        "the next call, so a character is never split. `n` must be non-negative.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.write",
        "process.write(handle: Int, text: String) -> Bool",
        "Writes all of `text` to a stream.\n\n"
        "Ambient. Returns `false` when the other side closed the pipe.",
        ambient=True,
    ),
    BuiltinDoc(
        "process.poll",
        "process.poll(handles: List[Int], timeoutMs: Int) -> List[Int]",
        "Returns the handles that are ready.\n\n"
        "Ambient. A negative timeout waits forever and `0` is non-blocking; streams "
        "are ready when readable or at EOF, processes when they have exited. The "
        "result is deduplicated.",
        ambient=True,
    ),
    BuiltinDoc(
        "os",
        "os",
        "Operating-system namespace.",
        kind="module",
    ),
    BuiltinDoc(
        "os.exit",
        "os.exit(code: Int) -> Nil",
        "Flushes both streams and terminates the process with `code`.\n\n"
        "`code` must be in `0..255`; anything else raises `RuntimeError`.",
    ),
    BuiltinDoc(
        "os.getenv",
        "os.getenv(name: String) -> String?",
        "Returns the value of an environment variable, or `nil` when unset.\n\n"
        "Ambient: it reads the host environment.",
        ambient=True,
    ),
    BuiltinDoc(
        "time",
        "time",
        "Time namespace (ambient).\n\n"
        "Functions read the host clock; they are outside the I1/I3 corpus.",
        kind="module",
        ambient=True,
    ),
    BuiltinDoc(
        "time.now",
        "time.now() -> Int",
        "Returns the current Unix time in milliseconds.\n\n"
        "Ambient and non-deterministic; tests must not assert an exact value.",
        ambient=True,
    ),
    BuiltinDoc(
        "time.sleep",
        "time.sleep(milliseconds: Int) -> Nil",
        "Suspends the current process for at least `milliseconds`.\n\n"
        "Ambient. A negative duration raises `RuntimeError`.",
        ambient=True,
    ),
    BuiltinDoc(
        "digest.sha256",
        "digest.sha256(text: String) -> String",
        "Returns the SHA-256 of the UTF-8 bytes of `text` as 64 lowercase hex "
        "characters.\n\n"
        "Deterministic (`core`): same bytes in both engines. This is an integrity "
        "digest, not a password hash; for a human API use `std.hash.sha256`.",
    ),
    BuiltinDoc(
        "digest.sha256Bytes",
        "digest.sha256Bytes(data: Bytes) -> Bytes",
        "Returns the raw 32-byte SHA-256 of `data`.\n\n"
        "Deterministic (`core`): same bytes in both engines. Use `toHex()` for the "
        "printable form or `std.hash.sha256Bytes` for the wrapper.",
    ),
    BuiltinDoc(
        "regex_engine.compile",
        "regex_engine.compile(pattern: String, flags: Int, mode: Int) -> List[Int]",
        "Compiles a pattern and returns `[1, handle]`; on a failure it returns "
        "`[0, code, offset]`, where `offset` is the byte offset of a syntax error "
        "(`-1` when unavailable) and `code` is negative (`-9` is the per-program "
        "size limit, reported as `size` by the public module).\n\n"
        "`mode` is `0` (linear, the default: guaranteed linear time) or `1` (full: "
        "backreferences and lookaround, bounded by a fixed backtracking limit). "
        "`flags` is a mask: `1` caseless, `2` multiline, `4` dot-all, `8` extended. "
        "Low level: most programs should use the `regex` module on top of it.",
    ),
    BuiltinDoc(
        "regex_engine.find",
        "regex_engine.find(handle: Int, subject: String, start: Int) -> List[Int]?",
        "Matches a compiled pattern starting at the code-point offset `start`.\n\n"
        "Returns `nil` when there is no match, otherwise the flat span list "
        "`[start0, end0, start1, end1, ...]`, one pair per group, with `-1` for a group "
        "that did not participate. Offsets count code points, like every string index. "
        "Exceeding the backtracking limit raises `RuntimeError`.",
    ),
    BuiltinDoc(
        "regex_engine.groupNames",
        "regex_engine.groupNames(handle: Int) -> List[String]",
        "Capture-group names of a compiled pattern, one entry per group.\n\n"
        "Index `0` is always the empty string; unnamed groups are empty too, so a "
        "name maps to its index and the public `regex` module expands `$name`.",
    ),
    BuiltinDoc(
        "regex_engine.free",
        "regex_engine.free(handle: Int) -> Nil",
        "Releases a compiled pattern.\n\n"
        "Idempotent: freeing twice, or freeing an unknown handle, is not an error. "
        "There is no finalizer, so a program that compiles in a loop must free.",
    ),
    BuiltinDoc(
        "Bytes",
        "Bytes",
        "Immutable sequence of bytes (0..255).\n\n"
        "`len(b)` counts bytes; `b[i]` is an `Int` 0..255; `str`/`repr` render "
        "`0x<hex>`; equality is structural and `b == s` is `false`. `Bytes` is not a "
        "`Map` key and has no literal syntax. Build with `Bytes.fromText`, `fromList`, "
        "`fromHex` or `fromBase64`; slice/concat and conversions are value methods.",
        kind="module",
    ),
    BuiltinDoc(
        "Bytes.empty",
        "Bytes.empty() -> Bytes",
        "Returns the empty `Bytes`.",
    ),
    BuiltinDoc(
        "Bytes.fromList",
        "Bytes.fromList(xs: List[Int]) -> Bytes",
        "Copies a list of integers 0..255 into `Bytes`.\n\n"
        "A value outside 0..255 (or a non-integer element) raises `RuntimeError`.",
    ),
    BuiltinDoc(
        "Bytes.fromText",
        "Bytes.fromText(text: String) -> Bytes",
        "Encodes the UTF-8 bytes of `text`.",
    ),
    BuiltinDoc(
        "Bytes.fromHex",
        "Bytes.fromHex(text: String) -> Result[Bytes, BytesError]",
        "Decodes RFC 4648 base16.\n\n"
        "Accepts lowercase and uppercase digits; an odd length or a non-hex "
        "character is `Err(BytesError.InvalidHex(message))`.",
    ),
    BuiltinDoc(
        "Bytes.fromBase64",
        "Bytes.fromBase64(text: String) -> Result[Bytes, BytesError]",
        "Decodes canonical RFC 4648 base64 (standard alphabet, padding required).\n\n"
        "Invalid, unpadded or non-canonical input is "
        "`Err(BytesError.InvalidBase64(message))`.",
    ),
    BuiltinDoc(
        "Bytes.slice",
        "Bytes.slice(start: Int, end: Int) -> Bytes",
        "Returns the half-open byte range `start..end`.\n\n"
        "Same bounds rules as `substr`: negative, inverted or past-the-end ranges "
        "raise `RuntimeError`.",
        kind="method",
    ),
    BuiltinDoc(
        "Bytes.concat",
        "Bytes.concat(other: Bytes) -> Bytes",
        "Returns a new `Bytes` with `other` appended; neither operand is mutated.",
        kind="method",
    ),
    BuiltinDoc(
        "Bytes.toList",
        "Bytes.toList() -> List[Int]",
        "Copies the bytes into a new `List[Int]`.",
        kind="method",
    ),
    BuiltinDoc(
        "Bytes.toText",
        "Bytes.toText() -> Result[String, BytesError]",
        "Decodes strict UTF-8; invalid input is "
        "`Err(BytesError.InvalidUtf8(message))` and is never replaced.",
        kind="method",
    ),
    BuiltinDoc(
        "Bytes.toHex",
        "Bytes.toHex() -> String",
        "Returns lowercase RFC 4648 base16.",
        kind="method",
    ),
    BuiltinDoc(
        "Bytes.toBase64",
        "Bytes.toBase64() -> String",
        "Returns canonical RFC 4648 base64 with padding.",
        kind="method",
    ),
    # ------------------------------------------------------------------
    # Built-in types
    # ------------------------------------------------------------------
    BuiltinDoc(
        "Result",
        "Result[T, E]",
        "Built-in generic sum type with `Result.Ok(value)` and `Result.Err(error)`.\n\n"
        "Use an exhaustive `match` to inspect it, or the combinators in "
        "`std.results`.",
        kind="type",
    ),
    BuiltinDoc(
        "BytesError",
        "BytesError",
        "Failure of a `Bytes` conversion.\n\n"
        "Variants: `BytesError.InvalidHex(message)`, `InvalidBase64(message)` and "
        "`InvalidUtf8(message)`. Available without an import; use `match` to inspect it.",
        kind="type",
    ),
    BuiltinDoc(
        "Exception",
        "Exception",
        "Base class for catchable runtime errors.\n\n"
        "`except Exception as e` catches user exceptions and runtime panics converted "
        "to `RuntimeError`.",
        kind="type",
    ),
    BuiltinDoc(
        "RuntimeError",
        "RuntimeError",
        "Catchable runtime error type, below `Exception`.\n\n"
        "Raised by the `raise` statement and by runtime panics; the `message` field "
        "holds the diagnostic text.",
        kind="type",
    ),
)

BY_NAME = {item.name: item for item in BUILTIN_DOCS}

__all__ = ["BUILTIN_DOCS", "BY_NAME", "BuiltinDoc"]
