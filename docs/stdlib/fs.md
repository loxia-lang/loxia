---
title: std.fs
sources:
  - std/fs.lx
  - loxia/docgen.py
---

# std.fs

File reading and writing. Ambient: outside the I1 corpus.

## API

## Classes

### `class FileError`

Host failure of a filesystem operation.

#### `val kind: String`

Stable token: `notFound`, `permission`, `isDirectory`, `notDirectory`,
`alreadyExists`, `tooManyFiles`, `noSpace`, `badMode`, `closed`, `invalidHandle`,
`io`.

#### `val message: String`

Human-readable detail; never contains an absolute path.

#### `fn init(kind: String, message: String)`

Builds a failure from a stable kind and a message.

### `class File`

Open file handle; close it, or prefer `withOpen`.

#### `val id: Int`

Kernel handle used by `fs.*`.

#### `fn init(id: Int)`

Wraps an existing handle; prefer `open`.

#### `fn read(n: Int) -> Result[String | Nil, FileError]`

Reads up to `n` bytes at a UTF-8 boundary; `Ok(nil)` means end of file.

#### `fn write(text: String) -> Result[Nil, FileError]`

Writes all of `text`.

#### `fn close() -> Result[Nil, FileError]`

Closes the handle; closing twice is a no-op.

## Functions

### `fn open(path: String, mode: String) -> Result[File, FileError]`

Opens `path` in mode `r`, `w` or `a`.

`w` truncates/creates, `a` creates and appends; `r` requires the file to exist.

### `fn withOpen[T](path: String, mode: String, body: fn(File) -> T) -> Result[T, FileError]`

Opens `path`, calls `body` and closes the file even when `body` raises.

This is the scoped form of `open`, replacing a `with` block: the handle never
escapes, and the close runs on normal return and on error.

### `fn readText(path: String) -> Result[String, FileError]`

Reads a UTF-8 file into a string.

### `fn readLines(path: String) -> Result[List[String], FileError]`

Reads a UTF-8 file as one string per line (LF and CRLF; no trailing empty item).

### `fn writeText(path: String, text: String) -> Result[Nil, FileError]`

Writes `text` as UTF-8, overwriting/creating the file.

### `fn appendText(path: String, text: String) -> Result[Nil, FileError]`

Appends `text` as UTF-8, creating the file when missing.

### `fn exists(path: String) -> Bool`

Returns whether `path` exists (file, directory or other entry).

### `fn listDir(path: String) -> Result[List[String], FileError]`

Lists directory entry names in sorted order.
