# TIPOS — pendências de tipos

Só o que ainda está **pendente**. O comportamento atual está em [`docs/spec/`](docs/spec/);
decisões fechadas, em [`docs/decisoes.md`](docs/decisoes.md) e nos [ADRs](docs/adr/). Este
arquivo não descreve o que já funciona.

## 1. Implementação pendente

### 1.1 M5 — tipos v2

- **T6a (restante)** — métodos genéricos (`fn map[U]`) e herança de `Box[Int]`; o MVP de
  classes genéricas está feito ([ADR-0040](docs/adr/0040-generics-classes-desenho.md)).
- **T6c** — `match`/enums e exaustividade.
- **T6b** — traits nominais (`implements`, métodos default) e constraints: decididos,
  **pós-MVP** ([ADR-0038](docs/adr/0038-traits-nominais.md)).

T6a/T6c fecham o M5; traits não bloqueiam o L4.

### 1.2 Checker

- **Narrowing**: merge em CFG/aliasing; chamada que muta campo não invalida
  ([ADR-0032](docs/adr/0032-narrowing-campos-indices.md)).
- **Função genérica como valor** (T3b só permite chamada).

### 1.3 Tipos

- **`Result[T, E]`** como enum/ADT, junto de T6c; `Option` já é `T?`
  ([ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md)).
- **Aliases `type`**: transparentes, sem generics, P3
  ([ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md)).

### 1.4 Backend

- **T7** — monomorfização.
- **Layout de tupla** (L6) e **chamada via trait** (vtable/type-id, L6).
- **`Any` boxeado** (pós-MVP).
