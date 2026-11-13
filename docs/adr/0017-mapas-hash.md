# ADR-0017 — Mapas: `Map[K, V]`, literal `{ k: v }` e chave ausente explícita

- **Status:** accepted
- **Data:** 2026-11-11
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0005](0005-val-var-imutabilidade.md),
  [ADR-0006](0006-int-float-separados.md), [ADR-0007](0007-ranges-e-iteracao.md),
  [ADR-0010](0010-tipagem-estatica.md), [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0015](0015-listas-tipadas.md), [`../spec/semantica.md`](../spec/semantica.md),
  [`TODO.md`](../../TODO.md) §1 e §11
- **Implementação:** [`src/execution/lox_map.py`](../../src/execution/lox_map.py),
  [`src/execution/interpreter.py`](../../src/execution/interpreter.py), [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`docs/spec/semantica.md`](../spec/semantica.md),
  [`tests/cases/map_*.lox`](../../tests/cases)

## Contexto

`List[T]` já existe, mas o caso de uso mais comum depois de uma sequência — associar uma
chave a um valor — ainda não tem runtime. `Map[K, V]` existe **só como anotação**: o parser
resolve `Map[String, Int]` para `MapTy`, o checker aceita, mas não há literal, indexação,
métodos, igualdade nem iteração. A spec prometia `Map` "quando existir" e o `TODO.md` §1
listava mapas como P2.

A decisão não é só "implementar um dicionário". Há quatro perguntas que mudam a linguagem:

1. **Nome** — `Map`, `Dict`, `Dictionary`, `HashMap` ou `Table`?
2. **Literal** — `{ k: v }` convive com o `{` de bloco; `["k": v]` (Lox2) evita o bloco,
   mas confunde com lista e não tem literal vazio.
3. **Chave ausente** — erro, `nil` (Lox2/JS) ou `V?` sempre?
4. **Chaves e igualdade** — `Float` como chave, `Bool` colidindo com `0`/`1`,
   igualdade por identidade vs estrutural.

## Decisão

### O tipo se chama `Map[K, V]`

`Map` é o nome do **ADT**, não da implementação. Isso mantém a simetria com `List` (que
também não se chama `ArrayList`) e com `Int`, `String` e `Bool`. O nome `Dict` foi
considerado, mas quebraria a simetria `List`/`Map` já documentada; `Dictionary` é longo em
anotações aninhadas; `HashMap` vaza a implementação e sugere ordem indefinida; `Table` é
ambíguo.

`map` minúsculo continua livre para a futura função de ordem superior (`map(xs, f)`), como
em Kotlin/Scala/Rust: a caixa distingue o tipo do valor, e as duas coisas aparecem em
posições sintáticas diferentes.

### Literal `{ chave: valor }`

```lox
val vazio: Map[String, Int] = {}
val idades = { "Ana": 32, "Bia": 28 }
val porCodigo = { 10: "dez", 20: "vinte" }
```

- Chaves são **expressões**, não identificadores mágicos: `{ nome: 1 }` usa a variável
  `nome` como chave; para a string literal use `{ "nome": 1 }`. Isso evita o "objeto JS"
  implícito e mantém I2.
- Em **posição de expressão** (`val m = ...`, argumento, `return`, condição), `{` abre um
  mapa. No **início de um statement**, `{` continua abrindo um bloco. `val m = {}` é o mapa
  vazio; `{}` sozinho é bloco vazio. O REPL e um statement isolado `{ "a": 1 }` precisam de
  parênteses/`val` — igual ao objeto literal de JS.
- Chaves duplicadas no literal são **erro de runtime**
  (`Duplicate key in map literal.`), não "o último vence". Atualizar uma chave existente é
  explícito: `m["a"] = 2`.
- A ordem de avaliação é esquerda→direita: chave, valor, próxima entrada.

### Chave ausente é erro; `get` é a consulta opcional

```lox
m["ausente"]          # erro de runtime: Key not found in map.
m.get("ausente")      # nil (tipo V?)
m.get("ausente") ?? 0 # default lazy, a forma idiomática
```

