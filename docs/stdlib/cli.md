---
title: std.cli
sources:
  - std/cli.lx
  - loxia/docgen.py
---

# std.cli

Deterministic command-line parsing from a declarative spec.

## API

## Functions

### `fn parse(args: List[String], spec: List[String]) -> Map[String, Any]`

Parses command-line arguments against a declarative spec into a map.

`args` is the raw argument list without the program name. `spec` lists
`flag:NAME`, `option:NAME` and `positional:NAME` entries; the result contains one
key per name. Missing flags are `false`, missing options and positionals are `nil`.
Options accept `--name value` and `--name=value`, and `--` switches to
positional-only parsing.

Raises `RuntimeError` for an invalid or duplicate spec entry, an unknown option, a
missing option value, or a positional argument that the spec does not declare.

### `fn flag(parsed: Map[String, Any], name: String) -> Bool`

Returns whether a boolean flag was present.

Returns `false` when `name` is absent or does not hold a `Bool`, so a value from a
mismatched spec never raises.

### `fn option(parsed: Map[String, Any], name: String) -> String | Nil`

Returns the value of an option, or `nil` when absent.

Also returns `nil` when `name` is absent or does not hold a `String`.

### `fn positional(parsed: Map[String, Any], name: String) -> String | Nil`

Returns a positional argument, or `nil` when absent.

Positionals are stored as `String` values, so this is equivalent to `option`.

### `fn usage(program: String, spec: List[String]) -> String`

Renders a deterministic usage block from the declared spec.

The first line is `Usage: <program> [options] <positional>...`; one detail line per
spec entry follows, using `--name` for flags and `--name <value>` for options.
