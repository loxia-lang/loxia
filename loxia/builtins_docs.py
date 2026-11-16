"""Documentação English dos builtins/primitivas (ADR-0091).

Fonte de verdade para a página `docs/stdlib/builtins.md`; nomes e assinaturas são
conferidos por teste contra `BUILTIN_NAMES` e `PRIMITIVES`.
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
    BuiltinDoc("args", "args() -> List[String]", "Returns the program arguments."),
    BuiltinDoc("chars", "chars(s: String) -> List[String]", "Splits a string into code points."),
    BuiltinDoc("charCodeAt", "charCodeAt(s: String, index: Int) -> Int", "Returns the Unicode code point at a code-point index."),
    BuiltinDoc("fromCodePoint", "fromCodePoint(codePoint: Int) -> String", "Builds a one-code-point string from a Unicode scalar."),
    BuiltinDoc("join", "join(parts: List[String], separator: String) -> String", "Joins strings with a separator."),
    BuiltinDoc("len", "len(value: Any) -> Int", "Returns the length of a string, list, map or tuple."),
    BuiltinDoc("range", "range(start: Int, end: Int, step: Int = 1) -> Range", "Creates a lazy integer range."),
    BuiltinDoc("print", "print(value: Any) -> Nil", "Writes the display form followed by a newline."),
    BuiltinDoc("repr", "repr(value: Any) -> String", "Returns the debug representation."),
    BuiltinDoc("str", "str(value: Any) -> String", "Returns the display string."),
    BuiltinDoc("substr", "substr(text: String, start: Int, end: Int) -> String", "Returns the half-open code-point slice."),
    BuiltinDoc("Int", "Int", "Namespace for integer conversions.", kind="module"),
    BuiltinDoc("Int.parse", "Int.parse(text: String) -> Int?", "Parses a decimal integer, returning `nil` when invalid."),
    BuiltinDoc("Float", "Float", "Namespace for float conversions.", kind="module"),
    BuiltinDoc("Float.parse", "Float.parse(text: String) -> Float?", "Parses a decimal float, returning `nil` when invalid."),
    BuiltinDoc("math", "math", "Deterministic math namespace.", kind="module"),
    BuiltinDoc("math.abs", "math.abs(value: Int | Float) -> Int | Float", "Returns the absolute value."),
    BuiltinDoc("math.min", "math.min(a: Int | Float, b: Int | Float) -> Int | Float", "Returns the smaller value."),
    BuiltinDoc("math.max", "math.max(a: Int | Float, b: Int | Float) -> Int | Float", "Returns the larger value."),
    BuiltinDoc("math.clamp", "math.clamp(value: Int | Float, low: Int | Float, high: Int | Float) -> Int | Float", "Clamps a value into `[low, high]`."),
    BuiltinDoc("math.floor", "math.floor(value: Float) -> Int", "Rounds down to an integer."),
    BuiltinDoc("math.ceil", "math.ceil(value: Float) -> Int", "Rounds up to an integer."),
    BuiltinDoc("math.round", "math.round(value: Float) -> Int", "Rounds to the nearest integer."),
    BuiltinDoc("math.trunc", "math.trunc(value: Float) -> Int", "Truncates toward zero."),
    BuiltinDoc("math.sqrt", "math.sqrt(value: Float) -> Float", "Returns the square root."),
    BuiltinDoc("io", "io", "Standard input/output namespace.", kind="module"),
    BuiltinDoc("io.readFile", "io.readFile(path: String) -> String?", "Reads a UTF-8 file, returning `nil` when unreadable.", ambient=True),
    BuiltinDoc("io.readAll", "io.readAll() -> String", "Reads all remaining standard input.", ambient=True),
    BuiltinDoc("io.write", "io.write(text: String) -> Nil", "Writes to standard output."),
    BuiltinDoc("io.writeErr", "io.writeErr(text: String) -> Nil", "Writes to standard error."),
    BuiltinDoc("io.writeFile", "io.writeFile(path: String, text: String) -> Bool", "Writes a UTF-8 file.", ambient=True),
    BuiltinDoc("io.readLine", "io.readLine() -> String?", "Reads one line from standard input.", ambient=True),
    BuiltinDoc("io.readUtf8", "io.readUtf8(n: Int) -> String?", "Reads exactly `n` bytes of standard input as strict UTF-8; `nil` only at immediate end of input.", ambient=True),
    BuiltinDoc("io.flush", "io.flush() -> Nil", "Flushes standard output and standard error."),
    BuiltinDoc("fs", "fs", "Filesystem namespace.", kind="module"),
    BuiltinDoc("fs.exists", "fs.exists(path: String) -> Bool", "Returns whether the path exists.", ambient=True),
    BuiltinDoc("fs.listDir", "fs.listDir(path: String) -> List[String]?", "Lists directory entries, or `nil` when unreadable.", ambient=True),
    BuiltinDoc("process", "process", "Process and stream handles (POSIX, ambient).", kind="module"),
    BuiltinDoc("process.spawn", "process.spawn(argv: List[String]) -> Int", "Starts a process without a shell; 0 when it cannot start.", ambient=True),
    BuiltinDoc("process.stdin", "process.stdin(handle: Int) -> Int", "Returns the stdin stream handle of a process.", ambient=True),
    BuiltinDoc("process.stdout", "process.stdout(handle: Int) -> Int", "Returns the stdout stream handle of a process.", ambient=True),
    BuiltinDoc("process.stderr", "process.stderr(handle: Int) -> Int", "Returns the stderr stream handle of a process.", ambient=True),
    BuiltinDoc("process.wait", "process.wait(handle: Int) -> Int", "Waits for a process; negative code means a signal.", ambient=True),
    BuiltinDoc("process.kill", "process.kill(handle: Int) -> Bool", "Sends SIGKILL; false when the process already exited.", ambient=True),
    BuiltinDoc("process.close", "process.close(handle: Int) -> Nil", "Releases a handle (does not kill a running process).", ambient=True),
    BuiltinDoc("process.read", "process.read(handle: Int, n: Int) -> String?", "Reads up to `n` bytes as UTF-8; `nil` at end of stream.", ambient=True),
    BuiltinDoc("process.write", "process.write(handle: Int, text: String) -> Bool", "Writes all text; false when the other side closed.", ambient=True),
    BuiltinDoc("process.poll", "process.poll(handles: List[Int], timeoutMs: Int) -> List[Int]", "Returns ready stream/process ids; negative timeout waits forever.", ambient=True),
    BuiltinDoc("os", "os", "Operating-system namespace.", kind="module"),
    BuiltinDoc("os.exit", "os.exit(code: Int) -> Nil", "Terminates the process with an exit code."),
    BuiltinDoc("os.getenv", "os.getenv(name: String) -> String?", "Reads an environment variable.", ambient=True),
    BuiltinDoc("time", "time", "Time namespace (ambient).", kind="module"),
    BuiltinDoc("time.now", "time.now() -> Int", "Returns the current Unix time in milliseconds.", ambient=True),
    BuiltinDoc("time.sleep", "time.sleep(milliseconds: Int) -> Nil", "Sleeps for the given duration.", ambient=True),
    BuiltinDoc("Result", "Result[T, E]", "Built-in sum type with `Ok(T)` and `Err(E)`.", kind="type"),
    BuiltinDoc("Exception", "Exception", "Base class for catchable runtime errors.", kind="type"),
    BuiltinDoc("RuntimeError", "RuntimeError", "Catchable runtime error type.", kind="type"),
)

BY_NAME = {item.name: item for item in BUILTIN_DOCS}

__all__ = ["BUILTIN_DOCS", "BY_NAME", "BuiltinDoc"]
