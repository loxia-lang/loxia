---
title: std.proc
sources:
  - std/proc.lx
  - loxia/docgen.py
---

# std.proc

Processes, streams and `poll` (POSIX, ambient).

## API

## Classes

### `class Stream`

Fluxo de bytes de um processo (`stdin`, `stdout` ou `stderr`).

#### `val id: Int`

Handle do stream em `proc.*`.

#### `fn init(id: Int)`

Cria a casca em volta de um handle já existente.

#### `fn read(n: Int) -> String | Nil`

Lê até `n` bytes; `nil` no fim do stream. Sempre em fronteira de UTF-8.

#### `fn write(text: String) -> Bool`

Escreve todo o texto; `false` se o outro lado fechou.

#### `fn close() -> Nil`

Fecha o descritor; usar o stream depois disso é erro.

### `class Process`

Processo filho com os três canais em pipes.

#### `val id: Int`

Handle do processo em `proc.*`.

#### `val stdin: Stream`

Canal de entrada do filho.

#### `val stdout: Stream`

Canal de saída do filho.

#### `val stderr: Stream`

Canal de erro do filho.

#### `fn init(id: Int)`

Cria a casca em volta de um processo já iniciado.

#### `fn wait() -> Int`

Espera o processo terminar; código negativo significa sinal.

#### `fn kill() -> Bool`

Mata com `SIGKILL`; `false` se o processo já tinha saído.

#### `fn close() -> Nil`

Fecha os canais e libera o handle (não mata um processo em execução).

### `class Output`

Saída capturada por `run`.

#### `val code: Int`

Código de saída (negativo quando o filho morreu por sinal).

#### `val stdout: String`

Tudo o que o filho escreveu em stdout.

#### `val stderr: String`

Tudo o que o filho escreveu em stderr.

#### `fn init(code: Int, stdout: String, stderr: String)`

Monta o resultado de uma execução.

## Functions

### `fn spawn(argv: List[String]) -> Process | Nil`

Inicia `argv` (sem shell) com pipes nos três canais; `nil` se não conseguiu.

### `fn run(argv: List[String], stdin: String = ..., timeoutMs: Int = ...) -> Output | Nil`

Roda `argv` até o fim e devolve código e saída; `nil` em falha ou timeout.

`stdin` é escrito antes do primeiro `poll` (limite prático: o buffer do pipe,
~64 KiB; texto maior pode bloquear se o filho não ler). `timeoutMs > 0` mata o
processo e devolve `nil`. Sem shell e sem interpolação de comando.
