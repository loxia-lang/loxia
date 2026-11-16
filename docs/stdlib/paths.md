---
title: std.paths
sources:
  - std/paths.lx
  - loxia/docgen.py
---

# std.paths

Lexical POSIX path helpers.

## API

## Functions

### `fn isAbsolute(path: String) -> Bool`

Returns whether the POSIX path is absolute.

### `fn split(path: String) -> List[String]`

Splits a POSIX path into components.

### `fn join(base: String, child: String) -> String`

Joins a base path and a child path, normalizing separators.

### `fn basename(path: String) -> String`

Returns the final path component.

### `fn dirname(path: String) -> String`

Returns the parent path.

### `fn ext(path: String) -> String`

Returns the file extension including the dot, or the empty string.

### `fn stem(path: String) -> String`

Returns the filename without its extension.

### `fn normalize(path: String) -> String`

Resolves `.` and `..` lexically.
