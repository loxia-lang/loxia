# Semântica

Comportamento observável do interpretador. Implementação: [`src/execution/interpreter.py`](../../src/execution/interpreter.py),
[`src/semantics/resolver.py`](../../src/semantics/resolver.py), [`src/execution/environment.py`](../../src/execution/environment.py),
[`src/execution/lox_function.py`](../../src/execution/lox_function.py), [`src/execution/lox_class.py`](../../src/execution/lox_class.py),
[`src/execution/lox_instance.py`](../../src/execution/lox_instance.py), [`src/execution/values.py`](../../src/execution/values.py).

## Execução

Um programa é uma lista de declarações executadas **em ordem**. Um erro de compilação
(léxico, sintaxe ou resolver) impede a execução inteira. Um erro de runtime interrompe o
programa no ponto em que ocorreu; o que já foi impresso permanece. Desde o
[ADR-0026](../adr/0026-freeze-1.0.md), erro de runtime **não capturado** é fatal (exit 70);
`try`/`raise` ([ADR-0042](../adr/0042-excecoes.md)) capturam exceções explícitas e erros de
runtime, e `Result` cobre erro esperado. Erros de tipo/sintaxe saem 65.

O REPL executa uma linha por vez, **mantendo variáveis, funções e classes** entre linhas.
Uma expressão pura como `1 + 1` é embrulhada em `print` e mostra `2`; declarações
(`var`, `fn`, `class`) não imprimem nada.

## Valores

| Valor | Origem | `stringify` |
| --- | --- | --- |
| `nil` | `nil`, `var` sem inicializador, `return;` | `nil` |
| `true`/`false` | literais, comparações | `true`/`false` |
| `Int` | literais sem `.`/expoente, aritmética inteira | decimal (`42`, `-3`) |
| `Float` | literais com `.`/expoente, `/`, mistura com `Float` | round-trip (`42.0`, `2.5`) |
| `List` | literal `[...]` | `[1, 2, 3]` (strings citadas dentro da lista) |
| `Map` | literal `{...}` | `{"a": 1, "b": 2}` (ordem de inserção) |
| `Range` | `a..b`, `range(a, b, step)` | `<range 0..10>` |
| string | literais, `+`, interpolação | conteúdo |
| função | `fn` | `<fn nome>` |
| função nativa | `len` | `<native fn>` |
| classe | `class` | nome da classe |
| instância | chamada de classe | `Nome instance` |

Números são **`Int` (i64) ou `Float` (f64)** — [ADR-0006](../adr/0006-int-float-separados.md).
`print 3;` mostra `3` e `print 3.0;` mostra `3.0`: o tipo vem do literal. As regras
completas estão neste documento e no
[ADR-0006](../adr/0006-int-float-separados.md).

### Truthiness

Só `nil` e `false` são falsos. `0`, `0.0`, `""`, listas e mapas (inclusive vazios) são
**verdadeiros**.

### Igualdade (`==`, `!=`)

- `nil == nil` → `true`; `nil` vs qualquer outro → `false`;
- `Int` e `Float` comparam por valor numérico, com promoção: `1 == 1.0` → `true` (o `Int`
  é convertido para `Float`; acima de `2^53` a conversão pode perder precisão, como no
  LLVM);
- `Range` compara **estruturalmente** (`start`, `end`, `step`): `(0..3) == (0..3)` → `true`;
- `List` compara **estruturalmente**, elemento a elemento, inclusive aninhada e com
  igualdade numérica (`[1, 2] == [1, 2.0]` → `true`). Comprimentos diferentes são
  `false`; ciclos são tratados com um conjunto de pares visitados;
- `Map` compara **estruturalmente, independentemente da ordem de inserção**:
  `{"a": 1, "b": 2} == {"b": 2, "a": 1}` → `true`; o número de entradas e a igualdade de
  cada valor contam, com guarda de ciclo. `Map` não é hashável;
- `true == 1` → `false` (booleano nunca é número);
- strings comparam por conteúdo;
- funções, classes e instâncias comparam por **identidade** (o mesmo objeto);
- `NaN != NaN` (IEEE); nenhum literal produz `NaN` hoje.

### Formatação de números

- `Int` → decimal, sem casas (`42`, `-3`);
- `Float` → menor representação que volta ao mesmo `double`, **sempre** distinguindo de
  `Int`: `2.0`, `-0.0`, `3.14`, `0.30000000000000004`;
- notação científica do Python a partir da magnitude correspondente (`1e+20`, `1e-07`);
- `NaN`, `inf` e `-inf` são os textos de `Float` não finitos; `inf` só aparece por
  overflow de `Float` (divisão por zero é erro);
- a formatação é contrato dos golden cases: `42` e `42.0` são saídas diferentes.

Listas formatam como `[1, 2, 3]`; strings dentro de listas são citadas e escapadas
(`["a\nb"]`); uma lista que contém a si mesma imprime `[[...]]`. Mapas formatam como
`{"a": 1, "b": 2}` na ordem de inserção, com strings citadas/escapadas; um mapa que contém
a si mesmo imprime `{"self": {...}}`. Fora de lista/mapa, string continua sem aspas.

## Variáveis, `val` e `var`

- `val x = expr;` cria binding **imutável** e **exige inicializador**.
- `var x;` cria binding mutável com `nil`; `var x = expr;` idem com valor.
- No `--check`, todo binding é **monomórfico**: `var x = 1` é `Int` para sempre; `x = 2.0`
  é erro. `var x = nil` sem anotação é erro (`Can't infer type of 'x' from nil; add an
  annotation.`); use `var x: Int? = nil` ou `var x: Any = nil`. Campo mutável com
  inicializador `nil` segue a mesma regra; `val x = nil` é permitido. Ver
  [ADR-0024](../adr/0024-mutacao-monomorfica.md).
- A imutabilidade é do **nome**, não do valor: `val lista` ainda pode ter conteúdo mutável
  (`lista.push(1)` é permitido).
- Atribuir a `val` local (ou a parâmetro imutável) é **erro de compilação**:
  `'x' is immutable; declare it with 'var' to allow assignment.`
- Atribuir a `val` **global** é erro de **runtime** (mesma mensagem, exit 70): globais não
  são rastreadas pelo resolver.
- `val` global **não pode ser redeclarado** (`val x = 1; var x = 2;`): erro de runtime
  `Can't redeclare immutable variable 'x'.` `var` global continua redeclarável; `var`
  seguido de `val` é permitido e o nome passa a ser imutável.
