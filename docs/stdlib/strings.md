---
title: std.strings
sources:
  - std/strings.lx
  - loxia/docgen.py
---

# std.strings

UTF-8 text operations over code points, not bytes or UTF-16 units.

## API

## Functions

### `fn isEmpty(s: String) -> Bool`

Returns `true` when the string has no characters.

### `fn isBlank(s: String) -> Bool`

Returns `true` when the string is empty or contains only whitespace.

Whitespace is space, tab, LF and CR, the same set used by `trim` and `words`.

### `fn ltrim(s: String) -> String`

Removes leading whitespace (space, tab, LF or CR).

### `fn rtrim(s: String) -> String`

Removes trailing whitespace (space, tab, LF or CR).

### `fn trim(s: String) -> String`

Removes leading and trailing whitespace (space, tab, LF or CR).

### `fn startsWith(s: String, prefix: String) -> Bool`

Returns whether the string starts with `prefix`.

An empty prefix always matches; a longer prefix never matches.

### `fn endsWith(s: String, suffix: String) -> Bool`

Returns whether the string ends with `suffix`.

An empty suffix always matches; a longer suffix never matches.

### `fn indexOf(s: String, needle: String) -> Int`

Returns the first code-point index of `needle`, or -1.

An empty needle matches at index 0. Indices count code points, not bytes.

### `fn lastIndexOf(s: String, needle: String) -> Int`

Returns the last code-point index of `needle`, or -1.

An empty needle returns `len(s)`. Indices count code points, not bytes.

### `fn contains(s: String, needle: String) -> Bool`

Returns whether the string contains `needle`; an empty needle is always contained.

### `fn split(s: String, separator: String) -> List[String]`

Splits on each occurrence of `separator`.

An empty separator splits into code points (`chars(s)`). Otherwise empty fields are
preserved: `split("a,,b", ",")` is `["a", "", "b"]`.

### `fn splitLines(s: String) -> List[String]`

Splits into lines on LF or CRLF.

A trailing newline produces a final empty line; `std.fs.readLines` drops it for file
input. A bare CR is not a line break here.

### `fn lines(s: String) -> List[String]`

Alias of `splitLines`; splits on LF or CRLF.

### `fn words(s: String) -> List[String]`

Splits on runs of whitespace, ignoring empty fields.

Leading and trailing whitespace is discarded, so `words("  a  b ")` is `["a", "b"]`.

### `fn repeat(s: String, count: Int) -> String`

Repeats the string `count` times.

A zero or negative count yields `""`.

### `fn upper(s: String) -> String`

Returns an uppercase copy.

Only ASCII `a-z` is mapped; other code points are copied unchanged (no Unicode case
folding).

### `fn lower(s: String) -> String`

Returns a lowercase copy.

Only ASCII `A-Z` is mapped; other code points are copied unchanged (no Unicode case
folding).

### `fn capitalize(s: String) -> String`

Uppercases the first code point and lowercases the rest.

Only ASCII letters change; an empty string is returned unchanged.

### `fn reverse(s: String) -> String`

Reverses by code points.

Combining marks and grapheme clusters are not handled specially: each code point is
moved independently.

### `fn count(s: String, needle: String) -> Int`

Counts non-overlapping occurrences of `needle`.

An empty needle returns 0.

### `fn replaceFirst(s: String, old: String, new: String) -> String`

Replaces the first occurrence of `old`.

Returns `s` unchanged when `old` is absent. An empty `old` matches at index 0, so
`new` is inserted before the text.

### `fn replaceAll(s: String, old: String, new: String) -> String`

Replaces every non-overlapping occurrence of `old`.

An empty `old` returns `s` unchanged, avoiding an infinite insertion.

### `fn slice(s: String, start: Int, end: Int) -> String`

Returns the half-open range `[start, end)`.

Indices are clamped: negatives become 0, `end < start` yields `""`, and `end` beyond
the string length is clamped to `len(s)`.

### `fn padStart(s: String, width: Int, fill: String) -> String`

Pads on the left with repeated `fill` to `width`.

If `s` is already at least `width` long, or `fill` is empty, `s` is returned
unchanged. The padding is truncated to the exact gap.

### `fn padEnd(s: String, width: Int, fill: String) -> String`

Pads on the right with repeated `fill` to `width`.

If `s` is already at least `width` long, or `fill` is empty, `s` is returned
unchanged. The padding is truncated to the exact width.
