---
title: std.log
sources:
  - std/log.lx
  - loxia/docgen.py
---

# std.log

Leveled logging to stderr, without timestamps.

## API

## Classes

### `class Logger`

Logger that writes to stderr and filters out levels below `minimum`.

#### `var minimum: Level`

Lowest level that will be written.

#### `fn init(minimum: Level | Nil = ...)`

Creates a logger; without an argument the minimum is `Level.Info`.

Passing `nil` selects the same default.

#### `fn setMinimum(level: Level) -> Nil`

Changes the minimum level; lower levels are suppressed from then on.

#### `fn log(level: Level, message: String) -> Nil`

Writes `[LEVEL] message` to stderr when `level >= minimum`.

Filtering never raises and does not affect stdout or the exit code.

#### `fn debug(message: String) -> Nil`

Logs at `Debug`.

#### `fn info(message: String) -> Nil`

Logs at `Info`.

#### `fn warn(message: String) -> Nil`

Logs at `Warn`.

#### `fn error(message: String) -> Nil`

Logs at `Error`.

## Enums

### `enum Level`

Log level; the order is `Debug < Info < Warn < Error`.

#### `Debug`

Diagnostic detail.

#### `Info`

Normal event.

#### `Warn`

Suspicious situation.

#### `Error`

Failure.
