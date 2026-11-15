# ADR-0076 — `std.lists.sort`: comparador de três vias e ordenação estável

- **Status:** accepted (implementado)
- **Data:** 2026-11-14
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0072](0072-stdlib-batteries.md), [ADR-0073](0073-imports-modulos.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [ADR-0036](0036-tuplas-implementacao.md),
  [`../../TODO.md`](../../TODO.md) §13
- **Implementação:** [`std/lists.lox`](../../std/lists.lx),
  [`tests/cases/std_lists.lox`](../../tests/cases/std_lists.lx)

## Contexto

T1 precisa de `sort`, mas a linguagem não tem traits, constraints nem interfaces. As
alternativas eram:

- comparador três-vias (`fn(T,T)->Int`);
- predicado `menor que` (`fn(T,T)->Bool`);
- função de chave (`fn(T)->K`, exigiria `K: Ord`);
- objeto comparador (exigiria classe/interface).

Também era preciso decidir estabilidade, mutação e o que fazer com `sortBy`/`groupBy`.

## Decisão

### 1. Comparador de três vias

```lox
fn compareInt(a: Int, b: Int) -> Int {
  if (a < b) { return -1 }
  if (a > b) { return 1 }
  return 0
}

val ordenada = lists.sort(xs, compareInt)
```

Contrato:

- negativo: `a` vem antes de `b`;
- zero: equivalentes;
- positivo: `a` vem depois de `b`;
- comparador inconsistente é bug do programa; o runtime não tenta validar uma ordem total.

Três vias preserva igualdade explícita, funciona para qualquer `T` e é o contrato que
`qsort`/`std::sort`/`Comparator` usam. O predicado `Bool` foi recusado por não expressar
igualdade e aceitar `<=` por engano; a chave pura ficou para quando houver constraints.

### 2. Estável, retorna lista nova

- merge sort O(n log n), estável;
- não muta a entrada;
- empates preservam a ordem original;
- O(n) memória extra é aceitável com Boehm.

Não há `sortInPlace` na v1.

### 3. `sortBy` e `groupBy` ficam de fora

- `sortBy` com chave pura exige `K: Ord`; com chave + comparador é quase `sort`.
  Reavaliar com uso real.
- `groupBy` retorna `Map[K, List[T]]`, mas `Map` só aceita `String`/`Int`/`Bool` em runtime;
  sem constraints, a assinatura mentiria. Fica para depois de constraints ou de uma
  variante restrita.

### 4. Demais lacunas

`zip`, `flatten`, `flatMap`, `unique`, `chunk` e `partition` entram como funções genéricas
em Lox, sem primitiva nova. `partition` devolve `(List[T], List[T])`; `chunk` com tamanho
≤ 0 devolve lista vazia.

## Consequências

### Positivas

- API pequena e explícita, sem comparador implícito.
- Ordenação determinística e estável; o I1 pode comparar bytes.
- Nenhuma mudança de ABI/backend; o monomorphizador já cobre os genéricos.

### Negativas / custos

- O call site do comparador é mais verboso.
- Um comparador inconsistente não é detectado.
- `sortBy`/`groupBy` continuam ausentes.
- Merge sort aloca listas auxiliares.

## Alternativas recusadas

| Alternativa | Por que não |
| --- | --- |
| `fn(T,T)->Bool` | Não expressa igualdade; erros de ordem estrita são silenciosos. |
| `sortBy` só com chave | Precisa de constraints; ordem/descendente ficam escondidos. |
| Objeto comparador | Sem traits/interface vira cerimônia e superfície de backend. |
| Quicksort in-place | Instável e com pior caso; não combina com contrato determinístico. |

## Como verificar

- `tests/cases/std_lists.lox`: ordena `[3,1,2,1]`, mantém estabilidade, cobre `zip`,
  `flatten`, `flatMap`, `unique`, `chunk` e `partition`, no interpretador e no binário.
- `make check` verde; `--check` limpo.
