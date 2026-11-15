# TIPOS — pendências de tipos

Só o que ainda está **pendente**. O comportamento atual está em [`docs/spec/`](docs/spec/);
decisões fechadas, em [`docs/decisoes.md`](docs/decisoes.md) e nos [ADRs](docs/adr/). Este
arquivo não descreve o que já funciona.

## 1. Implementação pendente

### 1.1 M5 — fechado

T6a/T6c foram implementados; restam no pós-MVP:

- **T6a (restante)** — métodos genéricos (`fn map[U]`), herança de `Box[Int]` e `is/as`
  reificado: **adiados** por decisão ([TODO.md](TODO.md) §10;
  [ADR-0040](docs/adr/0040-generics-classes-desenho.md)).
- **T6b** — interfaces nominais (item "traits" do Lox2): `implements`, métodos default e
  constraints. O modelo está no [ADR-0038](docs/adr/0038-traits-nominais.md); a v1 das
  interfaces no [ADR-0080](docs/adr/0080-interfaces-nominais-implementacao.md) e as
  constraints de função (`T: Ord + Num + Interface`) no
  [ADR-0081](docs/adr/0081-constraints-generics.md) — tree-walk/checker e backend
  implementados. Falta constraints em classes/enums e interfaces genéricas.

### 1.2 Checker

- **Narrowing**: invalidação em chamada/atribuição a campo/índice implementada
  ([ADR-0045](docs/adr/0045-narrowing-representacao.md)); resta CFG/aliasing fino e `var`
  capturado por closure ([ADR-0032](docs/adr/0032-narrowing-campos-indices.md)).
- **Função genérica como valor** (T3b só permite chamada).
- **Enum genérico em lambda/match**: `fn(x) => Result.Ok(x)` não infere `U`/`E`; exige
  função nomeada com retorno anotado. (O `T?` contra `Int?` já unifica `T = Int`.)

### 1.3 L5 — desenho fechado, backend pendente

- **Layout** de classe/campos/vtable/init em
  [ADR-0043](docs/adr/0043-layout-l5-classes.md).
- **Identidade** de classe por objeto em `is`/`as`/`except`
  ([ADR-0044](docs/adr/0044-identidade-classe.md)).
- **Representação** × narrowing: `storage_types` publicado, lowering usa o declarado
  ([ADR-0045](docs/adr/0045-narrowing-representacao.md)).

### 1.4 Tipos

- **Aliases `type`**: transparentes, sem generics, implementados no [ADR-0084](docs/adr/0084-type-alias.md)
  ([ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md)).
- **Padrões avançados** de `match` (literais/nil, guards, aninhamento, `|`) e enum genérico
  com variante nula; backend L6 ([ADR-0041](docs/adr/0041-enums-match.md)).

### 1.5 Backend

- **L2.5** — `T?` escalar/referência e `var x;` (`variables.lx` está `PENDING` l2);
  desbloqueia campos opcionais do L5.
- **T7** — monomorfização.
- **Layout de tupla** (L6) e **chamada via interface** (vtable/type-id, L6).
- **`Any` boxeado** (pós-MVP).
