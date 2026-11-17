# ADR-0015 — Listas tipadas: um tipo `List[T]`, mutável e invariante

- **Status:** accepted
- **Data:** 2026-11-11
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0005](0005-val-var-imutabilidade.md),
  [ADR-0006](0006-int-float-separados.md), [ADR-0007](0007-ranges-e-iteracao.md),
  [ADR-0010](0010-tipagem-estatica.md), [ADR-0014](0014-identidade-e-invariantes.md),
  [`../spec/semantica.md`](../spec/semantica.md), [`TODO.md`](../../TODO.md) §1
- **Implementação:** [`loxia_core/execution/lox_list.py`](../../loxia_core/execution/lox_list.py),
  [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py), [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py),
  [`docs/spec/semantica.md`](../spec/semantica.md),
  [`tests/cases/list_*.lox`](../../tests/cases)

## Contexto

`for x in` já existia para `Range` e `String`, e a spec prometia `List`/`Map` "quando
existirem" ([ADR-0007](0007-ranges-e-iteracao.md)). Sem coleção, faltava o caso de uso mais
básico de uma linguagem — ordenar, acumular, percorrer dados — e o exemplo de `quicksort`
ficava impossível. O `TODO.md` §1 listava `arrays` e `mapas` como P2.

A pergunta que abriu a decisão foi dupla:

1. **`array` e `list` são a mesma coisa?** Em design de linguagens, "array" costuma
   significar sequência contígua de tamanho fixo; "list" costuma significar sequência
   dinâmica. O "array" do JavaScript é um objeto heterogêneo/esparso — exatamente o que não
   queremos.
2. **`map` entra junto?** Não. A decisão foi separar: `List` primeiro, `Map` depois, para
   não misturar duas semânticas de coleção na mesma mudança.

## Decisão

### Um tipo, chamado `List[T]`

Há **um** tipo de sequência: `List[T]`, com `T` estático e homogêneo. Não existe `Array[T]`
separado na v1. Se um dia o LLVM precisar de uma sequência fixa/contígua como otimização,
`Array[T]` nasce como tipo distinto e documentado — não como sinônimo de `List`.

O nome é **capitalizado**: `List[Int]`, `List[List[String]]`, `List[Int | String]`,
`List[Int]?`. A grafia minúscula `list[int]` é erro com sugestão
(`Unknown generic type 'list'. Did you mean 'List'?`). O motivo é consistência com
`Int`, `String`, `Bool` e `Map`; `list` minúsculo fica livre para uma função/construtor
futuro.

### Mutável in-place

`List[T]` é uma **coleção mutável**. `val xs = [1]` congela o **binding**, não o conteúdo:

```lox
val xs: List[Int] = [1, 2]
xs.push(3)          # ok: muta o conteúdo
xs[0] = 9           # ok
# xs = [4]          # erro: reatribuir o binding 'xs'
```

Isso segue o modelo de `val` do [ADR-0005](0005-val-var-imutabilidade.md) e evita duplicar
a linguagem em `List`/`MutableList`. A consequência é **aliasing**: `val ys = xs` faz as
duas variáveis enxergarem a mesma lista; mutar uma é visível na outra. Está documentado na
spec. Listas imutáveis/persistentes ficam como alternativa futura, não como segundo tipo
agora.

### API híbrida

Consultas universais são **funções nativas**; mutações específicas de lista são **métodos**:

```lox
len(xs)             # Int, O(1); também len("abc")
xs.push(valor)      # muta; devolve nil
xs.pop()            # remove e devolve o último; lista vazia é erro
xs[i]               # lê
xs[i] = valor       # muta; devolve o valor atribuído
```

`len` é global porque também vale para `String` e não pertence a uma classe. `push`/`pop`
são métodos porque só existem em lista e combinam com a sintaxe de métodos que a linguagem
já tem. Não existe `xs.len()`; não existe `push(xs, v)`. A API é pequena de propósito:
`map`, `filter`, `contains`, `sort`, slice e `+` de listas ficam para depois (os dois
primeiros dependem de lambdas).

### Homogeneidade estrita

Sem anotação, todos os elementos precisam ter um tipo comum:

- `[1, 2.0]` → `List[Float]` (promoção `Int → Float` que já existe);
- `[1, "a"]` → **erro**;
- `[1, nil]` → **erro** (união não é inferida automaticamente);
- `[]` sem tipo esperado → **erro**; com `List[T]` esperado, é aceito. Com `Any`
  explícito (escape hatch), vira `List[Any]`.