- `m[k]` devolve `V` e **falha** se a chave não existe, como `xs[i]` fora do intervalo.
  Isso pega typo cedo e não transforma ausência em `nil` silencioso.
- `m.get(k)` devolve `V?` (`V | Nil`), inclusive quando o valor armazenado é `nil`.
  Para distinguir os dois casos use `m.has(k)`.
- **Não existe** `get(k, default)`. O `??` já faz isso e é lazy; um argumento default seria
  avaliado sempre, criaria um segundo idioma e exigiria tipagem dependente de aridade
  (`V | D` ou `Any`).
- `m[k] = v` insere ou atualiza e devolve `v` (como `xs[i] = v`).

### Chaves: `String`, `Int` e `Bool`

A v1 aceita chaves `String`, `Int` e `Bool`, e uniões explícitas desses tipos. `Bool` tem
tag própria na chave para **não colidir** com `0`/`1` (`true == 1` é `false` na linguagem).
`Float` fica de fora: `1 == 1.0` é `true`, então aceitar `Float` exigiria decidir se `1` e
`1.0` são a mesma chave, qual representação `keys()` devolve e como o `Map[Float, V]`
interage com a promoção. Isso é uma decisão própria, não um detalhe de implementação.
`nil`, `List`, `Map`, `Range`, classes e funções **não** são chaves.

Sem `--check`, a restrição continua valendo em runtime:
`Map keys must be strings, integers or booleans.` No `--check`, a anotação
> **Atualização (ADR-0039):** `Float` como chave está **fechado como não** para a v1;
> não há plano de canonicalização de `1 == 1.0`. Chaves seguem `String`/`Int`/`Bool`.

`Map[Float, Int]` é erro de tipo (`Map keys must be String, Int or Bool.`); `Any` continua
sendo o escape hatch e transfere a validação para o runtime.

### Mutações e consultas

| Operação | Resultado |
| --- | --- |
| `m[k]` | `V`; erro se ausente |
| `m[k] = v` | insere/atualiza; devolve `v` |
| `m.get(k)` | `V?`; `nil` se ausente |
| `m.has(k)` | `Bool` |
| `m.remove(k)` | remove e devolve `V`; erro se ausente |
| `m.keys()` | `List[K]` nova, em ordem de inserção |
| `m.values()` | `List[V]` nova, em ordem de inserção |
| `len(m)` | `Int`, O(1) |
| `for k in m` | teclas em ordem de inserção |

`keys()`/`values()` devolvem **snapshots** (listas novas), não views vivas: mutar o
resultado não muda o mapa e vice-versa. `remove` de chave ausente é erro para ser
consistente com `m[k]`; use `m.has(k)` antes quando a remoção for opcional. Não há
`clear`, `entries`, `map`/`filter` nem `+` de mapas na v1.

`Map` é mutável in-place como `List`: `val m = {}` congela o binding, não o conteúdo;
`val n = m` cria aliasing. Mapas **não** são hasháveis e não podem ser chave de `Map`.

### Iteração determinística

`for k in m` percorre as chaves na **ordem de inserção**, não na ordem de hash. Isso é
obrigatório pelo I3 (determinismo observável) e é o mesmo modelo de `List`. Mutar o mapa
durante a iteração é erro de runtime:
`Can't modify a map while iterating over it.` O mapa guarda um `version`; o iterador
confere a versão antes de cada chave e ao final. Atualizar o valor de uma chave existente
também conta como mutação (a versão sobe).

### Igualdade estrutural, independente de ordem

```lox
print { "a": 1, "b": 2 } == { "b": 2, "a": 1 }   # true
print { "a": 1 } == { "a": 1.0 }                # true (igualdade de valores)
print { "a": 1 } == { "a": 1, "b": 2 }          # false
```

- Compara o número de entradas e, para cada par do primeiro, procura a chave no segundo
  por igualdade de chave e compara o valor recursivamente. A ordem de inserção **não**
  importa.
