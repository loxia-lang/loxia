# ADR-0055 — L6e: `Any` com unbox, `is`/`as`, igualdade e `for-in` de tupla

- **Status:** accepted (primeira fatia de `Any`; enums/exceções e alguns casos de tupla pendentes)

> **Atualizado por** [ADR-0144](0144-any-dinamico-exige-estreitamento.md): acesso a membro, escrita, chamada e índice em `Any` passou a exigir estreitamento (`is`/`as`) no checker.
- **Data:** 2026-11-13
- **Relacionados:** [ADR-0049](0049-any-boxeado-spike-l6.md), [ADR-0054](0054-l6-tuplas.md)
- **Implementação:** [`loxia_core/backend/lower_class_codegen.py`](../../loxia_core/backend/lower_class_codegen.py),
  [`loxia_core/backend/lower_containers.py`](../../loxia_core/backend/lower_containers.py),
  [`runtime/objects.c`](../../runtime/objects.c)

## Decisão

- `Any` continua `{i64 tag, i64 payload}`; `as T` faz unbox checado pelo tipo de destino.
- `is T` para `Any` compara a tag; classes usam a cadeia de descritores e tuplas de
  aridade 2 comparam as tags dos elementos (`lox_tuple_is2`).
- Igualdade com `Any` usa `lox_any_equal`, que reutiliza a igualdade estrutural de
  listas/mapas/tuplas e promove números.
- `for-in` sobre tupla materializa cada elemento como `Any`, permitindo tuplas
  heterogêneas sem um slot monomórfico.
- Índice de `Any` estreitado usa o tipo de fluxo do checker para fazer unbox antes do
  acesso.

## Limitações

- `Any` com enums/exceções, `as`/`is` de tuplas de aridade > 2 e narrowing completo
  continuam pendentes; `tuple_iteration` ainda não foi promovido.
