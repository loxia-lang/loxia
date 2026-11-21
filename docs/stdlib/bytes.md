---
title: std.bytes
sources:
  - std/bytes.lx
  - loxia/docgen.py
---

# std.bytes

Byte buffers: incremental Builder, comparison and big/little-endian helpers.

## API

## Classes

### `class Builder`

Acumula bytes e materializa um `Bytes` no fim.

#### `fn init()`

Cria um Builder vazio.

#### `fn push(data: Bytes) -> Builder`

Anexa todos os bytes de `data` e devolve o próprio Builder.

#### `fn pushByte(value: Int) -> Builder`

Anexa um único byte 0..255 e devolve o próprio Builder.

#### `fn len() -> Int`

Número de bytes acumulados.

#### `fn build() -> Bytes`

Materializa uma cópia imutável; o Builder continua utilizável.

### `class ChunkBuilder`

Acumula blocos `Bytes` e materializa um `Bytes` por concatenação balanceada.

Para montar byte a byte use `Builder`; este evita a `List[Int]` e é indicado para
blocos grandes. O `build` copia O(n log k) no total (k = número de blocos), sem
manter uma cópia intermediária de todos os bytes; um único bloco é devolvido como
está (Bytes é imutável).

#### `fn init()`

Cria um ChunkBuilder vazio.

#### `fn push(data: Bytes) -> ChunkBuilder`

Anexa um bloco (blocos vazios são ignorados) e devolve o próprio builder.

#### `fn len() -> Int`

Número total de bytes acumulados.

#### `fn build() -> Bytes`

Materializa os blocos; o builder continua utilizável.

## Functions

### `fn compare(left: Bytes, right: Bytes) -> Int`

Compara dois `Bytes` lexicograficamente: -1, 0 ou 1.

### `fn u16be(value: Int) -> Bytes`

Encodes `value` (0..65535) as two big-endian bytes.

### `fn u16le(value: Int) -> Bytes`

Encodes `value` (0..65535) as two little-endian bytes.

### `fn u32be(value: Int) -> Bytes`

Encodes `value` (0..4294967295) as four big-endian bytes.

### `fn u32le(value: Int) -> Bytes`

Encodes `value` (0..4294967295) as four little-endian bytes.

### `fn u64be(value: Int) -> Bytes`

Encodes the 64-bit two's-complement pattern of `value` as eight big-endian bytes.

### `fn u64le(value: Int) -> Bytes`

Encodes the 64-bit two's-complement pattern of `value` as eight little-endian bytes.
