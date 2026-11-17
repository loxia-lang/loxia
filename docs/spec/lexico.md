---
sources:
  - loxia_core/frontend/scanner.py
  - loxia_core/frontend/keywords.py
  - loxia_core/frontend/token_type.py
  - loxia_core/frontend/tokens.py
---

# Lexicon

How the source code is split into tokens. Implementation: [`loxia_core/frontend/scanner.py`](../../loxia_core/frontend/scanner.py),
[`loxia_core/frontend/keywords.py`](../../loxia_core/frontend/keywords.py), [`loxia_core/frontend/token_type.py`](../../loxia_core/frontend/token_type.py).

## Files

- Encoding: UTF-8 (that is what `main.py` reads). Strings accept Unicode; `len`/index
  count code points ([ADR-0026](../adr/0026-freeze-1.0.md)).
- Identifiers are **ASCII** (`[A-Za-z_][A-Za-z0-9_]*`), with no Unicode normalization;
  Unicode is allowed in strings and comments, not in identifiers
  ([ADR-0035](../adr/0035-strings-texto.md));
  `ação` is not a valid name yet. The scanner walks the Python string.
- There is no special BOM or directives. A `.lx` file is a program **or a module**
  (file = module, ADR-0073); a first line `#!` is just a normal `#` comment.

## Spaces and comments

- Ignored: space, `\t`, `\r`.
- `\n` ends the line and increments the counter (lines start at **1**).
- Line comment: `#` to the end of the line.
- Documentation comment: `///` at the start of the line (after spaces), one or more
  consecutive lines immediately before a declaration. The text is Markdown; the
  first line is the summary. A blank line or another comment breaks the link; the doc
  is stored in the AST (`doc`) and does **not** become a token or reach the runtime ([ADR-0091](../adr/0091-doc-comments-e-geracao-de-docs.md)).
  `///` is only a doc at the start of the line; `//` is still integer division.
- Block comment: `/* ... */`, **nested** (`/* /* */ */`); an unclosed block is
  `Unterminated block comment.` and counts the inner lines.
- Comments appear anywhere between tokens (including at the end of a line); `#`
  inside a string is not a comment. There is no `--`.
- `//` is **not** a comment: it is the integer division operator. Where an
  expression is expected, `//` produces a targeted error (`'//' is integer division, and comments start
  with '#'`) instead of the generic `Expect expression.`

## Tokens

### One character

```
(   )   {   }   ,   .   -   +   ;   /   *   %   |   &   ^   ~
```

### One or two characters

```
!=          =    ==
<    <=          >    >=
.    ..    ...   -    ->
/    //          *    **
<    <<          >    >>    >>>
?    ??          ?.
```

`//` is integer division; `/` alone is `Float` division. `..` is the half-open range
(`0..10`), `..=` is the inclusive range (`0..=10`) and `...` is the
variadic/spread prefix (`...xs`, `f(...xs)`).
`?` is the optional type suffix; `??` is coalescing and `?.` is optional chaining. `#` and
`/*` start comments, not tokens.

### Literals

| Token | Rule | Value |
| --- | --- | --- |
| `NUMBER` | see below | `int` (i64) or `float` (f64) |
| `STRING` | `"` … `"` | `str` with the content between the quotes |
| `IDENTIFIER` | `ALPHA ( ALPHA \| DIGIT )*` | lexeme |

```
DIGIT   → "0" … "9"
ALPHA   → "a" … "z" | "A" … "Z" | "_"
```

Numbers ([ADR-0006](../adr/0006-int-float-separados.md)):

- **`Int`**: `DIGIT+` with an optional `_` between digits (`42`, `1_000_000`), or base
  `0x`/`0X` (hex), `0b`/`0B` (binary) and `0o`/`0O` (octal) — `0xFF` = 255, `0b1010` = 10,
  `0o755` = 493;
- **`Float`**: has a `.` with a digit on both sides and/or an exponent (`3.14`, `1e9`, `1.5e-3`,
  `1.0`);
