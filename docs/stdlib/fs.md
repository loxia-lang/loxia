---
title: std.fs
sources:
  - std/fs.lx
  - loxia/docgen.py
---

# std.fs

File reading and writing. Ambient: outside the I1 corpus.

## API

## Functions

### `fn readText(path: String) -> String | Nil`

Reads a UTF-8 file into a string, or `nil` when unreadable.

Ambient: the content depends on the filesystem. Text is returned exactly as stored,
including any trailing newline, and invalid UTF-8 yields `nil`.

### `fn readLines(path: String) -> List[String] | Nil`

Reads a UTF-8 file as one string per line, or `nil` when unreadable.

Accepts LF and CRLF line endings (a bare CR is not a break). Only the final empty
segment is dropped, so a file ending in a newline does not produce a trailing empty
item.

### `fn writeText(path: String, text: String) -> Bool`

Writes `text` as UTF-8, returning whether the write succeeded.

Ambient. Overwrites an existing file and creates a missing one; the parent
directory must exist. A filesystem error returns `false` instead of raising.

### `fn appendText(path: String, text: String) -> Bool`

Appends UTF-8 text, returning whether the write succeeded.

Ambient. Reads the current content and rewrites the file because the kernel has no
append primitive; a missing file is created. The parent directory must exist.

### `fn exists(path: String) -> Bool`

Returns whether `path` exists.

Ambient. True for files, directories and other entries that the host can stat.

### `fn listDir(path: String) -> List[String] | Nil`

Lists directory entry names in sorted order, or `nil` when unreadable.

Ambient. Sorting makes the result deterministic for a given directory; hidden files
are included and `"."`/`".."` are not.
