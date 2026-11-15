# ADR-0081 — Constraints em funções genéricas (`T: Ord + Interface`)

- **Status:** accepted (implementado: parser, checker, stdlib; backend inalterado)
- **Data:** 2026-11-15
- **Substitui:** o adiamento de constraints do [ADR-0038](0038-traits-nominais.md)
- **Relaciona:** [ADR-0027](0027-generics-t3b.md) (generics T3b),
  [ADR-0040](0040-generics-classes-desenho.md) (classes genéricas),
  [ADR-0080](0080-interfaces-nominais-implementacao.md) (interfaces nominais)

## Contexto

Generics T3b checam o corpo uma única vez e só permitem operações **universais**. Isso
impede a stdlib de expressar `max`, `min` e ordenação natural sem um comparator, e impede
o usuário de dizer “este `T` tem `area()`” ou “este `T` soma”. As interfaces nominais
(ADR-0080) já existem; falta o elo entre um parâmetro de tipo e uma capacidade.

O [ADR-0038](0038-traits-nominais.md) deixou constraints explicitamente pós-MVP. Esta é a
entrega delas, na forma mínima que resolve a dor real sem reabrir overloading.

## Decisão

### 1. Sintaxe

Bounds vêm depois do nome do parâmetro de tipo, com `:` e `+` entre constraints:

```
fn max[T: Ord] (a: T, b: T) -> T
fn soma[T: Ord + Num] (a: T, b: T) -> T
fn juntas[T: A + B, U: Nomeavel] (x: T, y: U) -> String
```

- `+` é o separador canônico (já é operador; não colide com a vírgula que separa
  parâmetros de tipo).
- Na v1, **só funções genéricas** aceitam bounds. `class C[T: Ord]` e `enum E[T: Ord]`
  falham no parser com `Constraints on class type parameters aren't supported yet.`
  (`E1005`); classes/enums continuam sem constraints.
- Nenhuma palavra-chave nova, nenhuma forma de declaração nova. O orçamento do
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) não muda.

### 2. Quais constraints existem

| Constraint | Quem satisfaz | O que libera no corpo |
| --- | --- | --- |
| `Ord` | `Int`, `Float`, `String` | `<`, `<=`, `>`, `>=` entre dois valores do mesmo `T` |
| `Num` | `Int`, `Float` | `+`, `-`, `*`, `%`, `**`, unário `-` entre dois valores do mesmo `T` |
| `Interface` | classe que implementa a interface (direta ou por herança); o próprio tipo de interface | os métodos da interface via `x.m(...)` |

- `Ord` e `Num` são **constraints embutidas**, reservadas: `interface Ord`, `class Num`
  etc. são erro de nome reservado. Elas não são interfaces e não podem ser implementadas.
- `T: Interface` usa a interface nominal do ADR-0080; não há structural typing.
- `==`/`!=` continuam universais para qualquer `T`; não precisam de bound.
- `T: Ord` **não** implica `Num`, e vice-versa. `T: Ord + Num` é permitido.
- `Any`, uniões, optionais, `List[T]`, tuplas e funções não satisfazem `Ord`/`Num`;
  `Any` também não satisfaz interface sem uma coerção explícita.

### 3. Regras no corpo

- `T: Num`: `_numeric` aceita o `TyVar`; o resultado de `+ - * % **` é o próprio `T`
  (não promove para `Float`). Os dois lados precisam ser **o mesmo** `T`.
- `T: Ord`: comparações devolvem `Bool`; os dois lados precisam ser **o mesmo** `T`.
- `/` é recusado em `TyVar` mesmo com `Num`: o resultado é sempre `Float`, então não
  preserva `T`. `//` e operadores de bits exigem `Int` concreto.
- `T: Interface`: `x.m(...)` resolve o método na interface; duas interfaces com o mesmo
  método e assinaturas diferentes são ambiguidade explícita. Campos/`this` continuam
  indisponíveis no corpo genérico.
- Métodos de interface podem receber `T` quando o parâmetro esperado é a própria
  interface (um `T: I` é atribuível a `I`).

### 4. Checagem na chamada

A inferência continua sendo por argumentos/contexto. Depois de unificar os `TyVar`:

- cada type argument é checado contra cada bound;
- se o type argument é outro `TyVar` (chamada dentro de corpo genérico), ele satisfaz o
  bound apenas se o próprio bound estiver declarado nele (`T: Ord + Num` passa em `Num`);
- a falha vira erro no token da chamada:
  `Type argument 'Bool' for 'T' doesn't satisfy constraint 'Ord'.`