- Em escopo local (bloco, função, `for`), redeclarar o mesmo nome no mesmo escopo é erro de
  compilação: `Already a variable with this name in this scope.` (vale para `val` e `var`).
- Blocos aninhados podem **sombrear** nomes de escopos externos (inclusive `val`).
- Ler variável local no próprio inicializador é erro:
  `Can't read local variable in its own initializer.` (global vira
  `Undefined variable` em runtime).
- Declarações `fn` e `class` criam bindings **mutáveis** (decisão separada em aberto).
- O resolver grava a **distância** de cada acesso local; variáveis globais continuam sendo
  buscadas em runtime no ambiente global. Isso garante escopo léxico: uma closure lê a
  variável do local onde foi **declarada**, não do local de onde é chamada.

Exemplo canônico:

```lox
var a = "global";
{
  fn showA() { print a; }
  showA();        // global
  var a = "block";
  showA();        // global (não "block")
}
```

## Operadores

| Operador | Tipos | Resultado |
| --- | --- | --- |
| `!` | qualquer | nega a truthiness |
| `-` | número | negação (em `Int`, com wrapping; debug checa overflow) |
| `~` | `Int` | complemento de 64 bits (`~x == -x - 1`) |
| `+` | dois números **ou** duas strings | soma com promoção / concatenação |
| `-` `*` | dois números | aritmética com promoção; `Int` faz wrapping (debug checa) |
| `/` | dois números | divisão **sempre `Float`** (`4 / 2` → `2.0`) |
| `//` | `Int` | divisão inteira truncada; divisor zero é erro |
| `%` | dois números | resto truncado (sinal do dividendo); `fmod` se houver `Float` |
| `**` | números | `Int ** Int` → `Int`; qualquer `Float` → `Float`; direito-associativo |
| `&` `\|` `^` | `Int` | operações bit a bit em 64 bits |
| `<<` `>>` `>>>` | `Int` | shift; `>>` aritmético, `>>>` lógico; contagem `0..63` |
| `<` `<=` `>` `>=` | dois números | booleano (promoção; com `NaN`, tudo `false`) |
| `==` `!=` | qualquer | igualdade |
| `and` `or` | qualquer | curto-circuito, devolve o operando |
| `a if c else b` | condição qualquer | escolhe um ramo; só avalia o escolhido |
| `a ?? b` | qualquer | devolve `a`, ou `b` se `a` for `nil` |
| `a?.b` | objeto anulável | `nil` se `a` for nil; senão acessa `b` |
| `a as T` | `Int`/`Float`/`Any`/classe/lista/mapa | cast explícito; falha em runtime se não converter |

- `Int op Float` promove o `Int` para `Float` (`1 + 2.0` → `3.0`); `Float → Int` nunca é
  implícito.
- **`--debug`** checa overflow de `Int` em `+ - * ** -`, `INT_MIN // -1` e `INT_MIN % -1`;
  overflow é erro fatal (`Integer overflow.`, exit 70). Sem a flag, release faz wrapping.
  Shifts continuam bitwise. Ver [ADR-0028](../adr/0028-overflow-debug.md).
- `+` **não** mistura número e string: `Operands must be two numbers or two strings.`
- Comparações relacionais são só numéricas: `Operands must be numbers.`
- Divisão por zero é **erro de runtime** (`Division by zero not allowed`), para `Int` e
  `Float` — decisão nossa, diferente do livro (que devolveria `inf`/`NaN`).
- Resto por zero também é erro de runtime (`Modulo by zero not allowed`).
- `%` segue C/LLVM: `-7 % 3` → `-1` (sinal do dividendo), não `2`.
- `//` também é truncado (`-7 // 2` → `-3`); com `%`, vale
  `a == (a // b) * b + (a % b)`. Overflow de `INT_MIN // -1` faz wrap; no `--debug` é
  erro. `INT_MIN % -1` é `0` no release e erro no debug.
- `**`: `2 ** 3` → `Int` 8; `2 ** -1` é erro (`Negative exponent not allowed for integer
  power.`); use `2.0 ** -1` para `0.5`. `2 ** 63` faz wrap para `INT_MIN`; no `--debug`
  cada multiplicação intermediária é checada. Expoente negativo em `Float` é permitido;
  domínio/overflow inválido é erro.
- `~`, `&`, `|`, `^` e shifts são **só `Int`**; `Bool` e `Float` são
  `Operands must be integers.` (unário: `Operand must be an integer.`). `>>>` opera no
  padrão unsigned de 64 bits (`-1 >>> 1 == INT_MAX`).
- Shift fora de `0..63` é erro (`Shift count must be between 0 and 63.`), não máscara.
- `and`/`or` devolvem o valor do operando, não um booleano:
  `nil or 2` → `2`; `false and 1` → `false`.
- A ordem de avaliação é esquerda→direita; `and`/`or` só avaliam a direita se necessário.
- `a if c else b`: condição usa truthiness; só um ramo é avaliado. Tipo é a união dos
  ramos (`Int`/`Int` → `Int`); o `else` é associativo à direita.
- `??` é **só nil**: `0 ?? 5` → `0`, `false ?? true` → `false`, `"" ?? "x"` → `""`;
  `or` continua truthiness. O direito só é avaliado se o esquerdo for `nil`.
- `?.` só protege `nil`: `nil?.x` → `nil`; `a?.b.c` não protege `b`; use `a?.b?.c`.
  Em `a?.m()`, se `a` for nil, o método e os argumentos não são avaliados; se `a` não for
  nil mas `m` não existir, continua erro. `a?.b = c` é inválido.
- `a?.b ?? c` combina os dois: `?.` evita o acesso e `??` aplica o default quando o
  resultado é nil. Sem `?.`, `a.b ?? c` ainda erra se `a` for nil.
- `?:` elvis **não existe**; `??` é a única coalescência.
- Strings processam `\n`, `\t`, `\r`, `\"`, `\\`, `\0`, `\$` e `\u{XXXX}`; escape
  desconhecido é erro. `"${expressão}"` interpola (ver abaixo). Ainda não há `"""` nem raw
  strings.
- Fonte e strings são UTF-8; `len(s)` conta **code points**, não bytes. `s[i]` em string
  **não existe**: para acesso aleatório use `chars(s)` (`List[String]`, O(n) explícito);
  `for c in s` itera code points sem alocar. Strings comparam por conteúdo (`==`/`!=`) e
  ordenam por `< <= > >=` na ordem de code point (= ordem de bytes UTF-8); mistura com
  número é erro. Não há normalização (`"é" != "e\u{301}"`). Identificadores são ASCII (sem
  normalização Unicode); ver [ADR-0026](../adr/0026-freeze-1.0.md) e
  [ADR-0035](../adr/0035-strings-texto.md).
