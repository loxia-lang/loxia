---
title: std.convert
sources:
  - std/convert.lx
  - loxia/docgen.py
---

# std.convert

Text conversions (integer/float/bool, Base64, hex) over UTF-8 bytes.

## API

## Classes

### `class DecodeError`

Falha de decodificação de texto (`base64DecodeResult`, `hexDecodeResult`).

`kind` é estável (`invalidBase64`, `invalidHex`, `invalidUtf8`); `index` é a posição
no texto de entrada; `len(text)` quando a falha é de comprimento (fim do texto, não uma
posição dentro dele); ou `-1` quando o problema está nos bytes decodificados (UTF-8
inválido) e não em um caractere. `message` é determinística, sem caminho nem locale.

#### `val kind: String`

Token estável: `invalidBase64`, `invalidHex` ou `invalidUtf8`.

#### `val index: Int`

Posição do problema no texto, ou `-1`.

#### `val message: String`

Detalhe determinístico.

#### `fn init(kind: String, index: Int, message: String)`

Cria a falha com o token estável, a posição e o detalhe.

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

### `fn base64DecodeResult(text: String) -> Result[String, DecodeError]`

Decodes standard Base64 into UTF-8 text, preserving the cause of a malformed input.

Requires padded input whose length is a multiple of 4. `Err` carries a `DecodeError`
with the position of the invalid character or of the misplaced padding; a length that
is not a multiple of 4 uses `index == len(text)`; bytes that are not valid UTF-8 are
`invalidUtf8` with `index` `-1`. The empty string decodes to `""`.

### `fn base64Decode(text: String) -> String | Nil`

Decodes standard Base64 into UTF-8 text.

Requires padded input whose length is a multiple of 4. Returns `nil` for invalid
characters, misplaced padding, or bytes that are not valid UTF-8. The empty string
decodes to `""`. Ergonomic shell over `base64DecodeResult` (ADR-0135).

### `fn hexEncode(text: String) -> String`

Encodes UTF-8 text as lowercase hexadecimal.

Each UTF-8 byte becomes two lowercase digits, so the result is twice as long as the
byte sequence.

### `fn hexDecodeResult(text: String) -> Result[String, DecodeError]`

Decodes hexadecimal into UTF-8 text, preserving the cause of a malformed input.

Accepts lowercase and uppercase digits and requires an even number of them. `Err`
carries a `DecodeError` with the position of the invalid digit; an odd length uses
`index == len(text)`; bytes that are not valid UTF-8 are `invalidUtf8` with `index` `-1`.

### `fn hexDecode(text: String) -> String | Nil`

Decodes hexadecimal into UTF-8 text.

Accepts lowercase and uppercase digits and requires an even number of them. Returns
`nil` for invalid digits or bytes that are not valid UTF-8. Ergonomic shell over
`hexDecodeResult` (ADR-0135).