- Ciclos (`m["self"] = m`) são tratados com um conjunto de pares visitados, como em
  `List`; a comparação não entra em loop.
- Mapas não são hasháveis; `List` e `Map` continuam fora do conjunto de chaves.

### Stringify

`stringify` imprime `{"a": 1, "b": 2}` na ordem de inserção. Chaves e valores string são
citados/escapados; `Int`/`Bool` saem sem quotes; mapas aninhados e listas usam a mesma
recursão. Um mapa que contém a si mesmo imprime `{"self": {...}}` (guarda de ciclo
compartilhada com `List`).

## Consequências

### Positivas

- O caso de uso "contar ocorrências", "cache", "tabela" fica possível sem classe manual.
- Chave ausente não vira `nil` por acidente: `m[k]` e `m.get(k)` têm contratos distintos.
- `??` continua sendo a única coalescência; não há `get(k, default)` redundante.
- Ordem de inserção + `version` mantêm I3 e detectam mutação durante iteração.
- A infraestrutura de `List` (literal, index, `for-in`, stringify, igualdade, checker) é
  reusada; `Map` não inventa um segundo modelo de coleção.
- `Float` fora das chaves evita a ambiguidade `1` vs `1.0` antes que ela vire dívida no
  codegen.

### Negativas / custos

- `m[k]` que falha é menos ergonômico que `m[k] ?? default` do Python/JS para consultas
  opcionais; a resposta é usar `m.get(k)`.
- Não há `Map[Float, V]` utilizável; quem precisa de chave fracionária usa `String` ou
  espera a decisão de canonicalização.
- `remove` de chave ausente é erro, então remoções opcionais exigem `has`.
- `keys()`/`values()` copiam; para mapas grandes isso é O(n) e memória extra.
- `{` como mapa em expressão e bloco em statement é uma regra contextual; quem escreve
  `{ "a": 1 }` como statement recebe erro de sintaxe, como no JS.
- Sem `entries()`/pares, `for` só dá chaves; valores exigem `m.values()` ou `m[k]`.

### Neutras

- `Map` não é palavra-chave; é um nome de tipo reconhecido pelo parser.
- Não há construtor `Map()`: o literal `{}` (com tipo esperado) cobre o caso vazio.
- `Map` é invariante em `K` e `V`, como `List`; `Map[String, Int]` não é
  `Map[String, Any]`.
- O checker trata `Map[Any, V]` como escape; o runtime ainda valida o tipo da chave.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `Dict[K, V]` | Mais Pythonico e evita colisão com `map()`, mas quebra a simetria `List`/`Map` e não é o termo dominante em linguagens tipadas. |
| `Dictionary[K, V]` | Nome do Lox2; explícito, porém longo em anotações aninhadas (`Dictionary[String, List[Int]]`). |
| `HashMap[K, V]` | Nomeia a implementação, sugere ordem indefinida (mau para I3) e engessa o layout do LLVM. |
| `Table[K, V]` | Evoca tabela/planilha; não é o termo usual para um mapa K→V tipado. |
| Literal `["k": v]` (Lox2) | Elimina a ambiguidade com bloco, mas confunde com lista, exige lookahead e não tem literal vazio (Lox2 usa `Dictionary()`). |
| `Map{ "k": v }` | Explícito e sem ambiguidade, mas ruidoso e amarra a sintaxe ao nome do tipo. |
| `m[k]` devolve `nil` (Lox2/JS) | Simples com `??`, mas typo vira `nil` silencioso e não distingue ausente de valor `nil`. |
| `m[k]` devolve `V?` sempre | Tipo honesto, mas todo acesso exige narrowing/`??`; verboso no caso comum. |
| `m.get(k, default)` | Duplica `??`, avalia o default sempre (eager) e exige tipagem dependente de aridade. |
| Chaves `Float` | `1 == 1.0` é `true`; canonicalizar muda a representação devolvida por `keys()` e a promoção de `Map[Float, V]`. Fica para uma decisão própria. |
| Igualdade por identidade | Barata, mas assimétrica com `List` (estrutural) e surpreendente para quem vem de Python/Ruby. |
| Duplicata no literal "último vence" | Silencioso; `m[k] = v` já é a forma explícita de atualizar. |
| `keys()`/`values()` como views vivas | Mais barato, mas mutação durante iteração/consulta vira comportamento imprevisível; snapshots são determinísticos. |

