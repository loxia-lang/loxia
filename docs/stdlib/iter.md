---
title: std.iter
sources:
  - std/iter.lx
  - loxia/docgen.py
---

# std.iter

Iteration helpers (`enumerate`, `zip`, `sum`, `contains`, `Step`).

## API

## Enums

### `enum Step[T]`

Envelope para iterar elementos que podem ser `nil`: `next() -> Step[T]?` e
`match step { Step.Item(value) => ... }`; `nil` continua encerrando a iteração.

#### `Item(T)`

Um elemento; `value` pode ser `nil` quando `T` é opcional.

## Functions

### `fn enumerate[T](items: List[T]) -> List[(Int, T)]`

Pares `(índice, elemento)` na ordem da lista.

### `fn zip[A, B](left: List[A], right: List[B]) -> List[(A, B)]`

Pares dos elementos de `left` e `right`, até a menor das duas listas.

### `fn sum(items: List[Int]) -> Int`

Soma de inteiros; lista vazia devolve `0`.

### `fn sumFloat(items: List[Float]) -> Float`

Soma de floats; lista vazia devolve `0.0`.

### `fn contains[T](items: List[T], item: T) -> Bool`

`true` quando `item` está na lista (igualdade estrutural).

### `fn any[T](items: List[T], predicate: fn(T) -> Bool) -> Bool`

`true` quando algum elemento satisfaz `predicate`.

### `fn all[T](items: List[T], predicate: fn(T) -> Bool) -> Bool`

`true` quando todos os elementos satisfazem `predicate`.

### `fn find[T](items: List[T], predicate: fn(T) -> Bool) -> T | Nil`

Primeiro elemento que satisfaz `predicate`, ou `nil`.
