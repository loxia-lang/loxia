---
title: std.test
sources:
  - std/test.lx
  - loxia/docgen.py
---

# std.test

Mini-harness de testes (TAP, `Suite`, matchers, `Recorder`).

## API

## Classes

### `class TestFailure(Exception)`

Falha de teste (separada de `RuntimeError`, que é bug de infraestrutura).

#### `fn init(message: String)`

Cria a falha com a mensagem exibida no relatório.

### `class Skip(Exception)`

Teste pulado de propósito; o runner conta como `skip`, não como falha.

#### `fn init(reason: String)`

Cria o skip com o motivo.

### `class Suite`

Suite de testes: `describe`, `it`, `report` e `done`.

#### `var total: Int`

Total de testes executados (filtrados não contam).

#### `var passed: Int`

Testes que passaram.

#### `var failed: Int`

Testes que falharam.

#### `var skipped: Int`

Testes pulados com `skip`.

#### `var prefixes: List[String]`

Prefixos abertos por `describe`.

#### `var filter: String`

Filtro de `--filter=` vindo dos argumentos do script.

#### `var only: String`

Nome exato de `--only=` vindo dos argumentos do script.

#### `var skipRequested: Bool`

Marca que `skip` foi chamado no teste atual.

#### `fn init()`

Cria uma suite vazia e lê `--filter=`/`--only=` de `args()`.

#### `fn describe(name: String, body: fn() -> Nil) -> Nil`

Abre um grupo; o nome entra no nome de cada `it`.

#### `fn it(name: String, body: fn() -> Nil) -> Nil`

Executa um teste agora e imprime `ok`/`not ok` em TAP.

#### `fn skip(reason: String) -> Nil`

Pula o teste atual com `reason` (o `it` conta como skip, não falha).

#### `fn report() -> Int`

Imprime plano e resumo em TAP; devolve 0 (tudo ok) ou 1 (alguma falha).

#### `fn done() -> Nil`

Atalho de `report()` que encerra o processo com o código de saída.

### `class Expectation[T]`

Asserção de igualdade para um valor concreto (escalar, string, lista, mapa, tupla).

#### `val value: T`

Valor observado.

#### `fn init(value: T)`

Envolve o valor observado.

#### `fn toBe(other: T) -> Nil`

Falha quando `value != other`.

#### `fn notToBe(other: T) -> Nil`

Falha quando `value == other`.

### `class ListExpectation[T]`

Asserção sobre os elementos de uma lista.

#### `val items: List[T]`

Lista observada.

#### `fn init(items: List[T])`

Envolve a lista observada.

#### `fn toContain(item: T) -> Nil`

Falha quando `item` não está na lista (igualdade estrutural).

### `class StringExpectation`

Asserção sobre o conteúdo de uma string.

#### `val text: String`

Texto observado.

#### `fn init(text: String)`

Envolve o texto observado.

#### `fn contains(needle: String) -> Nil`

Falha quando `text` não contém `needle`.

### `class Recorder`

Registra chamadas de um spy/fake: `record`, `count`, `order`, `clear`.

#### `val calls: List[String]`

Chamadas na ordem em que foram registradas.

#### `fn init()`

Cria um gravador vazio.

#### `fn record(name: String) -> Nil`

Registra uma chamada pelo nome.

#### `fn count(name: String) -> Int`

Quantas vezes `name` foi registrado.

#### `fn order() -> List[String]`

Cópia das chamadas na ordem registrada.

#### `fn clear() -> Nil`

Esvazia o registro.

## Functions

### `fn fail(message: String) -> Nil`

Falha o teste atual com `message`.

### `fn expect[T](value: T) -> Expectation[T]`

Envolve um valor concreto para `toBe`/`notToBe`.

### `fn expectGt[T](actual: T, expected: T) -> Nil`

Falha quando `actual <= expected` (ordem natural de `T: Ord`).

### `fn expectGe[T](actual: T, expected: T) -> Nil`

Falha quando `actual < expected`.

### `fn expectLt[T](actual: T, expected: T) -> Nil`

Falha quando `actual >= expected`.

### `fn expectLe[T](actual: T, expected: T) -> Nil`

Falha quando `actual > expected`.

### `fn expectNil[T](value: T | Nil) -> Nil`

Falha quando `value` não é `nil`. Passe um opcional tipado (`val x: Int? = nil`);
`expectNil(nil)` é opcional aninhado e o backend recusa.

### `fn expectNotNil[T](value: T | Nil) -> T`

Falha quando `value` é `nil`; devolve o valor estreitado.

### `fn expectList[T](items: List[T]) -> ListExpectation[T]`

Envolve uma lista para `toContain`.

### `fn expectString(text: String) -> StringExpectation`

Envolve uma string para `contains`.

### `fn expectRaise(body: fn() -> Nil) -> String`

Executa `body` e devolve a mensagem da exceção; falha se nada foi lançado.