Para heterogeneidade **explícita**, anote uma união ou `Any`:

```lox
val misto: List[Int | String] = [1, "a"]
val dinamico: List[Any] = [1, "a", true]
```

`List[Any]` é escape hatch e desliga a checagem do elemento; não é supertipo automático de
`List[Int]`. Sem `--check`, o runtime continua dinâmico (tipos são apagados), como o resto
da linguagem; a homogeneidade é **contrato estático**, não checagem de runtime. Isso é
necessário para manter o tree-walk como spec e o LLVM viável.

### Invariância

`List[Int]` **não** é atribuível a `List[Float]`, `List[Any]` ou `List[Int | String]`, mesmo
com `Int <: Float`. O motivo é a mutação: se `List[Int]` fosse `List[Float]`, um
`push(1.5)` pela variável `List[Float]` quebraria a promessa de que todos os elementos são
`Int`. A regra vale para listas aninhadas também.

### Igualdade estrutural

`==`/`!=` comparam listas **elemento a elemento**, com `nil`/bool/número/string usando as
regras já existentes:

```lox
print [1, 2] == [1, 2]       # true
print [1, 2] == [2, 1]       # false
print [1, 2] == [1, 2.0]     # true (igualdade numérica)
print [1] == 1               # false
```

Ciclos são permitidos (`xs.push(xs)`) e tratados: stringify imprime `[[...]]` e a igualdade
usa um conjunto de pares visitados. Listas **não** são hasháveis e não podem ser chave de
`Map` quando ele existir.

### Iteração com fail-fast

`for x in xs` percorre na ordem de inserção. Mutar a lista durante a iteração é **erro de
runtime**, não comportamento indefinido:

```lox
for x in xs { xs.push(x) }   # Can't modify a list while iterating over it.
```

A lista guarda um `version`; o iterador confere a versão antes de cada elemento e ao final.
Sem isso, o resultado dependeria do estado interno do iterador — violaria I3.

### `List` agora, `Map` depois

`Map[K, V]` já existe como **anotação** (`Map[String, Int]`), mas não tem literal, operações
nem runtime. A decisão é implementá-lo numa mudança separada, porque ele traz decisões
próprias: ambiguidade do literal `{ ... }` com bloco, igualdade/hash de chaves, chave
ausente (`erro`, `nil` ou `Option`), ordem de inserção e layout no LLVM. `List` estabelece
a infraestrutura que `Map` reusa (literal, index, type args, invariância, métodos nativos,
iteração, stringify, igualdade, testes).

## Consequências

### Positivas

- Caso de uso básico destravado: `quicksort` e o exemplo `examples/quicksort.lx`.
- `for-in` cumpre a promessa de iterar sobre `List`, sem protocolo de usuário.
- Uma decisão de tipo só (`List[T]`), sem `Array`/`List`/`MutableList` competindo.
- Homogeneidade explícita: `[1, "a"]` falha no `--check` em vez de virar JS.
- A API é pequena e cada operação tem erro definido (índice, `pop` vazio, mutação durante
  iteração).

### Negativas / custos

- **Mutabilidade + aliasing** surpreende quem vem de linguagens imutáveis; a spec avisa.
- **Invariância** é mais verbosa: para passar `List[Int]` onde se espera `List[Float]` é
  preciso converter/copiar explicitamente. É o preço da segurança com `push`.
- **Homogeneidade só vale no `--check`**; sem ele, `[1, "a"]` executa. É coerente com a
  tipagem gradual, mas não é uma garantia de runtime.
- **Sem `map`/`filter`** na v1; quem precisa escreve o laço.
- **Lista literal não é default de parâmetro nem inicializador de campo** (a regra de
  constante do parser continua). Em `init`, `this.xs = []` funciona.
- **Sem narrowing** de `List[T]?`: `len(xs)` e `for` exigem não-opcional; `xs?.push` e
  `xs?.pop` funcionam.

### Neutras

- `List` não é palavra-chave; é um nome de tipo reconhecido pelo parser.
- `len` é uma função nativa como `clock`/`range`, e pode ser sombreada por uma função do
  usuário.