- Comentários: `#` até o fim da linha; `/* ... */` de bloco, aninhado. `//` é operador,
  não comentário.

## Interpolação

`"texto ${expressão} mais texto"` avalia cada expressão da esquerda para a direita e
concatena os trechos. A conversão é a mesma `stringify` do `print`:

```lox
val nome = "Ana"
print "Oi, ${nome}!"        # Oi, Ana!
print "1 + 2 = ${1 + 2}"    # 1 + 2 = 3
print "mapa: ${{"a": 1}}"   # mapa: {"a": 1}
print "escape: \${nome}"   # escape: ${nome}
print "cifrão: $5"          # cifrão: $5
```

- Qualquer expressão é aceita, inclusive chamada, índice, mapa/lista e outra string
  interpolada; o resultado é sempre `String`.
- `\$` e `\${` produzem `$`/`${` literais; fora de `${...}`, `$`, `{` e `}` são literais.
- O checker checa cada expressão; erro dentro dela é erro normal do `--check`.
- Sem format spec, `"""` ou raw strings na v1.

## Listas

`List[T]` é a única sequência da linguagem: **homogênea no tipo**, **mutável in-place** e
**invariante**. Ver [ADR-0015](../adr/0015-listas-tipadas.md).

```lox
val xs: List[Int] = [1, 2, 3]
print xs[0]          # 1
xs[1] = 20
xs.push(4)
print len(xs)        # 4
print xs.pop()       # 4
for x in xs { print x }
```

- **Literal**: `[a, b, c]`; `[]` é a lista vazia. O tipo é inferido por unificação dos
  elementos: `[1, 2]` é `List[Int]`, `[1, 2.0]` é `List[Float]` (promoção). Mistura não
  numérica (`[1, "a"]`) é erro no `--check`; heterogeneidade exige anotação explícita
  (`List[Int | String]` ou `List[Any]`). Lista vazia sem tipo esperado é erro; com `Any`
  explícito, vira `List[Any]`.
- **Acesso**: `xs[i]`, com `i` `Int` e base zero. Índice negativo ou fora do intervalo é
  erro de runtime; `xs[i]` em não-lista/não-mapa é `Only lists and maps can be indexed.`
- **Atribuição**: `xs[i] = v` muta e devolve `v`; `v` precisa ser atribuível a `T` no
  `--check`; os mesmos limites de índice valem em runtime.
- **Métodos**: `xs.push(v)` adiciona ao fim e devolve `nil`; `xs.pop()` remove e devolve o
  último, e lista vazia é erro (`Can't pop from an empty list.`). `xs.len()` não existe;
  use `len(xs)`.
- **`len`**: `len(xs)` é O(1) e devolve `Int`; `len(s)` devolve o número de code points da
  string, e `len(m)` o número de entradas do mapa. `len` de outro tipo é erro de runtime no
  tree-walk e erro de tipo no `--check`.
- **Iteração**: `for x in xs` percorre na ordem de inserção; mutar a lista durante o laço é
  erro (`Can't modify a list while iterating over it.`), não snapshot silencioso.
- **Igualdade**: estrutural (ver acima). **Stringify**: `[1, 2, 3]`, com strings citadas e
  escapadas (`["a\nb"]`) e ciclos como `[[...]]`.
- **Aliasing**: listas são referências. `val ys = xs` não copia; mutar `ys` é visível em
  `xs`. `val` congela o binding, não o conteúdo.
- **Opcional**: `List[T]?` e `xs?.push(...)`/`xs?.pop()` funcionam; `len(xs)` e `for` sobre
  `List[T]?` exigem `if (xs != nil)` (narrowing) ou `??`/`?.`.
- **Tipos apagados**: sem `--check`, a lista aceita qualquer elemento em runtime; a
  homogeneidade é contrato estático. Não há checagem de tipo em `push` no runtime.
  A promoção `Int → Float` também é só de checagem: `xs.push(1)` em `List[Float]` é aceito,
  mas o valor continua `Int` em runtime (`print xs` → `[1, 2.0]`), como
  `val f: Float = 1`.
- **Limites**: sem slice, `+` de listas, `map`/`filter`, `contains`, `sort` nem indexação de
  string na v1. Lista literal não é default de parâmetro nem inicializador de campo; em
  `init`, `this.xs = []` funciona.

## Tuplas

`(1, "a")` é uma tupla de aridade 2; o tipo é `(Int, String)`. Tuplas têm **2+ elementos**
(sem `()` e sem `(x,)`), são **imutáveis** e **covariantes por elemento**: `(Dog, Int)` é
atribuível a `(Animal, Int)` e `(Int, String)` a `(Any, Any)`. Ver
[ADR-0030](../adr/0030-tuplas.md) e [ADR-0036](../adr/0036-tuplas-implementacao.md).

```lox
val par: (Int, String) = (1, "a")
print par[0]                 # 1
val (n, s) = par            # destructuring
print s                      # a
print len(par)               # 2
```

- **Literal e tipo**: `(a, b)`; parênteses sem vírgula continuam agrupamento. O tipo
  `(Int, String)` pode aninhar (`(Int, (String, Bool))`) e voltar de funções.
- **Acesso**: `t[0]`, `t[1]`; índice precisa ser `Int`. Índice **literal** fora do range é
  erro de `--check` (`Tuple index 2 out of bounds for length 2.`); índice **dinâmico**
  tem tipo `Int | String` (união dos elementos) e bounds em runtime
  (`Tuple index 5 out of bounds for length 2.`). Sem índice negativo.
- **Destructuring**: `val (a, b) = t`, `var (c, d) = t` e anotação opcional
  (`val (a, b): (Int, String) = t`). Exige tupla (ou união de tuplas de mesma aridade);
  `Any` só com anotação; aridade errada e nome duplicado são erro.
- **Igualdade**: estrutural, elemento a elemento (`(1, "a") == (1.0, "a")` → `true`).
- **Stringify**: `(1, "a")`, com strings citadas/escapadas, recursivo; `(...)` se houver
  ciclo via lista/mapa.
- **Imutabilidade**: `t[0] = x` é erro (`Only lists and maps can be indexed.`).
- **Iteração**: `for x in t` percorre os elementos; o tipo de `x` é a união dos itens
  (`(Int, String)` → `Int | String`).
- **`is`/`as`**: `x is (A, B)` testa aridade e cada posição; `x as (A, B)` é cast
  verificado (aceita `Any`; falha em runtime se a forma não bater).
