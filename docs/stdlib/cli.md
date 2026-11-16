---
title: std.cli
sources:
  - std/cli.lx
  - loxia/docgen.py
---

# std.cli

Deterministic command-line parsing.

## API

## Functions

### `fn parse(args: List[String], spec: List[String]) -> Map[String, Any]`

Parses command-line arguments against a declarative spec into a map.

### `fn flag(parsed: Map[String, Any], name: String) -> Bool`

Returns whether a boolean flag was present.

### `fn option(parsed: Map[String, Any], name: String) -> String | Nil`

Returns the value of an option, or `nil` when absent.

### `fn positional(parsed: Map[String, Any], name: String) -> String | Nil`

Returns a positional argument, or `nil` when absent.

### `fn usage(program: String, spec: List[String]) -> String`

Renders a usage line from the declared spec.
