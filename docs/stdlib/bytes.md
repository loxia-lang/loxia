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

### `class BytesError`

Falha de uma leitura: a fatia pedida não cabe no buffer.

`kind` é estável (`outOfBounds`); `offset`, `wanted` e `length` são os números que o
chamador precisa para dizer *onde* o parse saiu do trilho. Sem caminho nem locale.

#### `val kind: String`

Token estável: `outOfBounds`.

#### `val offset: Int`

Posição pedida.

#### `val wanted: Int`

Quantos bytes a leitura precisa.

#### `val length: Int`

Tamanho total do buffer.

#### `val message: String`

Detalhe determinístico, pronto para log.

#### `fn init(offset: Int, wanted: Int, length: Int)`

Cria a falha com a posição pedida, o tamanho necessário e o total do buffer.

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

### `class Builder`

Acumula bytes e materializa um `Bytes` no fim.

Blocos (`push`) ficam em um `ChunkBuilder`, então o custo é por bloco, não por byte;
bytes avulsos (`pushByte`) ficam em uma `List[Int]` pendente, materializada no próximo
`push` ou no `build`. O `build` copia O(n log k) (k = blocos + pendente) e não mantém
cópia intermediária de todos os bytes.

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

### `fn readU16beResult(data: Bytes, offset: Int) -> Result[Int, BytesError]`

Reads a big-endian `u16` at `offset`, preserving the cause of a short buffer.

### `fn readU16be(data: Bytes, offset: Int) -> Int | Nil`

Reads a big-endian `u16` at `offset`; `nil` if the two bytes are out of bounds.

Ergonomic shell over `readU16beResult` (ADR-0135): the cause is dropped, not lost.

### `fn readU16leResult(data: Bytes, offset: Int) -> Result[Int, BytesError]`

Reads a little-endian `u16` at `offset`, preserving the cause of a short buffer.

### `fn readU16le(data: Bytes, offset: Int) -> Int | Nil`

Reads a little-endian `u16` at `offset`; `nil` if the two bytes are out of bounds.

Ergonomic shell over `readU16leResult` (ADR-0135).

### `fn readU32beResult(data: Bytes, offset: Int) -> Result[Int, BytesError]`

Reads a big-endian `u32` at `offset`, preserving the cause of a short buffer.

### `fn readU32be(data: Bytes, offset: Int) -> Int | Nil`

Reads a big-endian `u32` at `offset`; `nil` if the four bytes are out of bounds.

Ergonomic shell over `readU32beResult` (ADR-0135).

### `fn readU32leResult(data: Bytes, offset: Int) -> Result[Int, BytesError]`

Reads a little-endian `u32` at `offset`, preserving the cause of a short buffer.

### `fn readU32le(data: Bytes, offset: Int) -> Int | Nil`

Reads a little-endian `u32` at `offset`; `nil` if the four bytes are out of bounds.

Ergonomic shell over `readU32leResult` (ADR-0135).

### `fn readU64beResult(data: Bytes, offset: Int) -> Result[Int, BytesError]`

Reads a big-endian `u64` at `offset`, preserving the cause of a short buffer.

The result is the 64-bit pattern in an `Int`: a value with the high bit set
appears negative, exactly like `u64be`.

### `fn readU64be(data: Bytes, offset: Int) -> Int | Nil`

Reads a big-endian `u64` at `offset`; `nil` if the eight bytes are out of bounds.

The result is the 64-bit pattern in an `Int`: a value with the high bit set
appears negative, exactly like `u64be`. Ergonomic shell over `readU64beResult`
(ADR-0135).

### `fn readU64leResult(data: Bytes, offset: Int) -> Result[Int, BytesError]`

Reads a little-endian `u64` at `offset`, preserving the cause of a short buffer.

The high bit appears as a negative `Int`, exactly like `u64le`.

### `fn readU64le(data: Bytes, offset: Int) -> Int | Nil`

Reads a little-endian `u64` at `offset`; `nil` if the eight bytes are out of bounds.

The high bit appears as a negative `Int`, exactly like `u64le`. Ergonomic shell
over `readU64leResult` (ADR-0135).