- **Fora da v1**: tuplas não são hasháveis nem chave de `Map`; sem destructuring aninhado;
  o backend L0–L3 as rejeita (layout no L6).

## Mapas

`Map[K, V]` é a coleção associativa da linguagem: **homogênea**, **mutável in-place** e
**invariante** em `K` e `V`. Ver [ADR-0017](../adr/0017-mapas-hash.md).

```lox
val idades: Map[String, Int] = {"Ana": 32}
print idades["Ana"]          # 32
print idades.get("Bia")      # nil
print idades.get("Bia") ?? 0 # 0
idades["Bia"] = 28
print idades.has("Bia")      # true
print len(idades)            # 2
for nome in idades { print nome }   # Ana, Bia (ordem de inserção)
```

- **Literal**: `{ chave: valor, ... }`; `{}` é o mapa vazio em posição de expressão. As
  chaves são **expressões**: `{ nome: 1 }` usa a variável `nome`; `{ "nome": 1 }` usa a
  string. No início de um statement, `{` continua abrindo um bloco — para um mapa isolado,
  use `val m = ...` ou parênteses. Chave repetida no literal é erro de runtime
  (`Duplicate key in map literal.`); para atualizar use `m[k] = v`.
- **Inferência**: sem anotação, as chaves e os valores precisam ter um tipo comum
  (`{"a": 1, "b": 2.0}` → `Map[String, Float]`); mistura não numérica exige anotação
  (`Map[String, Int | String]` ou `Map[String, Any]`). `{}` sem contexto é erro no
  `--check`; com `Map[K, V]` esperado, é aceito.
- **Chaves**: `String`, `Int`, `Bool` e uniões explícitas desses tipos. `Bool` é distinto de
  `0`/`1` (`{true: "a", 1: "b"}` tem duas chaves). `Float` não é chave na v1 (a relação
  `1 == 1.0` exigiria canonicalização); `nil`, `List`, `Map`, `Range`, classes e funções
  também não. Sem `--check`, a restrição vale em runtime
  (`Map keys must be strings, integers or booleans.`). **Hash consistente com `==`**: as
  chaves aceitas comparam e fazem hash pela mesma noção — `Bool` tem tag própria (não
  colide com `0`/`1`), `String` compara por conteúdo e `Int` por valor; como `Float` é
  rejeitado na entrada, `1 == 1.0` nunca vira duas entradas nem quebra a busca.
- **Acesso**: `m[k]` devolve `V` e é **erro** se a chave não existe
  (`Key not found in map.`). `m.get(k)` devolve `V?` (`nil` se ausente); `m.has(k)` devolve
  `Bool` e distingue ausente de valor `nil`. `m[k]` em não-mapa/não-lista é
  `Only lists and maps can be indexed.`
- **Atribuição**: `m[k] = v` insere ou atualiza e devolve `v`; no `--check`, `k` precisa ser
  atribuível a `K` e `v` a `V`.
- **Métodos**: `m.remove(k)` remove e devolve `V` (chave ausente é erro);
  `m.keys()`/`m.values()` devolvem `List[K]`/`List[V]` novas, em ordem de inserção (snapshot,
  não view). `m.len()` não existe; use `len(m)`.
- **Iteração**: `for k in m` percorre **chaves** na ordem de inserção; mutar o mapa durante o
  laço é erro (`Can't modify a map while iterating over it.`), inclusive atualizar o valor de
  uma chave existente. Pares `(k, v)` exigiriam tupla/destructuring (ainda não existem).
- **Igualdade**: estrutural e independente da ordem (ver acima). **Stringify**:
  `{"a": 1, "b": 2}` com strings citadas/escapadas e ciclos como `{"self": {...}}`.
- **Aliasing**: mapas são referências. `val n = m` não copia; mutar `n` é visível em `m`.
  `val` congela o binding, não o conteúdo. Mapas **não** são hasháveis e não podem ser chave.
- **Opcional**: `Map[K, V]?` e `m?.get(...)`/`m?.has(...)` funcionam; `len(m)` e `for` sobre
  `Map[K, V]?` exigem `if (m != nil)` (narrowing) ou `??`/`?.`.
- **Limites**: sem `clear`, `entries`, `map`/`filter`, `contains` nem `+` de mapas na v1.
  Sem `--check`, os tipos são apagados: o runtime não valida `V` no `m[k] = v`, só o tipo da
  chave; a homogeneidade é contrato estático.

## Ranges e `for-in`

`a..b` cria um `Range` **half-open** (`a` incluso, `b` exclusivo), só com bounds `Int`;
`range(a, b, step)` faz o mesmo com passo explícito (inclusive negativo). Range é um valor
lazy e reutilizável: não materializa elementos e cada `for` cria a sua própria iteração.

```lox
for i in 0..4 { print i; }        // 0 1 2 3
for i in range(5, 0, -2) { ... }  // 5 3 1
for i in 5..2 { ... }             // vazio
```

- Fontes aceitas hoje: `Range` (produz `Int`), `String` (produz `String` de 1 code point),
  `List[T]` (produz `T`, na ordem de inserção) e `Map[K, V]` (produz `K`, as chaves, na
  ordem de inserção).
- O iterável é avaliado **uma vez**, antes do binding do laço; bounds são avaliados uma vez
  da esquerda para a direita.
- A variável do laço é um **`val` novo por iteração**: reatribuí-la é erro de compilação e
  closures capturam o valor daquela iteração.
- Mutar a coleção durante a iteração é **proibido**: em `List`/`Map` é erro de runtime
  (`Can't modify a list while iterating over it.` /
  `Can't modify a map while iterating over it.`); `Range`/`String` são imutáveis.
- `Range` é truthy, imprime como `<range a..b>` (ou `<range a..b step s>`) e compara
  estruturalmente.
- Erros de runtime: `Can only iterate over a range, a list, a map or a string.`,
  `Range bounds must be integers.`, `range() arguments must be integers.`,
  `range() step can't be zero.`; aridade errada usa a mensagem padrão
  (`Expected 3 arguments but got N.`).

## Statements

| Statement | Efeito |
| --- | --- |
| `print expr;` | avalia e imprime com `stringify` + `\n` |
| `expr;` | avalia e descarta |
| `{ … }` | novo escopo |
| `if (c) s elif (c) s else s` | executa o ramo conforme truthiness; `elif` é `else if` |
| `while (c) s` | repete enquanto truthy |
| `for (init; cond; incr) s` | desaçucarado para bloco + `while` (ver sintaxe) |
| `for x in e s` | itera `e` (Range/String/List/Map/Tuple hoje); `x` é `val` por iteração |
| `return expr?;` | desempilha até a chamada da função |