- `1` is `Int`, `1.0` is `Float`; there are no suffixes (`1i64`, `1.0f32`) and no sign in the literal
  (the `-` is a unary operator);
- `_` only between digits: `1__0`, `_1` and `1_` are errors;
- `.5` and `1.` are not numbers (`1.` reads `1` and then `.`, a syntax error); bases do not
  accept `.` or an exponent;
- the maximum magnitude of `Int` is `9223372036854775807` (`2^63 - 1`); a larger literal is a compilation
  error. `INT_MIN` has no literal of its own: use `-9223372036854775807 - 1`;
- `1..10` (range) exists: the scanner requires a digit after the `.` of a float precisely so
  as not to swallow the `..`;
- `Float` is IEEE-754 binary64; a literal that overflows becomes `inf` (Python's behaviour).

Strings ([ADR-0070](../adr/0070-strings-multilinha-e-raw.md)):
- `"..."` is **single-line**; a real line break inside it is
  `Unterminated string; multiline strings use '"""'.` (the scanner discards the rest of the
  line so as not to cascade errors);
- `"""..."""` is the canonical form of a **multiline** string: it may contain free `"` and `""` and
  closes at the first `"""`; no removing the first line break and no dedent — the value
  is exactly what is between the delimiters (I2); unclosed → `Unterminated string.`;
- `r"..."` and `r"""..."""` are **raw**: `\` is literal and `${...}` does **not** interpolate. The `r`
  is only a prefix when the quote comes immediately after it; `r` alone is an identifier;
- `"..."` and `"""..."""` accept `\n`, `\t`, `\r`, `\"`, `\\`, `\0`, `\$` and `\u{XXXX}`
  (Unicode code point); an unknown escape is `Unknown escape sequence '\q'.`; an invalid `\u`
  is `Invalid Unicode escape.`;
- `${expression}` interpolates an expression (any expression, including another interpolated
  string); the expression's tokens are scanned in their own buffer and the closing `}`
  does not enter it. `\$` and `\${` produce literal `$`/`${`; `$` without `{` is
  literal;
- the line counter follows the content, including inside `"""`; the token is reported
  on the line where it ends.

### Keywords

```
and    as     async  await  class  elif   else   enum   except
false  finally fn    for    if     in     interface is  match
nil    not    or     raise  return super  this   true
try    val    var    while
```

`not` is negation (ADR-0068); `!` alone is not a token — the scanner reports
`Unexpected character: ! (use 'not' for negation).` and `!=` remains inequality.

`fn` replaced `fun`; `fun` is now an ordinary identifier (it is not a keyword).

They are case-sensitive (`Class` is an identifier).

`async` and `await` are **reserved** in preparation for asynchrony
([ADR-0037](../adr/0037-async-direcao.md)); they have no syntax yet, so using them as
identifiers is a compilation error.

### End of file

There is always an `EOF` token, with the current line. The parser depends on it.

## Lexical errors

| Situation | Message | Consequence |
| --- | --- | --- |
| character outside the alphabet | `Unexpected character: X` | compilation error (exit 65) |
| `!` alone (outside `!=`) | `Unexpected character: ! (use 'not' for negation).` | compilation error (exit 65) |
| unclosed string (EOF or open `"""`) | `Unterminated string.` | compilation error (exit 65) |
| line break in `"..."` | `Unterminated string; multiline strings use '"""'.` | compilation error (exit 65) |
| interpolation without `}` | `Unterminated interpolation.` | compilation error (exit 65) |
| unknown escape | `Unknown escape sequence '\q'.` | compilation error (exit 65) |
| invalid `\u{...}` | `Invalid Unicode escape.` | compilation error (exit 65) |
| malformed numeric literal (`1__0`, `0x` without digits) | `Invalid number literal.` | compilation error (exit 65) |
| `Int` literal above `2^63 - 1` | `Too large integer literal.` | compilation error (exit 65) |

After an error the scanner continues; the parser may report more errors in the same run.