- `Map` continua no roadmap; a anotação já existe, o runtime não.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `Array[T]` separado de `List[T]` | Duas semânticas de sequência na v1; `Array` só se o LLVM precisar de tamanho fixo/contíguo. |
| Lista imutável/persistente | `push`/`set` O(n), sintaxe `xs = xs.push(v)`; não combina com o uso esperado (quicksort, acumuladores). |
| `List` + `MutableList` (Kotlin) | Segurança máxima, mas dobra checker, runtime e codegen; adiável. |
| Lista heterogênea como JS | Viola I2 e a própria motivação; `List[Any]`/união explícita cobrem o caso. |
| Covariância (`List[Int]` → `List[Float]`) | Unsound com `push`; exigiria lista read-only. |
| Igualdade por identidade | `[1,2] == [1,2]` seria `false`; surpreende e atrapalha testes/asserts. |
| `xs.len()` em vez de `len(xs)` | `len` também vale para `String`; função universal é mais simples que método em primitivo. |
| `Map` junto | Dobraria a superfície e anteciparia decisões de literal/hash/chave ausente; `List` primeiro. |

## Plano para o LLVM

O tree-walk é a spec; o codegen futuro precisa reproduzir:

- **Layout**: `List[T]` monomorfizado como `{ i64 len, i64 cap, T* data }` (ou header
  compartilhado + ponteiro para dados). `List[Int]` usa `i64*` sem boxing. `List[Any]` usa
  valores boxeados.
- **Promoção `Int → Float` é só de checagem**: `xs.push(1)` em `List[Float]` é aceito e o
  valor continua `Int` no tree-walk (`print xs` → `[1, 2.0]`), como `val f: Float = 1`.
  Para preservar I1, o codegen de `List[Float]` precisa manter o valor original (elemento
  tagged/boxeado) ou o checker passa a exigir `Float` exato nas escritas de lista — a
  decisão de representação fica para o codegen, não para este ADR. Não emitir `double*`
  cru sem resolver isso.
- **Mutação**: `push` realoca com crescimento geométrico; `pop` decrementa `len`; `xs[i]`
  carrega no offset `i * sizeof(T)` com guarda de índice.
- **Iteração**: o `version` do tree-walk compila para um `i64` no header e uma comparação
  por iteração; mutação durante o laço chama o runtime de erro.
- **Igualdade**: chamada a um helper de runtime que compara `len` e elementos
  recursivamente; ciclos exigem um conjunto de pares visitados (ou um limite documentado).
- **`len`**: carrega o campo `len` (O(1)); para `String`, usa o header de tamanho.
- **Sem generics de usuário ainda**: como só `List` é genérica, a monomorfização é por tipo
  concreto (`List[Int]`, `List[String]`, ...), não um sistema de generics completo.

## Como verificar

- Golden cases: [`tests/cases/list_literal.lox`](../../tests/cases/list_literal.lx),
  [`list_index.lox`](../../tests/cases/list_index.lx),
  [`list_methods.lox`](../../tests/cases/list_methods.lx),
  [`list_iteration.lox`](../../tests/cases/list_iteration.lx),
  [`list_equality.lox`](../../tests/cases/list_equality.lx),
  [`list_stringify.lox`](../../tests/cases/list_stringify.lx),
  [`list_cycle.lox`](../../tests/cases/list_cycle.lx) e os erros em
  [`tests/cases/errors/list_*.lox`](../../tests/cases/errors).
- Checker: [`tests/test_checker.py`](../../tests/test_checker.py) cobre invariância,
  literal misto, `[]` sem contexto, `push`/index com tipo errado e `len`.
- Determinismo: `list_iteration.lox` e `list_stringify.lox` entraram em
  [`tests/test_determinism.py`](../../tests/test_determinism.py); `examples/quicksort.lx`
  também.
- `make check` verde (ruff + mypy strict + pytest).

## Referências

- [ADR-0005](0005-val-var-imutabilidade.md) — `val`/`var` e imutabilidade do binding.
- [ADR-0006](0006-int-float-separados.md) — promoção `Int → Float`.
- [ADR-0007](0007-ranges-e-iteracao.md) — `for-in` e iteráveis.
- [ADR-0010](0010-tipagem-estatica.md) — checker gradual e tipos apagados.
- [ADR-0014](0014-identidade-e-invariantes.md) — portão de admissão e I1–I3.
- [`../spec/semantica.md`](../spec/semantica.md) — listas e mapas.
- [`TODO.md`](../../TODO.md) §1 — checklist de sintaxe.
- Kotlin `List`/`MutableList` (invariância e mutabilidade), Python `list` (ordem e
  igualdade estrutural), Rust `Vec<T>` (layout e crescimento).
