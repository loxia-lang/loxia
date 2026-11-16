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

Logger que escreve em stderr; `minimum` filtra os níveis mais baixos.

#### `var minimum: Level`

Menor nível que será escrito.

#### `fn init(minimum: Level | Nil = ...)`

Cria o logger; sem argumento, o mínimo é `Level.Info`.

#### `fn setMinimum(level: Level) -> Nil`

Troca o nível mínimo.

#### `fn log(level: Level, message: String) -> Nil`

Escreve `[NÍVEL] mensagem` em stderr se `level >= minimum`.

#### `fn debug(message: String) -> Nil`

Loga em `Debug`.

#### `fn info(message: String) -> Nil`

Loga em `Info`.

#### `fn warn(message: String) -> Nil`

Loga em `Warn`.

#### `fn error(message: String) -> Nil`

Loga em `Error`.

## Enums

### `enum Level`

Nível de log; a ordem é `Debug < Info < Warn < Error`.

#### `Debug`

Detalhe de diagnóstico.

#### `Info`

Evento normal.

#### `Warn`

Situação suspeita.

#### `Error`

Falha.
