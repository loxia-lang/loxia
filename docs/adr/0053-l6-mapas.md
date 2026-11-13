# ADR-0053 — L6c: mapas boxeados no runtime

- **Status:** accepted (Map implementado; tuplas/Any/enums/exceções pendentes)
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0052](0052-l6-listas.md), [ADR-0051](0051-l6-range-for-in-escalares.md)
- **Implementação:** [`src/backend/lower_containers.py`](../../src/backend/lower_containers.py),
  [`runtime/runtime.c`](../../runtime/runtime.c)

## Decisão

- `Map` é `LoxMap {count, capacity, entries, version}` na arena; entradas guardam
  `LoxValue` de chave/valor.
- Chaves `Bool`/`Int`/`String` usam a tag para separar `true` de `1`; igualdade de
  strings é por conteúdo.
- Ordem de inserção preservada; atualizar valor mantém a posição.
- `m[k]` ausente é panic; `m.get(k)` devolve `nil`; `m.remove(k)` ausente é panic.
- `keys`/`values` devolvem `List`; `for-in` itera chaves em ordem.
- Igualdade é independente de ordem e estrutural; ciclos usam identidade/limite.
- `print`/`str`/`repr` formatam `{chave: valor}` com strings citadas e ciclos `{...}`.

## Consequências

Casos promovidos: `map_literal`, `map_methods`, `map_keys`, `map_iteration`,
`map_equality`, `map_stringify` e `map_cycle`; `interpolation` também passou a compilar.