O `;` é opcional no fim da linha (ou EOF); duas instruções na mesma linha ainda precisam
dele. Continuação de expressão exige o operador no **fim** da linha; operador no começo
da linha seguinte inicia outro statement. `return` sozinho na linha devolve `nil`.

## Funções

- Declaração: `fn nome(params) { corpo }`; o nome é definido **antes** do corpo, então a
  função pode ser recursiva; funções no mesmo escopo podem se chamar (resolução em runtime
  para globais, distância para locais).
- Parâmetros são **imutáveis por padrão** (`val` implícito). `fn f(var x)` permite
  reatribuir `x`; sem `var`, a atribuição é erro de compilação.
- Parâmetro pode ter **default constante**: `fn f(a, b = 10)`. Obrigatórios vêm antes dos
  opcionais; depois de um default, todos os seguintes precisam de default.
- Chamada: avalia o **callee** primeiro e os argumentos da esquerda para a direita; depois
  verifica se é chamável e a aridade.
- Não é chamável: `Can only call functions and classes.`
- Aridade errada: aridade fixa usa `Expected N arguments but got M.`; com defaults,
  `Expected at least N arguments but got M.` ou `Expected N to M arguments but got K.`
- Closures: a função captura o ambiente onde foi **declarada** (por referência). Variáveis
  capturadas continuam mutáveis.
- `return;` devolve `nil`. `return` no topo do programa é erro de compilação:
  `Can't return from top-level code.` Para retornar um valor, ele precisa estar na mesma
  linha do `return`; `return` sozinho na linha devolve `nil`.
- Parâmetros e locais do corpo compartilham o mesmo escopo: declarar `var a` quando existe
  parâmetro `a` é erro (mesma mensagem de redeclaração).
- `clock()` **não existe na 1.0**: tempo é entrada ambiente e violaria o I3. Um módulo
  `time` explicitamente não determinístico fica para depois. O prelúdio determinístico é
  `chars`, `len`, `str`, `repr`, `range`, `Int`, `Float` e `math`.
- `len(x)` aceita `List`, `Map` ou `String`; devolve `Int` (O(1) para lista/mapa, code
  points para string). Outro tipo é erro:
  `len() expects a string, a list or a map.`
- `chars(s)` exige `String` e devolve `List[String]` com os code points (cada um é uma
  string de 1 cp); O(n) explícito. `chars("aço")` → `["a", "ç", "o"]`; outro tipo é erro.
- `str(x)` devolve a forma de exibição (string no topo sem aspas); `repr(x)` devolve a forma
  de debug (string citada/escapada). Ambas aceitam qualquer valor, têm aridade 1 e devolvem
  `String`; em listas as duas usam a mesma formatação hoje. Builtins globais são
  imutáveis: redefinir `chars`/`len`/`str`/`repr`/`range`/`Int`/`Float`/`math` no escopo global é
  erro; local e parâmetro podem sombrear. `clock` deixou de ser builtin; pode ser usado
  como nome comum.
- `range(start, end, step)` é nativa de aridade 3 e exige `Int`; devolve `Range`.
### Conversões e `math`

Casts são explícitos com `as`; não há conversão implícita:

```lox
val i = 3.9 as Int        # 3 (trunca em direção a zero)
val f = 3 as Float        # 3.0
val d = anyValue as Dog   # checagem de runtime
```

- `Int as Float` arredonda para f64 (pode perder precisão acima de `2^53`).
- `Float as Int` trunca em direção a zero; `NaN`, `Inf` ou fora de `[INT_MIN, INT_MAX]`
  é erro fatal (`Can't cast this Float to Int.`).
- `Any as T` checa o runtime: números convertem para `Int`/`Float`; classes, listas e
  mapas usam a mesma checagem de `is`.
- `T as T` é identidade; `as Any` devolve o valor. Target união (`Int?`, `Int | String`)
  ainda não existe; use narrowing/`is`.
- String não vira número por cast; use `parse`.

```lox
val n = Int.parse("42")      # Int? (nil se inválido)
val f = Float.parse("3.14")  # Float?
```

`Int.parse`/`Float.parse` são membros dos namespaces nativos `Int`/`Float`; texto inválido,
vazio, com espaços ou fora do range devolve `nil`. Não existe `42.toString()`; use `str`.

`math` é um namespace nativo somente leitura:

```lox
math.abs(x)   math.min(a, b)   math.max(a, b)   math.clamp(x, lo, hi)
math.floor(x) math.ceil(x)     math.round(x)    math.trunc(x)
math.sqrt(x)
```

- `abs/min/max/clamp` aceitam `Int`/`Float` e promovem na mistura; `min/max` de dois
  argumentos; `clamp` exige `low <= high`.
- `floor/ceil/round/trunc` devolvem `Int`; exigem valor finito no range i64. `round`
  arredonda metade para longe de zero.
- `sqrt` devolve `Float`; negativo vira `NaN`.
- `abs(INT_MIN)` é wrap no release e erro no `--debug`.
- **Fora da 1.0**: `log`, `exp`, `sin`, `cos`, `tan`, `pow` e `math.pi`; dependem da libm
  e ficam fora do I3. Ver [ADR-0029](../adr/0029-conversoes-math.md).

- Lambdas: `fn(x) => expr` (corpo de expressão, retorno implícito) e `fn(x) { ... }`
  (bloco com `return`), com `-> Tipo` opcional antes do corpo. São closures sobre o
  ambiente onde foram avaliadas; `this`/`super` são lexicais e `return` volta da lambda.
  Parâmetros seguem as regras de funções, mas **defaults são erro**. `print` de lambda sai
  `<lambda>`. A tipagem está em “Tipos e `--check`”. Ver
  [ADR-0022](../adr/0022-lambdas.md).

## Tipos e `--check`

Anotações de tipo existem na AST, mas o **interpretador as ignora**: tipos são apagados em
runtime. A checagem é opt-in pelo CLI (`--check`), que não executa o programa.

```lox
fn soma(a: Int, b: Int = 10) -> Int {
  return a + b;
}

val x = soma(1);              // Int inferido, sem anotação
val nome: String? = nil;      // String | Nil
val rotulo = nome or "sem nome";  // String (truthy remove Nil)
```

- No `--check`, funções e métodos precisam de anotação em **todos os parâmetros e no
  retorno**; `init` não declara retorno. Parâmetro/campo sem anotação e sem inicializador
  é erro; local sem inicializador também. Lambdas em `val` podem inferir parâmetros e
  generalizar o esquema (T4); `fn` continua contrato explícito. Ver
  [ADR-0033](../adr/0033-inferencia-t3c-t4.md) e [ADR-0034](../adr/0034-t3c-revertido.md).
