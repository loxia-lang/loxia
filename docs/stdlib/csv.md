---
title: std.csv
sources:
  - std/csv.lx
  - loxia/docgen.py
---

# std.csv

RFC 4180 CSV parsing and serialization.

## API

## Functions

### `fn parse(text: String) -> List[List[String]] | Nil`

Parses RFC 4180 CSV text into rows, returning `nil` on malformed input.

### `fn stringify(rows: List[List[String]]) -> String`

Serializes rows as RFC 4180 CSV, quoting fields when needed.
