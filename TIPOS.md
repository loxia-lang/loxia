# TIPOS — pendências de tipos

Só o que ainda está **aberto ou pendente**. O comportamento atual está em
[`docs/spec/`](docs/spec/); decisões fechadas, em [`docs/decisoes.md`](docs/decisoes.md) e
nos [ADRs](docs/adr/). Este arquivo não descreve o que já funciona.

## 1. Decisões em aberto

| Id | Decisão | Opções | Recomendação |
| --- | --- | --- | --- |
| `D-2` | sufixos de literal (`1i64`/`1.0f32`) | ter / não ter | não ter enquanto `Int` for i64 |
| — | `Float` como chave de `Map` | manter fora / canonicalizar `1 == 1.0` | fora enquanto não houver canonicalização |
| — | `Option`/`Result` explícitos | alias de `T?` / tipo próprio / não ter | `Option` = `T?`; `Result` para erro recuperável, sem `throw` duplicando |
| — | `type` alias | ter / não ter | pós-MVP |

## 2. Pendente de implementação

### 2.1 M5 — tipos v2

- **T6a** — classes/métodos genéricos.
- **T6c** — `match`/enums e exaustividade.
- **T6b** — traits nominais (`implements`, métodos default) e constraints: decididos,
  **pós-MVP** ([ADR-0038](docs/adr/0038-traits-nominais.md)).

T6a/T6c fecham o M5; traits não bloqueiam o L4.

### 2.2 Checker

- **Narrowing**: merge em CFG/aliasing; chamada que muta campo não invalida
  ([ADR-0032](docs/adr/0032-narrowing-campos-indices.md)).
- **Função genérica como valor** (T3b só permite chamada).
- **`Never`/`throw`**: `throw` público e interação com o fluxo (pós-1.0).

### 2.3 Tipos

- **Tuplas**: `for x in t`, `is (A, B)`/`as (A, B)` e backend (L6)
  ([ADR-0036](docs/adr/0036-tuplas-implementacao.md)).
- **Enum/ADT e `Result`/`Option`**: dependem de T6c e da decisão do §1.
- **Aliases `type`**: pós-MVP.

### 2.4 Backend

- **T7** — monomorfização.
- **Layout de tupla** (L6) e **chamada via trait** (vtable/type-id, L6).
- **`Any` boxeado** (pós-MVP).
