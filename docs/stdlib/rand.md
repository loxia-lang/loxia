---
title: std.rand
sources:
  - std/rand.lx
  - loxia/docgen.py
---

# std.rand

Deterministic PRNG with an explicit seed.

## API

## Classes

### `class Rand`

Gerador xorshift64*; a mesma semente produz a mesma sequência.

#### `var state: Int`

Estado interno (nunca zero).

#### `fn init(seed: Int)`

Cria o gerador; `seed = 0` vira a constante padrão do xorshift.

#### `fn reseed(seed: Int) -> Nil`

Reinicia a sequência com `seed`.

#### `fn nextInt() -> Int`

Próximo valor bruto de 64 bits (pode ser negativo).

#### `fn int(min: Int, max: Int) -> Int`

Inteiro em `[min, max]` (inclusivo); erro se `min > max` ou range grande demais.

#### `fn float() -> Float`

Float em `[0.0, 1.0)` com 53 bits de mantissa.

#### `fn bool() -> Bool`

`true` ou `false` com probabilidade 1/2.

## Functions

### `fn shuffle[T](items: List[T], generator: Rand) -> Nil`

Embaralha `items` in-place (Fisher-Yates) usando `generator`.