- um type argument não inferido continua sendo `Can't infer type argument(s) ...`.

Sem coerção explícita, um `Any` não entra em `T: Ord`/`Num`/interface. Para `Ord`/`Num` um
`as Int`/`as Float` ainda pode ser usado antes da chamada; `as` para interface ainda não
existe, então na prática `Any` não satisfaz bound de interface. Isso mantém I4 (o checker
é a fonte única) e evita monomorfização de um tipo que não tem a operação.

### 5. Backend

Bounds são **apagados**: a monomorfização T7 continua igual. O corpo genérico é compilado
uma vez por combinação concreta de type arguments, e é aí que `T` vira `Int`, `Float`,
`String` ou uma classe. Não há vtable/itab novo para constraints.

Consequência: um programa `--check` limpo com constraints compila pelo mesmo caminho de
T7; não há `PENDING` novo nem mudança na ABI.

### 6. Stdlib

- `lists.min` e `lists.max` passam de `List[Int]` para `[T: Ord]` (mesma assinatura de
  uso para `Int`, agora também `Float`/`String`).
- novo `lists.sortNatural[T: Ord]` faz merge sort usando `<=`; `lists.sort` com comparator
  continua existindo (não há overload nem mudança de assinatura).
- `lists.sum` continua `List[Int]`: somar `Float`/`String` exigiria um zero genérico e
  outra decisão de API; não entra nesta entrega.

## Portão sintático (ADR-0066)

1. **Substituição:** não cria grafia nova para uma declaração existente; reusa `:` (já
   separador de anotação) e `+` (já operador) dentro da lista de parâmetros de tipo.
2. **Decidibilidade local:** depois de `[` e de `:` o parser sabe que está em bounds;
   `+` ali não pode ser união de tipos (união usa `|`), então não há lookahead arbitrário.
3. **Precedência:** a mudança é só na gramática de tipos; nenhum nível de expressão novo.
4. **Forma canônica:** `T: A + B`; `,` continua separando parâmetros de tipo e `where` foi
   recusado. O orçamento (28 palavras-chave, 6 formas de declaração, 19 níveis) não muda;
   só a produção `typeParameter` ganha um sufixo opcional.

## Consequências

- `max`, `min`, ordenação natural e funções de usuário sobre interfaces ficam expressivas
  sem comparator e sem casts.
- A linguagem ganha uma regra de tipo nova, mas **local e nominal**: não há inferência de
  constraints, `where`, bounds em classes ou implementações automáticas.
- `T: Ord` é resolvido por tipo concreto (`Int`, `Float`, `String`); não há
  operator overloading para classes.
- Classes genéricas com bounds continuam fora; se a dor aparecer, a extensão natural é
  aplicar o mesmo `_declare_type_params`/checagem de construção de `Box[T]`.

## Alternativas

| Alternativa | Por que não |
| --- | --- |
| Só `T: Interface`, sem `Ord`/`Num` | Não resolve a stdlib: `Int`/`String` não declaram `implements`; `max` continuaria com comparator |
| `T: A, B` | Ambíguo com a vírgula que separa parâmetros de tipo (`[T: A, U: B]`) |
| `where T: A + B` | Segunda forma de dizer a mesma coisa e mais sintaxe; `+` no parâmetro já é local |
| Traits com métodos (`Ord.compare`) | Exigiria `Self`, implementações para primitivos e overloading; custo desproporcional |
| Constraints em classes/enums já | Dobraria o escopo (validar toda anotação/construção `Box[T]`) sem dor demonstrada |
| Implícito (`Any` satisfaz tudo) | Viola I2/I4 e permitiria monomorfização de operação inexistente |

## Como Verificar

- `tests/cases/generic_constraints.lx` no corpus (`t7`) cobre `Ord`, `Num`,
  `Ord + Num`, interface, múltiplas interfaces, chamada aninhada e valor de interface;
  o diferencial roda tree-walk e nativo.
- `tests/test_checker.py` cobre bounds limpos e nove erros (constraint desconhecida,
  duplicada, operador sem bound, tipo concreto que não satisfaz, `Any`/`Bool`, método sem
  bound e bound insuficiente em chamada aninhada).
- `tests/test_parser.py` cobre `[T: Ord + Forma, U: Num]` e a recusa em classe;
  `tests/test_ast_printer.py` cobre o dump de bounds.
- `tests/cases/std_lists.lx` cobre `min`/`max` com `String`/`Float` e `sortNatural` com
  `Int`/`String`, no tree-walk e no backend.
- `make check` verde; `make bench` sem regressão (constraints não tocam caminho quente).
