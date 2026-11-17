---
title: std.paths
sources:
  - std/paths.lx
  - loxia/docgen.py
---

# std.paths

Lexical POSIX path helpers; no filesystem access.

## API

## Functions

### `fn isAbsolute(path: String) -> Bool`

Returns whether the POSIX path is absolute.

A path is absolute when its first code point is `/`; the empty string is relative.

### `fn split(path: String) -> List[String]`

Splits a POSIX path into components.

Splits on `/` and drops empty components, so repeated and leading/trailing
separators disappear: `split("/a//b/")` is `["a", "b"]` and `split("")` is `[]`.

### `fn joinPath(base: String, child: String) -> String`

Joins a base path and a child path with a single `/` separator.

An absolute `child` (or an empty `base`) wins and is returned unchanged. An empty
`child` returns `base`. This is a lexical join: `.` and `..` are not resolved and
separators already present in `child` are preserved.

### `fn basename(path: String) -> String`

Returns the final path component.

Trailing separators are ignored. `/` is its own basename and the empty path maps
to `.`; `basename("a/b/")` is `"b"`.

### `fn dirname(path: String) -> String`

Returns the parent path without a trailing separator.

`dirname("/a")` is `/`, `dirname("a")` and the empty path are `.`. The result is
lexical: no filesystem lookup or symlink resolution happens.

### `fn ext(path: String) -> String`

Returns the file extension of the final component, without the leading dot.

`ext("a/b.tar.gz")` is `"gz"`; a dotfile such as `.bashrc` has no extension, and a
missing extension returns `""`.

### `fn stem(path: String) -> String`

Returns the final component without its extension.

`stem("a/b.tar.gz")` is `"b.tar"`; a name without an extension is returned
unchanged, and dotfiles such as `.bashrc` keep their leading dot.

### `fn normalize(path: String) -> String`

Resolves `.` and `..` lexically, collapsing repeated separators.

Absolute paths keep their leading `/`; `..` above a relative root is preserved, so
`normalize("a/../..")` is `".."`. The empty path normalizes to `.`. No filesystem
access and no symlink resolution: the result depends only on the input text.