- Assinaturas de funções de topo são conhecidas **antes** dos corpos: uma função pode
  chamar outra declarada depois, inclusive recursão mútua. O código de topo continua na
  ordem dos statements: chamar uma função antes da declaração dela ainda é erro; métodos e
  campos de classes seguem a ordem da classe. Ver
  [ADR-0020](../adr/0020-assinaturas-explicitas.md).
- Locais e expressões são inferidos: `val x = f()` não precisa de tipo.
- Tipos: `Int`, `Float`, `Bool`, `String`, `Nil`, `Any`, `Never`, `Range`, classes,
  `List[T]`, `Map[K, V]`, tipos de função `fn(Int) -> Int`, uniões `A | B` e `T?`
  (= `T | Nil`). `Int` é non-null. `List[T]` e `Map[K, V]` são invariantes:
  `List[Int]` não é `List[Float]` nem `List[Any]`; `Map[String, Int]` não é
  `Map[String, Any]`.
- Tipos de função: parâmetros são **contravariantes** e o retorno é **covariante**;
  defaults contam como intervalo de aridade. Uma classe (`Animal`) é atribuível à
  assinatura do seu construtor (`fn(String) -> Animal`), mas uma instância (`: Animal`)
  não é. Ver [ADR-0021](../adr/0021-tipos-de-funcao.md).
- Funções genéricas introduzem parâmetros de tipo (`T`, `U`) que podem aparecer em
  `List[T]`, `Map[String, T]`, `fn(T) -> U`, uniões e `T?`. O checker cria uma variável de
  tipo fresca por declaração e resolve a chamada por unificação: argumentos e tipo
  esperado (retorno, `val` anotado, argumento de função) preenchem os `T`. Se sobrar algum
  sem inferência, é erro (`Can't infer type argument(s) 'T'.`). Não há constraints,
  variance declarada, type application explícita nem `T` em chave de `Map` sem constraint;
  `Any` não infere `T`. `val f = fn(x) => x` é generalizado (T4); parâmetro de `fn` continua
  exigindo anotação (T3c rejeitado). No runtime os tipos são apagados; o backend monomorfiza
  ([ADR-0027](../adr/0027-generics-t3b.md), [ADR-0033](../adr/0033-inferencia-t3c-t4.md),
  [ADR-0034](../adr/0034-t3c-revertido.md)).
- Lambdas: `fn(x) => expr` e `fn(x) { ... }`. O corpo de expressão vira retorno
  implícito; o bloco exige `return`. O tipo esperado preenche parâmetros sem anotação
  (`aplicar(fn(x) => x * 2, 3)`); sem contexto, em `val`, os parâmetros são inferidos como
  variáveis de tipo e o esquema é generalizado (`val id = fn(x) => x` serve para `Int` e
  `String`); `var` continua exigindo contexto. O retorno é inferido;
  mistura de `return`s não-nil exige `-> T`; bloco que pode cair no fim acrescenta `Nil`,
  e retorno declarado não-nil exige todos os caminhos. Defaults em parâmetro de lambda são
  erro. `this`/`super` são lexicais e `return` volta da lambda. `print` de lambda sai
  `<lambda>`. Ver [ADR-0022](../adr/0022-lambdas.md).
- Funções genéricas: `fn id[T] (x: T) -> T { ... }`. Os parâmetros de tipo são declarados
  entre o nome e `(` e valem nas anotações e no corpo (`T`, `List[T]`, `Map[String, T]`,
  `fn(T) -> U`). O corpo é checado **uma vez**, sem constraints: só operações universais
  valem (`==`, `str`/`repr`, atribuir, listas/mapas, chamar funções passadas). `a + b` e
  `len(x)` em `T` são erro até existir trait. A chamada infere por unificação dos
  argumentos e do tipo esperado; `id(1)` ⇒ `T = Int`. A inferência é da esquerda para a
  direita: uma lambda antes do argumento que fixa `T` precisa de anotação. Não há
  `id[Int] (1)` nem função genérica como valor (`val f = id` é erro); zero-arg exige
  contexto (`val xs: List[Int] = empty();`). Recursão com os mesmos argumentos de tipo é
  permitida; recursão polimórfica é recusada. Classes/métodos genéricos ainda não existem.
  O runtime apaga `T`; o backend monomorfiza (ADR-0027). Ver
  [ADR-0027](../adr/0027-generics-t3b.md).
- Listas: `[1, 2]` infere `List[Int]`; `[1, 2.0]` infere `List[Float]`; `[]` exige tipo
  esperado; mistura não numérica exige anotação explícita. `push`/`xs[i] = v` checam o
  elemento; `xs[i]` checa que o índice é `Int`; `len` checa lista/string/mapa. `xs.pop()` e
  `xs[i]` devolvem `T`.
- Mapas: `{"a": 1}` infere `Map[String, Int]`; chaves e valores precisam de tipo comum;
  `{}` exige tipo esperado; `m[k]` checa `k` contra `K` e devolve `V`; `m[k] = v` checa
  `v`; `m.get(k)` devolve `V?`; `m.has(k)` devolve `Bool`; `m.remove(k)` devolve `V`;
  `m.keys()`/`m.values()` devolvem `List[K]`/`List[V]`; `for k in m` liga `k: K`; `len(m)`
  é `Int`. Só `String`, `Int`, `Bool` (e uniões desses) são chaves válidas; `Map[Float, V]`
  é erro de tipo.
- Interpolação: cada expressão é checada normalmente e o resultado é `String`; qualquer
  tipo é convertido por `stringify`.
- Promoção só `Int → Float` na checagem; `Float → Int` exigirá cast explícito.
- Funções e métodos com retorno **não-nil** precisam retornar em todos os caminhos no
  `--check` (`Function 'f' must return Int on all paths.`); `return;` nesse caso é erro.
  Tipos nilables, `Any`, `Never` e `<error>` ficam de fora. Ver
  [ADR-0023](../adr/0023-soundness-do-checker.md).
- Erro de chamada identifica o argumento: `Argument 2: Expected String, found Int.`
  Passar a classe onde se espera uma instância é reportado como
  `Expected an instance of Animal, found the class Animal.`
- Condições usam **truthiness** (qualquer tipo); `and`/`or` devolvem o operando. O checker
  tipa `or` como `truthy(A) | B` e `and` como `falsy(A) | B`; `!` devolve `Bool`.
