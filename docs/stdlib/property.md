---
title: std.property
sources:
  - std/property.lx
  - loxia/docgen.py
---

# std.property

Property-based testing with generators, shrinking and seeds.

## API

## Classes

### `class Gen[T]`

Gerador de valores com estratégia de geração e de redução (shrinking).

#### `val generate: fn(Rand) -> T`

Produz um valor a partir do gerador aleatório.

#### `val shrink: fn(T) -> List[T]`

Candidatos menores que `value` (lista vazia = não reduz).

#### `fn init(generate: fn(Rand) -> T, shrink: fn(T) -> List[T])`

Cria o gerador com as duas funções.

#### `fn sample(random: Rand) -> T`

Amostra um valor.

#### `fn smaller(value: T) -> List[T]`

Candidatos menores para o shrinking.

## Functions

### `fn forAll[T](generator: Gen[T], check: fn(T) -> Nil, runs: Int = ..., seed: Int = ...) -> Nil`

Executa `check` com `runs` valores; falha com contraexemplo reduzido e seed.

### `fn int() -> Gen[Int]`

Inteiro de 64 bits; reduz para 0 e para a metade.

### `fn intRange(min: Int, max: Int) -> Gen[Int]`

Inteiro em `[min, max]`; reduz na direção de `min`.

### `fn bool() -> Gen[Bool]`

`Bool`; reduz `true` para `false`.

### `fn float() -> Gen[Float]`

`Float` em `[0.0, 1.0)`; reduz para `0.0`.

### `fn listOf[T](element: Gen[T], maxLength: Int = ...) -> Gen[List[T]]`

Lista de `T` com tamanho em `[0, maxLength]`; reduz removendo elementos.

### `fn listOfInt(element: Gen[Int], maxLength: Int = ...) -> Gen[List[Int]]`

Lista de `Int`; alias de `listOf` mantido para compatibilidade.

### `fn listOfString(element: Gen[String], maxLength: Int = ...) -> Gen[List[String]]`

Lista de `String`; alias de `listOf` mantido para compatibilidade.

### `fn stringOf(maxLength: Int = ...) -> Gen[String]`

String de `[a-z0-9]` com tamanho em `[0, maxLength]`; reduz removendo caracteres.

### `fn oneOf[T](options: List[T]) -> Gen[T]`

Escolhe um dos valores de `options` (não vazio); reduz para o primeiro.
