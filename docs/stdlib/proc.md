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

### `class Stream`

Byte stream of a child process (`stdin`, `stdout` or `stderr`).

#### `val id: Int`

Stream handle used by `proc.*`.

#### `fn init(id: Int)`

Wraps an existing stream handle.

#### `fn read(n: Int) -> String | Nil`

Reads up to `n` bytes, or `nil` at end of stream.

Reading stops at a UTF-8 boundary, so the returned text is always valid even when
`n` lands inside a multi-byte code point.

#### `fn write(text: String) -> Bool`

Writes all text, returning `false` when the other side closed the pipe.

#### `fn close() -> Nil`

Closes the descriptor; using the stream afterwards is an error.

Close each handle once: a second close raises for an unknown handle.

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

#### `fn wait() -> Int`

Waits for the process to exit and returns its status.

A negative status means the child was terminated by a signal.

#### `fn kill() -> Bool`

Sends `SIGKILL`, returning `false` when the process already exited.

#### `fn close() -> Nil`

Closes the channels and releases the handle.

Does not kill a process that is still running; call `kill` first if needed.

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

### `fn spawn(argv: List[String]) -> Process | Nil`

Starts `argv` without a shell, with pipes on all three channels.

Returns `nil` when the process cannot be started. `argv[0]` is resolved by the OS,
not by a shell, so no quoting or command interpolation happens.

### `fn run(argv: List[String], stdin: String = ..., timeoutMs: Int = ...) -> Output | Nil`

Runs `argv` to completion and returns its exit code and captured output.

`stdin` is written before the first `poll` (practical limit: the pipe buffer,
~64 KiB; larger text can block if the child does not read). `timeoutMs > 0` kills the
process and returns `nil`. There is no shell and no command interpolation; `nil` also
means the process could not be started.
