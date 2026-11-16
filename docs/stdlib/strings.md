---
title: std.strings
sources:
  - std/strings.lx
  - loxia/docgen.py
---

# std.strings

UTF-8 text operations over code points.

## API

## Functions

### `fn isEmpty(s: String) -> Bool`

Returns true when the string has no characters.

### `fn isBlank(s: String) -> Bool`

Returns true when the string is empty or only whitespace.

### `fn ltrim(s: String) -> String`

Removes leading whitespace.

### `fn rtrim(s: String) -> String`

Removes trailing whitespace.

### `fn trim(s: String) -> String`

Removes leading and trailing whitespace.

### `fn startsWith(s: String, prefix: String) -> Bool`

Returns whether the string starts with `prefix`.

### `fn endsWith(s: String, suffix: String) -> Bool`

Returns whether the string ends with `suffix`.

### `fn indexOf(s: String, needle: String) -> Int`

Returns the first code-point index of `needle`, or -1.

### `fn lastIndexOf(s: String, needle: String) -> Int`

Returns the last code-point index of `needle`, or -1.

### `fn contains(s: String, needle: String) -> Bool`

Returns whether the string contains `needle`.

### `fn split(s: String, separator: String) -> List[String]`

Splits on a separator.

### `fn splitLines(s: String) -> List[String]`

Splits into lines, accepting LF, CRLF and CR.

### `fn lines(s: String) -> List[String]`

Splits into lines, accepting LF, CRLF and CR.

### `fn words(s: String) -> List[String]`

Splits on whitespace, ignoring empty fields.

### `fn repeat(s: String, count: Int) -> String`

Repeats the string `count` times.

### `fn upper(s: String) -> String`

Returns an uppercase copy.

### `fn lower(s: String) -> String`

Returns a lowercase copy.

### `fn capitalize(s: String) -> String`

Uppercases the first character and lowercases the rest.

### `fn reverse(s: String) -> String`

Reverses by code points.

### `fn count(s: String, needle: String) -> Int`

Counts non-overlapping occurrences of `needle`.

### `fn replaceFirst(s: String, old: String, new: String) -> String`

Replaces the first occurrence of `old`.

### `fn replaceAll(s: String, old: String, new: String) -> String`

Replaces every occurrence of `old`.

### `fn slice(s: String, start: Int, end: Int) -> String`

Returns the half-open range `[start, end)`.

### `fn padStart(s: String, width: Int, fill: String) -> String`

Pads on the left to `width` using `fill`.

### `fn padEnd(s: String, width: Int, fill: String) -> String`

Pads on the right to `width` using `fill`.
