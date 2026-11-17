---
title: std.collections
sources:
  - std/collections.lx
  - loxia/docgen.py
---

# std.collections

Stack, Queue, Deque and PriorityQueue, backed by lists.

## API

## Classes

### `class Stack[T]`

Generic LIFO stack backed by a list.

#### `var items: List[T]`

Elements from bottom to top.

#### `fn init()`

Creates an empty stack.

#### `fn push(value: T) -> Nil`

Pushes `value` onto the top.

#### `fn pop() -> T | Nil`

Removes and returns the top, or `nil` when the stack is empty.

#### `fn peek() -> T | Nil`

Returns the top without removing it, or `nil` when the stack is empty.

#### `fn len() -> Int`

Returns the number of elements.

#### `fn isEmpty() -> Bool`

Returns `true` when the stack has no elements.

#### `fn toList() -> List[T]`

Returns a copy of the elements from top to bottom.

#### `fn clear() -> Nil`

Removes every element.

### `class Queue[T]`

Generic FIFO queue backed by a list and a moving head index.

#### `var items: List[T]`

Elements in arrival order; slots before `head` are already consumed.

#### `var head: Int`

Index of the next element to dequeue.

#### `fn init()`

Creates an empty queue.

#### `fn enqueue(value: T) -> Nil`

Adds `value` at the back of the queue.

#### `fn dequeue() -> T | Nil`

Removes and returns the oldest element, or `nil` when the queue is empty.

#### `fn peek() -> T | Nil`

Returns the oldest element without removing it, or `nil` when empty.

#### `fn len() -> Int`

Returns the number of live elements; consumed slots are not counted.

#### `fn isEmpty() -> Bool`

Returns `true` when the queue has no elements.

#### `fn toList() -> List[T]`

Returns a copy of the elements in dequeue order.

#### `fn clear() -> Nil`

Removes every element.

### `class Deque[T]`

Generic double-ended queue backed by two lists.

#### `var front: List[T]`

Front half, with the front element at the end of the list.

#### `var back: List[T]`

Back half, with the back element at the end of the list.

#### `fn init()`

Creates an empty deque.

#### `fn pushFront(value: T) -> Nil`

Inserts `value` at the front.

#### `fn pushBack(value: T) -> Nil`

Inserts `value` at the back.

#### `fn popFront() -> T | Nil`

Removes and returns the front element, or `nil` when empty.

#### `fn popBack() -> T | Nil`

Removes and returns the back element, or `nil` when empty.

#### `fn peekFront() -> T | Nil`

Returns the front element without removing it, or `nil` when empty.

#### `fn peekBack() -> T | Nil`

Returns the back element without removing it, or `nil` when empty.

#### `fn len() -> Int`

Returns the number of elements.

#### `fn isEmpty() -> Bool`

Returns `true` when the deque has no elements.

#### `fn toList() -> List[T]`

Returns a copy from front to back.

#### `fn clear() -> Nil`

Removes every element.

### `class PriorityQueue[T]`

Min-priority queue backed by a binary heap and an explicit comparator.

#### `var items: List[T]`

Heap array in partial order.

#### `val less: fn(T, T) -> Bool`

Comparator: returns `true` when `a` must leave before `b`.

#### `fn init(less: fn(T, T) -> Bool)`

Creates an empty queue; `less` defines the priority order.

#### `fn push(value: T) -> Nil`

Inserts `value` and restores the heap order.

#### `fn pop() -> T | Nil`

Removes and returns the highest-priority (least) element, or `nil` when empty.

#### `fn peek() -> T | Nil`

Returns the highest-priority element without removing it, or `nil` when empty.

#### `fn len() -> Int`

Returns the number of elements.

#### `fn isEmpty() -> Bool`

Returns `true` when the priority queue has no elements.

#### `fn toList() -> List[T]`

Returns a copy in priority order without modifying the queue.

#### `fn clear() -> Nil`

Removes every element.
