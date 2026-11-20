---
title: std.proc
sources:
  - std/proc.lx
  - loxia/docgen.py
---

# std.proc

Processes, streams and `poll` (POSIX, ambient: outside I1/I3).

## API

## Classes

### `class ProcError`

Host failure of a process operation.

#### `val kind: String`

Stable token: `spawnFailed`, `closed`, `pipeClosed`, `timeout`, `io`.

#### `val message: String`

Human-readable detail; no PID, path or locale text.

#### `fn init(kind: String, message: String)`

Builds a failure from a stable kind and a message.

### `class Stream`

Byte stream of a child process (`stdin`, `stdout` or `stderr`).

#### `val id: Int`

Stream handle used by `proc.*`.

#### `fn init(id: Int)`

Wraps an existing stream handle.

#### `fn read(n: Int) -> Result[String | Nil, ProcError]`

Reads up to `n` bytes, or `Ok(nil)` at end of stream.

Reading stops at a UTF-8 boundary, so the returned text is always valid even when
`n` lands inside a multi-byte code point.

#### `fn write(text: String) -> Result[Nil, ProcError]`

Writes all text; `pipeClosed` when the other side closed the pipe.

#### `fn close() -> Result[Nil, ProcError]`

Closes the descriptor; closing twice is a no-op.

### `class Process`

Child process with its three channels connected to pipes.

#### `val id: Int`

Process handle used by `proc.*`.

#### `val stdin: Stream`

Child's standard input.

#### `val stdout: Stream`

Child's standard output.

#### `val stderr: Stream`

Child's standard error.

#### `fn init(id: Int)`

Wraps an already-started process handle; prefer `spawn`.

#### `fn wait() -> Result[Int, ProcError]`

Waits for the process to exit and returns its status.

A negative status means the child was terminated by a signal.

#### `fn kill() -> Bool`

Sends `SIGKILL`, returning `false` when the process already exited.

#### `fn close() -> Result[Nil, ProcError]`

Closes the channels and releases the handle; closing twice is a no-op.

### `class Output`

Captured output of a finished `run`.

#### `val code: Int`

Exit code (negative when the child died from a signal).

#### `val stdout: String`

Everything the child wrote to stdout.

#### `val stderr: String`

Everything the child wrote to stderr.

#### `fn init(code: Int, stdout: String, stderr: String)`

Builds the result of a finished run.

## Functions

### `fn spawn(argv: List[String]) -> Result[Process, ProcError]`

Starts `argv` without a shell, with pipes on all three channels.

`argv[0]` is resolved by the OS, not by a shell, so no quoting or command
interpolation happens.

### `fn run(argv: List[String], stdin: String = ..., timeoutMs: Int = ...) -> Result[Output, ProcError]`

Runs `argv` to completion and returns its exit code and captured output.

`stdin` is written before the first `poll` (practical limit: the pipe buffer,
~64 KiB; larger text can block if the child does not read). `timeoutMs > 0` kills the
process and returns `Err(ProcError("timeout", ...))`. There is no shell.
