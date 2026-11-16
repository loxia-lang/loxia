# ADR-0061 — L6i: enums, `Result` e `match` no backend

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0041](0041-enums-match.md), [ADR-0054](0054-l6-tuplas.md),
  [ADR-0062](0062-l6-excecoes-unwinding.md), [`../../TODO.md`](../../TODO.md) §0/§6
- **Implementação:** [`loxia_core/backend/lower_enums.py`](../../loxia_core/backend/lower_enums.py),
  [`runtime/containers.c`](../../runtime/containers.c), `tests/cases/enums.lox`,
  `tests/cases/result.lox`

## Contexto

`enums.lox` e `result.lox` são os dois maiores `PENDING` restantes. O tree-walk já tem
enums genéricos, variantes com payload, `Result` embutido e `match` exaustivo; o backend
ainda não representa nenhum deles. Diferente de `List`/`Map`, aqui não basta um valor
boxeado: `Cor.Verde`, `Shape.Circle(2.0)` e `match s { ... }` precisam de **identidade de
enum**, **dispatch por variante** e **binding de payload**.

## Decisão proposta

### Representação

- Descritor global de enum: `{id, name, variant_count, variant_names[]}` na arena.
- Valor de enum:

```text
LoxEnumValue { i64 enum_id, i64 variant, i64 payload_count, LoxValue *payload }
```

- `Cor.Verde` sem payload é um valor constante; `Shape.Circle(2.0)` chama um construtor
  gerado que boxeia os argumentos e devolve `LoxEnumValue`.
- `Result` é um enum embutido, com descritor inicializado no runtime/prelude.
- `Any` ganha a tag `ENUM`; `print`/`str`/`repr` produzem `Cor.Verde` e
  `Shape.Circle(2.0)`; igualdade é estrutural (`enum_id` + variante + payload).
- O tipo genérico do enum é apagado no runtime, como em classes genéricas; o checker
  continua responsável pela aridade/tipos do payload.

### `match`

- O checker já garante exaustividade e tipos; o backend trata `match` como expressão.
- Lowering proposto: avaliar o scrutinee uma vez, extrair `enum_id`/`variant`, emitir uma
  cadeia de comparações/blocos, bindar o payload no escopo de cada braço, `phi` no fim.
- `WildcardPattern` vira o braço default; sem wildcard, o checker garante cobertura.
- Não há HIR geral: o compilador de `match` pode ser um helper local em
  `lower_enums.py`, com blocos explícitos.

### Fora do escopo

- Métodos em enums, traits/constraints, variantes com campos nomeados, `match` estrutural
  em listas/mapas e reificação de argumentos de tipo.
- Enums como valor de função (`Enum` como namespace) além do acesso `Enum.Variante`.

## Alternativas

| Alternativa | Por que não (agora) |
| --- | --- |
| Apagar enum para tupla `(tag, payload...)` | Perde nome/print, identidade de enum e igualdade entre enums distintos; `Result` fica opaco. |
| Representar como classe/instância | Reusa vtable/descritor, mas mistura identidade de classe com enum e complica `is`/`as`/print. |
| Baixar `match` para `if`/`else` na AST | Duplica o checker e perde a garantia de avaliar o scrutinee uma vez. |
| HIR completa de patterns | Custo alto para 2 casos; o helper de `match` cobre o AST atual. |

## Consequências

- Novos símbolos de runtime e tag `Any`; nenhuma ABI existente muda.
- Casos alvo: `enums.lox`, `result.lox`.
- Dependência: nenhuma de exceções; pode entrar antes do unwinding.
