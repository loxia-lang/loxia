---
title: std.csv
sources:
  - std/csv.lx
  - loxia/docgen.py
---

# std.csv

RFC 4180 CSV parsing and serialization, with CRLF output.

## API

## Functions

### `fn parse(text: String) -> List[List[String]] | Nil`

Parses RFC 4180 CSV text into rows of fields.

Accepts LF and CRLF line endings and preserves empty fields. Returns `nil` on
malformed input, including a stray quote in an unquoted field or an unterminated
quoted field. Empty text parses to `[]`; a blank line is a record with one empty
field, not an empty row.

### `fn stringify(rows: List[List[String]]) -> String`

Serializes rows as RFC 4180 CSV, quoting fields when needed.

Fields are quoted when they contain `,`, `"`, CR or LF, and embedded quotes are
doubled. Every row ends with CRLF, including the last one; an empty row raises
`RuntimeError` because RFC 4180 has no representation for it. `[]` yields `""`.
