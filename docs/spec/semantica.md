# Semântica

Comportamento observável do interpretador. Implementação: [`src/interpreter.py`](../../src/interpreter.py),
[`src/resolver.py`](../../src/resolver.py), [`src/environment.py`](../../src/environment.py),
[`src/lox_function.py`](../../src/lox_function.py), [`src/lox_class.py`](../../src/lox_class.py),
[`src/lox_instance.py`](../../src/lox_instance.py), [`src/values.py`](../../src/values.py).

## Execução

Um programa é uma lista de declarações executadas **em ordem**. Um erro de compilação
(léxico, sintaxe ou resolver) impede a execução inteira. Um erro de runtime interrompe o
programa no ponto em que ocorreu; o que já foi impresso permanece.

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
| função nativa | `clock` | `<native fn>` |
| classe | `class` | nome da classe |
| instância | chamada de classe | `Nome instance` |

Números são **`Int` (i64) ou `Float` (f64)** — [ADR-0006](../adr/0006-int-float-separados.md).
`print 3;` mostra `3` e `print 3.0;` mostra `3.0`: o tipo vem do literal. As regras
completas estão neste documento e no ADR; pendências em
[`../../TIPOS.md`](../../TIPOS.md) §3.

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
| `-` | número | negação (em `Int`, com wrapping) |
| `~` | `Int` | complemento de 64 bits (`~x == -x - 1`) |
| `+` | dois números **ou** duas strings | soma com promoção / concatenação |
| `-` `*` | dois números | aritmética com promoção; `Int` faz wrapping |
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

- `Int op Float` promove o `Int` para `Float` (`1 + 2.0` → `3.0`); `Float → Int` nunca é
  implícito.
- `+` **não** mistura número e string: `Operands must be two numbers or two strings.`
- Comparações relacionais são só numéricas: `Operands must be numbers.`
- Divisão por zero é **erro de runtime** (`Division by zero not allowed`), para `Int` e
  `Float` — decisão nossa, diferente do livro (que devolveria `inf`/`NaN`).
- Resto por zero também é erro de runtime (`Modulo by zero not allowed`).
- `%` segue C/LLVM: `-7 % 3` → `-1` (sinal do dividendo), não `2`.
- `//` também é truncado (`-7 // 2` → `-3`); com `%`, vale
  `a == (a // b) * b + (a % b)`. Overflow de `INT_MIN // -1` faz wrap.
- `**`: `2 ** 3` → `Int` 8; `2 ** -1` é erro (`Negative exponent not allowed for integer
  power.`); use `2.0 ** -1` para `0.5`. `2 ** 63` faz wrap para `INT_MIN`. Expoente
  negativo em `Float` é permitido; domínio/overflow inválido é erro.
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
  (`Map keys must be strings, integers or booleans.`).
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
| `for x in e s` | itera `e` (Range/String/List/Map hoje); `x` é `val` por iteração |
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
- `clock()` devolve segundos desde a época como `float`, aridade 0.
- `len(x)` aceita `List`, `Map` ou `String`; devolve `Int` (O(1) para lista/mapa, code
  points para string). Outro tipo é erro:
  `len() expects a string, a list or a map.`
- `str(x)` devolve a forma de exibição (string no topo sem aspas); `repr(x)` devolve a forma
  de debug (string citada/escapada). Ambas aceitam qualquer valor, têm aridade 1 e devolvem
  `String`; em listas as duas usam a mesma formatação hoje. Builtins globais são
  imutáveis: redefinir `len`/`str`/`repr`/`clock`/`range` no escopo global é erro; local e
  parâmetro podem sombrear.
- `range(start, end, step)` é nativa de aridade 3 e exige `Int`; devolve `Range`.
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
  é erro; local sem inicializador também.
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
  não é. Generics ainda não existem; ver [ADR-0021](../adr/0021-tipos-de-funcao.md).
- Lambdas: `fn(x) => expr` e `fn(x) { ... }`. O corpo de expressão vira retorno
  implícito; o bloco exige `return`. O tipo esperado preenche parâmetros sem anotação
  (`aplicar(fn(x) => x * 2, 3)`); sem contexto, anotar é obrigatório. O retorno é inferido;
  mistura de `return`s não-nil exige `-> T`; bloco que pode cair no fim acrescenta `Nil`,
  e retorno declarado não-nil exige todos os caminhos. Defaults em parâmetro de lambda são
  erro. `this`/`super` são lexicais e `return` volta da lambda. `print` de lambda sai
  `<lambda>`. Ver [ADR-0022](../adr/0022-lambdas.md).
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
- Narrowing: `if (x != nil)`, `if (x == nil)`, `if (x)` e `!` em volta disso refinam `x`
  no ramo; `if (x == nil) { return }` refina o resto do bloco. `val` e `var` estreitam, mas
  uma atribuição invalida o refinamento. Chamadas/closure que mutam um `var` durante a
  execução não são rastreadas — prefira `val` quando precisar da garantia. `is T`, loops,
  `and`/`or` e campos/índices ainda **não** refinam; ver
  [ADR-0018](../adr/0018-narrowing.md).
- Erros de tipo são de **compilação** e impedem a execução; exit code 65.
- Limitações atuais: narrowing completo (`is T`, loops, `and`/`or`), generics de verdade,
  inferência de parâmetro sem anotação e `as`; lambdas existem, mas sem trailing closure,
  parâmetro único sem parênteses ou retorno implícito de bloco. Anotar `Float` não converte
  o valor em runtime (o tree-walk continua dinâmico).

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
