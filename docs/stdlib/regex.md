---
title: regex
sources:
  - bundled/regex.lx
  - loxia/docgen.py
---

# regex

Unicode regular expressions: linear by default, backtracking opt-in.

## API

## Classes

### `class RegexError`

Why a pattern failed to compile.

#### `val kind: String`

Stable category: `syntax`, `arguments`, `mode`, `size` or `engine`.

#### `val offset: Int`

Byte offset of the syntax error reported by `compile`; `-1` when the engine
cannot report one (arguments, mode, size or engine error).

#### `fn init(kind: String, offset: Int = ...)`

Creates the error; pass the offset reported by `compile` (`-1` when unknown).

### `class Match`

One match. `text` is group 0; `groups` holds 1..n, `nil` when a group did not
participate.

#### `val text: String`

Group 0: the whole match.

#### `val start: Int`

Start offset in code points.

#### `val end: Int`

End offset in code points (exclusive).

#### `val groups: List[String | Nil]`

Capture groups 1..n, in source order.

#### `fn init(text: String, start: Int, end: Int, groups: List[String | Nil])`

Creates a match; prefer the values returned by `find`/`findAll`.

### `class Regex`

A compiled pattern. Close it to release the native handle.

#### `fn init(handle: Int, names: List[String])`

Wraps a native handle; prefer `compile` or `tryCompile`.

#### `fn close() -> Nil`

Releases the engine handle; idempotent.

#### `fn isMatch(text: String) -> Bool`

`true` when the pattern matches anywhere in `text`.

#### `fn find(text: String) -> Match | Nil`

Leftmost match; `nil` when the pattern does not match.

#### `fn findFrom(text: String, start: Int) -> Match | Nil`

Leftmost match at or after `start` (code points); `nil` when none.

#### `fn findAll(text: String) -> List[Match]`

All non-overlapping matches, left to right. An empty match advances one
code point, so `findAll` always terminates.

#### `fn replace(text: String, replacement: String) -> String`

Replaces the first match. `$0` is the whole match, `$1`.. the numbered
groups, `$name`/`${name}` the named ones and `$$` a literal dollar (use
`\${name}` in a Loxia string: `${...}` is interpolation). An unmatched
group expands to the empty string.

#### `fn replaceAll(text: String, replacement: String) -> String`

Replaces every non-overlapping match; same expansion rules as `replace`.

#### `fn split(text: String) -> List[String]`

Splits `text` on each match; empty fields are preserved.

## Functions

### `fn compile(pattern: String, caseless: Bool = ..., multiline: Bool = ..., dotall: Bool = ..., extended: Bool = ...) -> Result[Regex, RegexError]`

Compiles `pattern` for `Mode.Linear` (guaranteed linear time).

Flags: `caseless`, `multiline` (`^`/`$` per line), `dotall` (`.` matches
newline) and `extended` (ignore whitespace and `#` comments).

### `fn compileFull(pattern: String, caseless: Bool = ..., multiline: Bool = ..., dotall: Bool = ..., extended: Bool = ...) -> Result[Regex, RegexError]`

Compiles `pattern` for `Mode.Full`: backreferences and lookaround, bounded by
a fixed backtracking limit. The compiled program is also bounded per pattern
(delegated sub-regexes, DFA cache and VM instructions); an oversized pattern
or a variable lookbehind that needs more cache fails with kind `size`.
Prefer `compile` for untrusted patterns.

### `fn tryCompile(pattern: String, caseless: Bool = ..., multiline: Bool = ..., dotall: Bool = ..., extended: Bool = ...) -> Regex | Nil`

Like `compile`, but returns `nil` on a syntax error. Use `compile` when the
error kind matters.

### `fn tryCompileFull(pattern: String, caseless: Bool = ..., multiline: Bool = ..., dotall: Bool = ..., extended: Bool = ...) -> Regex | Nil`

Like `compileFull`, but returns `nil` on a syntax error.
