---
title: std.fs
sources:
  - std/fs.lx
  - loxia/docgen.py
---

# std.fs

File reading/writing (ambient: outside I1).

## API

## Functions

### `fn readText(path: String) -> String | Nil`

Reads a UTF-8 file, returning `nil` when unreadable.

### `fn readLines(path: String) -> List[String] | Nil`

Reads a UTF-8 file as lines, returning `nil` when unreadable.

### `fn writeText(path: String, text: String) -> Bool`

Writes UTF-8 text, returning whether the write succeeded.

### `fn appendText(path: String, text: String) -> Bool`

Appends UTF-8 text, returning whether the write succeeded.

### `fn exists(path: String) -> Bool`

Returns whether the path exists.

### `fn listDir(path: String) -> List[String] | Nil`

Lists directory entries, returning `nil` when unreadable.