## Plano para o LLVM

O tree-walk é a spec; o codegen futuro precisa reproduzir:

- **Layout**: `Map[K, V]` monomorfizado com um header `{ i64 len, i64 cap, i64 version }`,
  um vetor de entradas na ordem de inserção (`{ K key, V value }`) e uma tabela hash
  aberta de índices para lookup. `keys()`/`values()` copiam o vetor de entradas.
- **Hash determinístico**: hash próprio (ex.: FNV-1a) para `String`, identidade/valor para
  `Int` e tag para `Bool`; nunca o hash aleatório do Python. A comparação de chave usa a
  mesma igualdade da linguagem (`Int`/`Float` não se misturam porque `Float` não é chave).
- **Ordem**: inserção append no vetor; remoção pode deixar buraco (tombstone) e a iteração
  pula tombstones, ou compacta; a ordem relativa das chaves restantes é preservada.
- **`version`**: `i64` no header; cada mutação incrementa; a iteração compara antes de
  cada chave e ao final e chama o runtime de erro.
- **Lookup**: hash + probing; `m[k]` chama o helper que devolve `V` ou panic; `get` devolve
  `V?` (tagged/`Option`); `has` devolve `Bool`.
- **Igualdade**: helper de runtime com conjunto de pares visitados (ou limite documentado),
  como em `List`.
- **Sem generics de usuário ainda**: monomorfização por tipo concreto (`Map[String, Int]`,
  `Map[Int, List[String]]`, ...), como `List`.

## Como verificar

- Golden cases: [`tests/cases/map_literal.lox`](../../tests/cases/map_literal.lox),
  [`map_methods.lox`](../../tests/cases/map_methods.lox),
  [`map_iteration.lox`](../../tests/cases/map_iteration.lox),
  [`map_equality.lox`](../../tests/cases/map_equality.lox),
  [`map_stringify.lox`](../../tests/cases/map_stringify.lox),
  [`map_cycle.lox`](../../tests/cases/map_cycle.lox),
  [`map_keys.lox`](../../tests/cases/map_keys.lox) e os erros em
  [`tests/cases/errors/map_*.lox`](../../tests/cases/errors).
- Checker: [`tests/test_checker.py`](../../tests/test_checker.py) cobre inferência do
  literal, `{}` sem contexto, mistura de chaves/valores, invariância, `get`/`has`/
  `keys`/`values`/`remove`, `len`, iteração e `Map[Float, Int]` rejeitado.
- Determinismo: `map_iteration.lox` e `map_stringify.lox` entram em
  [`tests/test_determinism.py`](../../tests/test_determinism.py); a ordem de inserção
  precisa ser byte a byte igual entre seeds.
- `make check` verde (ruff + mypy strict + pytest).

## Referências

- [ADR-0015](0015-listas-tipadas.md) — infraestrutura de `List` reusada e decisão de
  separar `Map`.
- [ADR-0014](0014-identidade-e-invariantes.md) — portão de admissão e I1–I3.
- [ADR-0016](0016-api-stdlib-hibrida.md) — `len` global; métodos para ações específicas.
- [`../spec/semantica.md`](../spec/semantica.md) — mapas, igualdade e hash.
- Lox2 Collections (`Dictionary`, literal `["k": v]`, chave ausente `nil`):
  <https://mysidia-inc.gitbook.io/lox2/basics/collections>.
- Python `dict` (`d[k]` erro, `get` opcional), Rust `HashMap`/`BTreeMap`, Kotlin `Map` e
  Java `Map` — modelos de contrato e ordem.
