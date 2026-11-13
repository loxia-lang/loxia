# ADR-0052 — L6b: listas boxeadas no runtime

- **Status:** accepted (List implementada; Map/tuplas/Any/enums/exceções pendentes)
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0031](0031-backend-nativo.md), [ADR-0051](0051-l6-range-for-in-escalares.md),
  [`../../TODO.md`](../../TODO.md) §6
- **Implementação:** [`src/backend/lower_containers.py`](../../src/backend/lower_containers.py),
  [`runtime/runtime.c`](../../runtime/runtime.c)

## Decisão

- `List` é um ponteiro para `LoxList {count, capacity, items, version}` na arena.
- Elementos são `LoxValue {tag, payload}`; a tag usa os mesmos valores de `Any`.
- O backend conhece o tipo do elemento pelo checker; literais, índice, `push`, `pop`,
  `len`, `for-in`, `print`/`str`/`repr` e igualdade estrutural usam esse tipo para
  (des)boxear.
- Listas literais guardam o tipo runtime de cada elemento; `[1, 2.0]` continua
  imprimindo `[1, 2.0]` e a igualdade promove numericamente (`[1] == [1.0]`).
- Igualdade de listas é estrutural; auto-referência curto-circuita por identidade
  (`xs == xs`) e o formatador usa uma pilha de listas ativas para produzir `[[...]]`.
- `for-in` sobre lista lê por índice e desboxa cada elemento.

## Limitações

- `Map`, tuplas e `List[Any]` completo (casts/igualdade com `Any`) seguem pendentes.
- `map`/`filter` genéricos ainda esbarram na lambda sem `FnTy` concreto no backend; é a
  próxima correção de integração T7×L6.
- A representação é boxeada por elemento; desboxar listas monomorfizadas é otimização
  posterior, não requisito de correção.

## Consequências

Casos promovidos: `list_literal`, `list_index`, `list_methods`, `list_iteration`,
`list_equality`, `list_stringify` e `list_cycle`.