- `expr is T` devolve `Bool` e testa o valor em runtime: primitivos, classe/subclasse,
  `List[T]`/`Map[K, V]` (elementos inclusos; O(n)) e uniões. `Any` sempre verdadeiro,
  `Never` sempre falso; tipos de função são recusados no `--check`. Uma classe como valor
  não é instância (`Animal is Animal` é `false`). Ver
  [ADR-0025](../adr/0025-is-e-narrowing.md).
- Narrowing: `if (x != nil)`, `if (x == nil)`, `if (x)`, `if (x is T)` e `!` em volta disso
  refinam `x` no ramo; `if (x == nil) { return }` refina o resto do bloco. `and` no ramo
  verdadeiro e `or` no ramo falso combinam refinamentos; `while` aplica o refinamento
  verdadeiro ao corpo. `val` e `var` estreitam, mas uma atribuição invalida o refinamento.
  Chamadas/closure que mutam um `var` durante a execução não são rastreadas — prefira `val`
  quando precisar da garantia. **Campos e índices literais** também refinam
  (`p.nome`, `xs[0]`, `m["k"]`); mutar o caminho (`p.nome = ...`) ou a raiz (`p = ...`)
  invalida, e a saída normal de `while (x != nil)` refina o resto do bloco pelo falso.
  Índice dinâmico (`xs[i]`) não refina e mutação via chamada/closure não é rastreada (sem
  aliasing); merge completo em CFG fica fora; ver
  [ADR-0018](../adr/0018-narrowing.md), [ADR-0025](../adr/0025-is-e-narrowing.md) e
  [ADR-0032](../adr/0032-narrowing-campos-indices.md).
- Erros de tipo são de **compilação** e impedem a execução; exit code 65.
- Limitações atuais: merge completo de fluxo em CFG, classes/métodos
  genéricos, inferência de parâmetro sem anotação, tipos de função/casts de união em `is`,
  e cast de união em `as`; lambdas existem, mas sem trailing closure, parâmetro único sem
  parênteses ou retorno implícito de bloco. Anotar `Float` não converte o valor em runtime
  (o tree-walk continua dinâmico).

## Classes

```lox
class Conta {
  var saldo;

  init(saldo) {
    this.saldo = saldo;
  }

  deposita(v) {
    this.saldo = this.saldo + v;
  }
}

class ContaPoupanca(Conta) {
  render() {
    this.saldo = this.saldo * 1.1;
  }
}
```

- `class Nome { campos e métodos }` cria a classe e a liga ao nome no escopo atual.
- `class Nome(Super) { ... }` declara herança simples; `class Nome < Super` é erro.
- Campos são **declarados** no corpo com `val`/`var`; não existem campos dinâmicos:
  `obj.x = 1` em campo não declarado é erro (`Undefined field 'x'.`).
- Todo campo declarado precisa estar inicializado: por inicializador constante
  (`var idade = 0`) ou por atribuição no `init`. Ao fim do `init`, campo não inicializado é
  erro de runtime (`Field 'x' must be initialized.`). No `--check`, todo campo sem
  inicializador precisa ser atribuído em **todos os caminhos** do `init`; `if`/`else` usa
  interseção, `return` antecipado exige os campos prontos e laços não contam como
  atribuição definitiva. Ver [ADR-0023](../adr/0023-soundness-do-checker.md).
- `val` campo só pode ser atribuído **dentro do `init`** (e uma vez); fora dele o resolver
  reporta `Can't assign to immutable field 'x'.` e o runtime também recusa uma segunda
  atribuição. `var` campo é mutável em qualquer método.
- Campo e método com o mesmo nome, ou campo redeclarado (inclusive na subclasse), é erro de
  compilação (`Field 'x' already declared.`).
- Inicializadores de campo são constantes na v1 e rodam na criação da instância, antes do
  `init`.
- Métodos **não** usam `fn`; são funções com `this` ligado.
- `this` é **implícito**: métodos não recebem `self`.
- `Nome(args)` cria instância, executa `init` (se existir) e devolve a instância.
  A aridade da classe é o intervalo do `init` (0 se não houver).
- `init` devolve sempre a instância: `return;` é permitido, `return valor;` é erro de
  compilação (`Can't return a value from an initializer.`).
- `this` só existe dentro de métodos; fora de classe é erro de compilação
  (`Can't use 'this' outside of a class.`).
- Campos têm prioridade sobre métodos na leitura.
- Ler propriedade que não é campo nem método: `Undefined property 'x'.`
- `obj.campo = v` exige instância: `Only instances have fields.`
- Ler propriedade de não-instância: `Only instances have properties.`
- Método lido como valor continua ligado à instância (`var f = obj.m; f();`).

### Classes genéricas

```lox
class Box[T] {
  var value: T
  init(value: T) { this.value = value }
  get() -> T { return this.value }
}

val b: Box[Int] = Box(1)   # Box(1) infere Box[Int]
print b.get()              # 1
```

- `class Box[T]` e `class Pair[A, B]`: `T` vale em campos, métodos, `init` e `this`; o tipo
  é `Box[Int]`, `Pair[Int, String]` etc. (`T?`, `List[T]` e aninhamento funcionam).
- `Box(1)` infere os argumentos pelo `init`; com tipo esperado (`val b: Box[Int] = Box()`),
  o esperado fixa os argumentos. Sem `init` e sem esperado, é erro pedindo anotação.
  `Box` sem argumentos em posição de tipo é erro de aridade.
- Os argumentos são **invariantes**: `Box[Int]` não é `Box[Any]` nem `Box[Float]`
  (campos mutáveis tornariam a covariância unsound). `Any` como argumento de inferência
  também é recusado: `Box(x)` com `x: Any` pede anotação.
- `this` é `Box[T]` e `init` devolve `Box[T]`; o runtime apaga `T` (`print Box(1)` →
  `Box instance`).
- Fora do MVP: métodos genéricos (`fn map[U]`), herança de `Box[Int]`, constraints,
  type application explícita (aplicar argumentos à chamada) e `is`/`as Box[Int]`
  (recusados com mensagem
  explícita). Ver [ADR-0040](../adr/0040-generics-classes-desenho.md).

### Herança

- Sintaxe: `class B(A)` (herança simples; sem `extends`, `:` ou `<`).
- Métodos e `init` são herdados; o método da subclasse **sobrescreve** o da superclasse
  silenciosamente (não há keyword `override`). No `--check`, a assinatura do override é
  comparada com a da superclasse: parâmetros contravariantes, retorno covariante e defaults
  como intervalo de aridade; `init` fica de fora. Ver
  [ADR-0023](../adr/0023-soundness-do-checker.md).
