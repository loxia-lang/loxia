---
title: std.collections
sources:
  - std/collections.lx
  - loxia/docgen.py
---

# std.collections

Stack, Queue, Deque and PriorityQueue.

## API

## Classes

### `class Stack[T]`

Pilha LIFO genérica.

#### `var items: List[T]`

Elementos do topo para a base.

#### `fn init()`

Cria uma pilha vazia.

#### `fn push(value: T) -> Nil`

Empilha `value`.

#### `fn pop() -> T | Nil`

Desempilha o topo, ou `nil` se vazia.

#### `fn peek() -> T | Nil`

Espia o topo sem desempilhar.

#### `fn len() -> Int`

Número de elementos.

#### `fn isEmpty() -> Bool`

`true` quando vazia.

#### `fn toList() -> List[T]`

Cópia dos elementos do topo para a base.

#### `fn clear() -> Nil`

Remove todos os elementos.

### `class Queue[T]`

Fila FIFO genérica.

#### `var items: List[T]`

Elementos na ordem de chegada (com lixo antes de `head`).

#### `var head: Int`

Índice do próximo elemento a sair.

#### `fn init()`

Cria uma fila vazia.

#### `fn enqueue(value: T) -> Nil`

Enfileira `value`.

#### `fn dequeue() -> T | Nil`

Desenfileira o mais antigo, ou `nil` se vazia.

#### `fn peek() -> T | Nil`

Espia o próximo sem remover.

#### `fn len() -> Int`

Número de elementos vivos.

#### `fn isEmpty() -> Bool`

`true` quando vazia.

#### `fn toList() -> List[T]`

Cópia dos elementos na ordem de saída.

#### `fn clear() -> Nil`

Remove todos os elementos.

### `class Deque[T]`

Deque (fila de duas pontas) genérica.

#### `var front: List[T]`

Metade da frente, com o topo no fim.

#### `var back: List[T]`

Metade de trás, com o topo no fim.

#### `fn init()`

Cria um deque vazio.

#### `fn pushFront(value: T) -> Nil`

Insere no início.

#### `fn pushBack(value: T) -> Nil`

Insere no fim.

#### `fn popFront() -> T | Nil`

Remove do início, ou `nil` se vazio.

#### `fn popBack() -> T | Nil`

Remove do fim, ou `nil` se vazio.

#### `fn peekFront() -> T | Nil`

Espia o início.

#### `fn peekBack() -> T | Nil`

Espia o fim.

#### `fn len() -> Int`

Número de elementos.

#### `fn isEmpty() -> Bool`

`true` quando vazio.

#### `fn toList() -> List[T]`

Cópia na ordem do início para o fim.

#### `fn clear() -> Nil`

Remove todos os elementos.

### `class PriorityQueue[T]`

Fila de prioridade (min-heap) com comparador explícito.

#### `var items: List[T]`

Heap em ordem parcial.

#### `val less: fn(T, T) -> Bool`

`true` quando `a` deve sair antes de `b`.

#### `fn init(less: fn(T, T) -> Bool)`

Cria a fila vazia com o comparador `less`.

#### `fn push(value: T) -> Nil`

Insere `value`.

#### `fn pop() -> T | Nil`

Remove o menor, ou `nil` se vazia.

#### `fn peek() -> T | Nil`

Espia o menor sem remover.

#### `fn len() -> Int`

Número de elementos.

#### `fn isEmpty() -> Bool`

`true` quando vazia.

#### `fn toList() -> List[T]`

Cópia ordenada do menor para o maior.

#### `fn clear() -> Nil`

Remove todos os elementos.
