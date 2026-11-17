---
title: std.convert
sources:
  - std/convert.lx
  - loxia/docgen.py
---

# std.convert

Text conversions (integer/float/bool, Base64, hex) over UTF-8 bytes.

## API

## Functions

### `fn toInt(text: String) -> Int | Nil`

Parses a decimal integer, returning `nil` when invalid.

Delegates to `Int.parse`: an optional `+`/`-` followed by ASCII digits, with no
surrounding whitespace. Values outside the i64 range return `nil`.

### `fn toFloat(text: String) -> Float | Nil`

Parses a decimal float, returning `nil` when invalid.

Delegates to `Float.parse`: digits with an optional fraction and exponent
(`1`, `-2.5`, `1e3`). Surrounding whitespace is rejected, and non-finite results
return `nil`.

### `fn toBool(text: String) -> Bool | Nil`

Parses `true` or `false`, returning `nil` when invalid.

The match is exact: `True` and `FALSE` return `nil`, as does any other text.

### `fn base64Encode(text: String) -> String`

Encodes UTF-8 text as standard Base64.

Uses the `A-Z a-z 0-9 + /` alphabet with `=` padding and no line breaks. Each code
point is first expanded to its UTF-8 bytes, so the result depends only on the text.

### `fn base64Decode(text: String) -> String | Nil`

Decodes standard Base64 into UTF-8 text.

Requires padded input whose length is a multiple of 4. Returns `nil` for invalid
characters, misplaced padding, or bytes that are not valid UTF-8. The empty string
decodes to `""`.

### `fn hexEncode(text: String) -> String`

Encodes UTF-8 text as lowercase hexadecimal.

Each UTF-8 byte becomes two lowercase digits, so the result is twice as long as the
byte sequence.

### `fn hexDecode(text: String) -> String | Nil`

Decodes hexadecimal into UTF-8 text.

Accepts lowercase and uppercase digits and requires an even number of them. Returns
`nil` for invalid digits or bytes that are not valid UTF-8.