- Subclasse **sem** `init` herda o `init` da superclasse. Se a subclasse define `init`, ela
  deve chamar `super.init(...)` explicitamente; não há chamada automática.
- Campos são herdados; redeclarar um campo na subclasse é erro. `val` herdado não pode ser
  reatribuído (nem no `init` da subclasse); `var` herdado pode.
- Inicializadores de campo da superclasse rodam na criação da instância, antes do `init`.
- `super.metodo(args)` busca `metodo` na superclasse e o liga ao `this` atual (não ao
  "this da superclasse").
- `super` só pode aparecer dentro de método de classe **com** superclasse:
  - fora de classe → `Can't use 'super' outside of a class.`
  - classe sem superclasse → `Can't use 'super' in a class with no superclass.`
- Herdar de si mesma → erro de compilação: `A class can't inherit from itself.`
- Superclasse precisa ser classe em runtime: `Superclass must be a class.`
- `super.metodo` inexistente → `Undefined property 'metodo'.`

## Enums e match

```lox
enum Cor { Vermelho, Verde, Azul }
enum Shape { Circle(Float), Rect(Float, Float) }

val s: Shape = Shape.Circle(2.0)
val area = match s {
  Shape.Circle(r) => 3.14 * r * r
  Shape.Rect(w, h) => w * h
}
```

- `enum Nome { Variante, Variante(Tipo, ...) }` declara um tipo fechado; variantes têm
  payload **posicional** e são acessadas com namespace (`Cor.Verde`,
  `Shape.Circle(1.0)`). Enums são declarados no topo do programa.
- Enums podem ser genéricos (`enum Pair[A, B]`); `Result[T, E]` é embutido, com
  `Result.Ok(T)`/`Result.Err(E)`, e não pode ser redefinido. `Option` continua sendo `T?`.
- Tipo: `Shape`, `Result[Int, String]`; argumentos são invariantes. `is`/`as` aceitam enum
  sem argumentos (`x is Cor`); com argumentos são recusados (runtime apaga `T`).
- `match` é **expressão**: `match e { Padrão => expr ... }`. Padrões da v1:
  `Nome.Variante`, `Nome.Variante(a, b)` (bindings posicionais) e `_`. Arms são separados
  por linha, `;` ou `,`; usar `match` como statement é descartar o resultado.
- Exaustividade é **obrigatória**: todas as variantes cobertas ou `_`; faltante é erro
  (`Non-exhaustive match; missing Shape.Rect.`); variante duplicada/arm depois de `_` é
  `Unreachable match arm.` O scrutinée precisa ser um enum (não `Any`/união).
- Os bindings do padrão têm o tipo do payload (`Result.Ok(v)` → `v: T`); o tipo do `match`
  é a união dos arms. Sem `--check`, um `match` sem arm que case é erro de runtime
  (`No match arm matched.`).
- Igualdade é estrutural (enum, variante e payload); `print Cor.Verde` →
  `Cor.Verde`, `print Shape.Circle(1.0)` → `Shape.Circle(1.0)`. Enums não são iteráveis,
  não têm `len` e não são chave de `Map`.
- Fora da v1: padrões literais/`nil`, guards, aninhamento, `|`, `match` sobre uniões e
  variantes nulas de enum genérico. O backend rejeita `enum`/`match` até o L6.

## Exceções

```lox
class MyError(Exception) {
  init(msg: String) { this.message = msg }
}

try {
  raise MyError("falhou")
} except MyError as e {
  print "meu: ${e.message}"
} except LoxRuntimeError as e {
  print "runtime: ${e.message}"
} finally {
  print "sempre"
}
```

- `Exception` é a base embutida; `LoxRuntimeError` é subclasse embutida e representa
  qualquer erro de runtime (divisão por zero, índice etc.). O usuário pode declarar
  `class MyError(Exception)` com `message`.
- `raise Expr` exige instância de `Exception`; `raise;` dentro de `except` relança a
  exceção corrente. Fora de `except`, `raise;` é erro.
- `try` é statement; `except Tipo as e` é tipado, múltiplo e avaliado em ordem;
  `except Exception as e` é catch-all e precisa ser o último. Pelo menos um `except` ou
  `finally` é obrigatório.
- Erros de runtime são convertidos para `LoxRuntimeError` no `try`; capturar tipos
  específicos (`DivisionByZero`) fica para depois. `finally` sempre roda e seu
  `return`/`raise` vence o fluxo anterior.
- Exceção não capturada: `Unhandled exception: <tipo>: <msg>` + `[line N]`, exit 70.
  Sem stack trace; o backend rejeita `try`/`raise` até o L6.

## Erros

| Fase | Quando | Exit code (arquivo) |
| --- | --- | --- |
| léxico/sintaxe/resolver | antes de executar | **65** |
| runtime | durante a execução | **70** |
| arquivo não encontrado | antes de tudo | **66** |

- Formato de compilação: `[line N] Error at 'token': mensagem` (ou `at end`).
- Formato de runtime: `mensagem` + `[line N]`.
- Mensagens são em inglês (compatibilidade com o livro e testes).
- Erros de compilação são **acumulados** (parser tenta se recuperar; resolver reporta todos);
  erros de runtime param no primeiro.
- Ainda **não há** colunas, spans, stack trace, códigos de erro nem JSON — plano em
  [`../../TODO.md`](../../TODO.md) §3.1.
- No REPL, cada linha começa com estado de erro limpo e o ambiente permanece.

## Diferenças conscientes em relação ao livro

- Divisão por zero é erro (o livro devolve `inf`).
- O REPL aceita `;` final opcional e imprime o valor de expressões.
- `return` no topo é erro de compilação já no cap. 11 (no livro, o resolver faz isso).
- Números são `Int` e `Float` separados (o livro usa só `float`); `/` é sempre `Float`,
  `%` é truncado e `Int` faz wrapping — ver [ADR-0006](../adr/0006-int-float-separados.md).
- `val`/`var` não existem no livro (que só tem `var` mutável); ver [ADR-0005](../adr/0005-val-var-imutabilidade.md).
- `for x in` e `Range` (`0..10`) não existem no livro; ver
  [ADR-0007](../adr/0007-ranges-e-iteracao.md).
- `List[T]` (literal, indexação, `push`/`pop`, `len` e igualdade estrutural) não existe no
  livro; ver [ADR-0015](../adr/0015-listas-tipadas.md).

Tudo o mais segue o jlox do livro, inclusive as mensagens.
