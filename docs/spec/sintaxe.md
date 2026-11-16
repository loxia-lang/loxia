---
sources:
  - loxia_core/frontend/parser.py
  - loxia_core/frontend/keywords.py
  - loxia_core/frontend/ast_printer.py
---

# Sintaxe

Gramática do parser atual ([`loxia_core/frontend/parser.py`](../../loxia_core/frontend/parser.py)) — recursive descent,
uma função por nível de precedência.

> Isto é o **Lox implementado**. A sintaxe alvo da linguagem própria
> (`break`/`continue`, por exemplo) está em [`../../TODO.md`](../../TODO.md) §1.
> `fn`, `elif`, o `;` opcional, ternário, `??`, `?.`, interpolação, escapes, `not`,
> destructuring aninhado, `"""` e raw strings já existem; `val`/`var` existem desde o
> ADR-0005.


Trailing comma é aceito (e canônico no formatter) em parâmetros, chamadas,
listas, mapas e tuplas **quando a construção é multiline**; enums e `match` continuam
sem vírgula final.

## Gramática (EBNF)

```ebnf
program        → declaration* EOF ;

declaration    → classDecl
               | interfaceDecl
               | typeAliasDecl
               | enumDecl
               | funDecl
               | varDecl
               | valDecl
               | statement ;

classDecl      → "class" IDENTIFIER typeParameters? ( "(" IDENTIFIER ")" )?
                 ( "implements" IDENTIFIER ( "," IDENTIFIER )* )? "{" classMember* "}" ;
interfaceDecl  → "interface" IDENTIFIER "{" interfaceMember* "}" ;
typeAliasDecl  → "type" IDENTIFIER "=" type terminator ;
interfaceMember → "fn"? IDENTIFIER "(" parameters? ")" ( "->" type )? ( block | terminator ) ;
enumDecl       → "enum" IDENTIFIER typeParameters? "{" variant ( "," variant )* "}" ;
variant        → IDENTIFIER ( "(" type ( "," type )* ")" )? ;
classMember    → fieldDecl | "fn"? function ;
fieldDecl      → ( "val" | "var" ) IDENTIFIER ( ":" type )? ( "=" expression )? terminator ;
funDecl        → "fn" function ;
function       → IDENTIFIER functionTypeParameters? "(" parameters? ")" ( "->" type )? block ;
typeParameters → "[" IDENTIFIER ( "," IDENTIFIER )* "]" ;
functionTypeParameters → "[" typeParameter ( "," typeParameter )* "]" ;
typeParameter  → IDENTIFIER ( ":" constraint ( "+" constraint )* )? ;
constraint     → IDENTIFIER ;
parameters     → parameter ( "," parameter )* ;
parameter      → "var"? "..."? IDENTIFIER ( ":" type )? ( "=" expression )? ;

varDecl        → "var" ( IDENTIFIER ( ":" type )? ( "=" expression )?
               | destructure ( ":" type )? "=" expression ) terminator ;
valDecl        → "val" ( IDENTIFIER ( ":" type )? "=" expression
               | destructure ( ":" type )? "=" expression ) terminator ;

destructure    → "(" pattern ( "," pattern )+ ")" ;
pattern        → IDENTIFIER | destructure ;   (* recursivo: (a, (b, c)) *)

type           → unionType ;
unionType      → postfixType ( "|" postfixType )* ;
postfixType    → primaryType ( "?" )* ;
primaryType    → IDENTIFIER ( "[" type ( "," type )* "]" )?
               | "(" type "," type ( "," type )* ")"   (* tupla *)
               | "(" type ")" ;

statement      → exprStmt
               | forStmt
               | ifStmt
               | returnStmt
               | whileStmt
               | tryStmt
               | raiseStmt
               | block ;

terminator     → ";"? ;   (* ver “Ponto e vírgula opcional” *)

exprStmt       → expression terminator ;
forStmt        → "for" "(" ( varDecl | valDecl | exprStmt | ";" )
                 expression? ";"
                 expression? ")" statement
               | "for" IDENTIFIER "in" expression statement ;
ifStmt         → "if" "(" expression ")" statement
                 ( "elif" "(" expression ")" statement )*
                 ( "else" statement )? ;
returnStmt     → "return" expression? terminator ;
whileStmt      → "while" "(" expression ")" statement ;
tryStmt        → "try" block ( "except" IDENTIFIER "as" IDENTIFIER block )*
                 ( "finally" block )? ;
raiseStmt      → "raise" expression? terminator ;
block          → "{" declaration* "}" ;

expression     → assignment ;
assignment     → conditional ( "=" assignment )? ;   (* alvo: variável, propriedade ou índice *)
conditional    → coalesce ( "if" coalesce "else" conditional )? ;
coalesce       → logic_or ( "??" coalesce )? ;
logic_or       → logic_and ( "or" logic_and )* ;
logic_and      → equality ( "and" equality )* ;
equality       → comparison ( ( "!=" | "==" ) comparison )* ;
comparison     → bitwise_or ( ( ">" | ">=" | "<" | "<=" ) bitwise_or | "is" postfixType )* ;
bitwise_or     → bitwise_xor ( "|" bitwise_xor )* ;
bitwise_xor    → bitwise_and ( "^" bitwise_and )* ;
bitwise_and    → range ( "&" range )* ;
range          → shift ( ( ".." | "..=" ) shift )* ;
shift          → term ( ( "<<" | ">>" | ">>>" ) term )* ;
term           → factor ( ( "-" | "+" ) factor )* ;
factor         → unary ( ( "*" | "/" | "//" | "%" ) unary )* ;
unary          → ( "not" | "-" | "~" ) unary | power ;
power          → call ( "**" unary )? ;
call           → primary ( "(" arguments? ")" | "." IDENTIFIER | "?." IDENTIFIER
                 | "[" expression "]" )* ;
arguments      → ( expression ( "," expression )* ( "," spread )? ) | spread ;
spread         → "..." expression ;
primary        → "true" | "false" | "nil" | "this"
               | NUMBER | STRING | INTERPOLATED_STRING | IDENTIFIER
               | "(" expression ( "," expression )+ ")"   (* tupla *)
               | "(" expression ")"
               | "super" "." IDENTIFIER
               | "[" ( expression ( "," expression )* )? "]"
               | "{" ( expression ":" expression
                       ( "," expression ":" expression )* )? "}"
               | matchExpr
               | lambda ;
matchExpr      → "match" expression "{" matchArm+ "}" ;
matchArm       → pattern "=>" expression ;
pattern        → "_" | IDENTIFIER "." IDENTIFIER
                 ( "(" IDENTIFIER ( "," IDENTIFIER )* ")" )? ;
lambda         → "fn" "(" parameters? ")" ( "->" type )? ( "=>" expression | block ) ;
```

`try` exige pelo menos um `except`/`finally`; `raise` sem expressão só dentro de
`except` (relança). `except Exception as e` é o catch-all e deve ser o último.

`enum` declara variantes namespaced (`Cor.Verde`, `Shape.Circle(1.0)`); `match` é
expressão e exige enum exaustivo (ver [`semantica.md`](semantica.md)). `Result` é um enum
embutido com `Ok(T)`/`Err(E)`.

`INTERPOLATED_STRING` é o literal `"texto ${expressão} mais texto"`; a expressão é qualquer
`expression` e pode conter outra string interpolada. `\${` e `\$` escapam o cifrão.

Defaults de parâmetro e inicializadores de campo são **constantes na v1** (literal,
`nil`, `true`/`false`, `-` de literal numérico ou parênteses em torno disso). Parâmetros
obrigatórios vêm antes dos opcionais; campos podem aparecer antes ou depois dos métodos.

Anotações de tipo são opcionais para o interpretador (que as ignora); no modo `--check`
as funções precisam de anotações em todos os parâmetros e no retorno (lambdas em `val`
podem inferir e generalizar; ver T4). `T?` é açúcar para
`T | Nil`; `Int` é non-null. `List[T]` e `Map[K, V]` são os únicos genéricos: o nome é
capitalizado, `List`/`Map` sem argumentos é erro e `list[int]`/`map[...]` também (com
sugestão de capitalização). Em `Map[K, V]`, `K` precisa ser `String`, `Int`, `Bool` (ou
união desses); `Map[Float, V]`, `Map[List[T], V]` etc. são erro de tipo.

Tipos de função são escritos `fn(Int, String) -> Bool`; `fn()` não tem parâmetros. A seta
liga ao tipo de retorno, então `fn(Int) -> Int | Nil` devolve `Int | Nil`. Para a própria
função ser opcional, use parênteses: `(fn(Int) -> Int)?`. Ver
[ADR-0021](../adr/0021-tipos-de-funcao.md).

Lambdas usam `fn` em posição de expressão:

```
lambda := "fn" "(" params? ")" ("->" type)? ( "=>" expression | block )
```

```lox
val dobro = fn(x: Int) => x * 2
val soma = fn(a: Int, b: Int) { return a + b }
aplicar(fn(x) => x * 2, 3)
```

`=>` introduz corpo de expressão (o valor é o retorno); `{ ... }` introduz bloco com
`return` explícito. `-> Tipo` é opcional antes de qualquer corpo. Parâmetros seguem as
regras de funções, **menos defaults** (`fn(x: Int = 1) => ...` é erro). `fn(` em expressão
é lambda; `fn nome(` é declaração. Ver [ADR-0022](../adr/0022-lambdas.md).

Type aliases são declarações top-level com `type` **contextual** (não é palavra-chave):

```lox
type UserId = Int
type Nomes = List[String]
type Callback = fn(Int) -> Int
```

O alvo usa a gramática normal de tipos, pode referenciar classes/interfaces/enums/aliases
declarados antes ou depois e não pode ser genérico (`type BoxAlias[T] = ...` é erro). O
alias é transparente: `UserId` e `Int` são o mesmo tipo em anotações, `is`/`as` e no
backend. Ver [ADR-0039](../adr/0039-decisoes-tipos-pendentes.md) e
[ADR-0084](../adr/0084-type-alias.md).

Funções genéricas declaram parâmetros de tipo entre o nome e `(`:

```lox
fn id[T] (x: T) -> T { return x; }
fn map[T, U] (xs: List[T], f: fn(T) -> U) -> List[U] { ... }
```

`T`/`U` são nomes comuns (ASCII), válidos em `: T`, `-> T`, `List[T]`, `Map[String, T]`,
`fn(T) -> U` e no corpo. Não há type application explícita: `id(1)` infere `T = Int`;
`id[Int] (1)` **não** existe. Chamadas sem argumento/contexto que permitam inferir todos os
`T` são erro.

Funções genéricas podem declarar **constraints** depois de `:`, unidas por `+`:

```lox
fn max[T: Ord] (a: T, b: T) -> T { ... }
fn juntas[T: A + B] (x: T) -> String { ... }
```

`Ord` e `Num` são constraints embutidas; nomes de interface também valem. Na v1 só
funções aceitam bounds: `class C[T: Ord]` e `enum E[T: Ord]` são erro de parser
(`Constraints on class type parameters aren't supported yet.`). Classes genéricas
(`class Box[T]`) existem e inferem os argumentos no construtor; métodos com `[T]`
continuam recusados no `--check`. Herança de classe genérica (`class C(Box[Int])`) ainda
não existe. Ver [ADR-0027](../adr/0027-generics-t3b.md),
[ADR-0040](../adr/0040-generics-classes-desenho.md) e
[ADR-0081](../adr/0081-constraints-generics.md).

`expr is Tipo` é uma expressão booleana; o lado direito usa a gramática de tipos e o
operador fica no nível de comparação. `is` testa primitivos, classes/subclasses,
`List[T]`/`Map[K, V]` (elementos inclusos) e uniões; tipos de função são recusados no
`--check`. `Animal` como valor não é instância: `Animal is Animal` é `false`. Ver
[ADR-0025](../adr/0025-is-e-narrowing.md).

Em **contexto de expressão** a união exige parênteses: `x is (Int | String)` é válido,
mas `x is Int | String` é erro de sintaxe. O `|` é também o operador bitwise; sem o
parêntese o parser não sabe se ele pertence ao tipo ou à expressão. Anotações
(`val x: Int | String`, `-> Int | String`) continuam sem parênteses, porque ali não
existe expressão concorrente. `as` segue a mesma gramática de tipo; união em `as` é
recusada pelo checker (`as doesn't support union types`), não pelo parser.

O literal de mapa só existe em **posição de expressão** (`val m = {...}`, argumento,
`return`, condição). No início de um statement, `{` abre um **bloco**:

```lox
val m = {"a": 1}    # mapa
{ "a": 1 }          # bloco: o ':' não é um statement válido
```

No segundo caso o parser reporta um erro dirigido (`Unexpected ':'. Map literals can't
start a statement...`) em vez do genérico `Expect ';' after expression.`

## Ponto e vírgula opcional

`;` termina statements e campos, mas pode ser omitido quando o próximo token começa em
outra linha, no EOF ou num `}` de fechamento. Duas instruções na mesma linha ainda exigem
`;`.

```lox
val a = 1
var b = 2
print(a + b)

val c = 1; val d = 2

if (ok) { print("um") }     # `}` fecha o statement: `;` é opcional antes da chave
```

Para continuar uma expressão na linha seguinte, deixe o **operador no fim** da linha:

```lox
val total = 1 +
  2            # ok: 3
```

Dentro de `()`, `[]` e `{}` de expressão o operador também pode **começar** a linha,
porque ali não existe um statement novo para iniciar:

```lox
val total = (
  1
  + 2          # ok: 3
)
```

Fora de brackets, operador no começo da linha seguinte **não** continua a expressão; ele
inicia outro statement:

```lox
var x = 1
-2             # statement separado; x continua 1
```

`return` sozinho no fim da linha devolve `nil`; para retornar um valor, mantenha-o na
mesma linha do `return` (antes de `;`, `}` ou de outra linha, não precisa de `;`). Uma chamada com `(` precisa começar na mesma linha do callee;
quebrar antes de `.` é permitido (encadeamento de propriedades). Os `;` do cabeçalho do
`for` C-style continuam obrigatórios.

`elif` é açúcar para `else if`, com a mesma exigência de parênteses na condição:

```lox
if (n < 0) print("negativo")
elif (n == 0) print("zero")
else print("positivo")
```

## Precedência e associatividade

Do menor para o maior:

| Nível | Operadores | Associatividade |
| --- | --- | --- |
| atribuição | `=` | direita |
| condicional | `a if c else b` | direita no `else` |
| coalescência | `??` | direita |
| or | `or` | esquerda |
| and | `and` | esquerda |
| igualdade | `==` `!=` | esquerda |
| comparação | `<` `<=` `>` `>=` `is T` | esquerda |
| or de bits | `\|` | esquerda |
| xor de bits | `^` | esquerda |
| and de bits | `&` | esquerda |
| range | `..`, `..=` | esquerda |
| shift | `<<` `>>` `>>>` | esquerda |
| termo | `+` `-` | esquerda |
| fator | `*` `/` `//` `%` | esquerda |
| cast | `as T` | esquerda |
| unário | `not` `-` `~` | direita |
| potência | `**` | direita; lado direito aceita unário |
| chamada | `()` `.` `?.` `[ ]` | encadeia à esquerda |
| primário | literais, `this`, `super.x`, `( … )`, `[ … ]` | — |

`**` é o caso especial: `-2 ** 2` é `-(2 ** 2)` (potência liga mais forte que o sinal
unário à esquerda), mas `2 ** -1` é permitido. Os operadores de bits ligam mais forte que
`==`/`!=`/comparações, então `flags & MASK == 0` é `(flags & MASK) == 0`; shifts ficam
abaixo de `+`/`-`, como no C.

`as` liga mais forte que `*` e mais fraco que unário: `-x as Int` é `(-x) as Int` e
`x as Int + 1` é `(x as Int) + 1`. O lado direito é um `type`; `as Int | String` é cast
para a união (hoje recusado), não um `|` bitwise. Ver
[ADR-0029](../adr/0029-conversoes-math.md).

Consequências:
- `-a.b()` = `-(a.b())` — a chamada liga mais forte que o unário;
- `a = b = c` atribui da direita para a esquerda;
- `a or b and c` = `a or (b and c)`;
- `not a == b` = `(not a) == b` — `not` liga mais forte que `==` (ADR-0068);
- `0..1 + 2` = `0..(1 + 2)` — o termo liga mais forte que o range; `..=` tem a mesma
  precedência de `..`;
- `0..n < 5` = `(0..n) < 5` — range liga mais forte que a comparação;
- `a ?? b or c` = `a ?? (b or c)`;
- `a ?? b if c else d` = `(a ?? b) if c else d`;
- `a?.b.c` protege só `a`; `a?.b?.c` protege os dois;
- `a?.b = c` é erro (não há assignment opcional);
- `xs[0]` indexa e `xs[0] = v` atribui; o `[` precisa estar na **mesma linha** da
  expressão anterior, como o `(` de chamada;
- `(1, 2)` é literal de tupla (2+ elementos; `(1)` continua agrupamento e `(1,)` é erro);
  `(1, 2,)` aceita vírgula final. `f(1, 2)` são dois argumentos; para uma tupla como
  argumento, `f((1, 2))`. `val (a, b) = t` e `var (c, d) = t` desestruturam (anotação
  opcional); o padrão aninha em qualquer profundidade (`val (a, (b, c)) = t`), com
  anotação recursiva `(Int, (String, Bool))` ([ADR-0069](../adr/0069-destructuring-aninhado.md)).
- `[1, 2]` é literal de lista e `[]` é a lista vazia; vírgula final (`[1,]`, `[1, 2,]`)
  é aceita, e o formatter só a insere em construções multiline.

`<` é **só** comparação. Herança usa parênteses após o nome da classe
(`class B(A)`), com uma única superclasse; `class B < A` é erro de sintaxe. A superclasse
não pode ser genérica (`class C(Box[Int])` é erro); classe genérica pode herdar de classe
não genérica.

Interfaces são nominais e usam `implements` **contextual** depois do cabeçalho da classe
([ADR-0080](../adr/0080-interfaces-nominais-implementacao.md)):

```lox
interface Forma {
  area() -> Float                 # abstrato: sem corpo
  fn nome() -> String {           # default: com corpo; `fn` é opcional
    return "forma"
  }
}

class Circulo implements Forma { ... }
class Triangulo(Figura) implements Forma, Desenhavel { ... }
```

- `interface` é palavra-chave e a declaração é **top-level**.
- O corpo só aceita métodos; `init`, campos e `static` são recusados. Método sem `{` é
  assinatura abstrata e termina pela regra normal de `;` opcional (fim de linha, `}` ou
  EOF); método com `{ ... }` é default.
- `implements` só é especial no cabeçalho da classe; em qualquer outro lugar continua
  identificador (`val implements = 1` funciona).
- Sem interfaces genéricas (`interface I[T]`), sem herança de interface (`interface A : B`)
  e sem `class C(A, I)`.

## Açúcar sintático

### `for` C-style vira `while`

Não existe nó para o `for` C-style na AST. O parser desaçucara:

```lox
for (var i = 0; i < 3; i = i + 1) print(i);
```

vira

```lox
{
  var i = 0;
  while (i < 3) {
    print(i);
    i = i + 1;
  }
}
```

Por isso o `for` tem as mesmas regras de escopo de um bloco e uma condição omitida vira
`true` (laço infinito).

O `for-in` é diferente: vira o nó `ForIn(name, iterable, body)` e **não** desaçucara para
`while`, porque o interpretador precisa reportar "não iterável" e o codegen precisa do laço
por iterável (Range/String/List/Map/Tuple — `Map` produz as chaves). Ver
[`semantica.md`](semantica.md#ranges-e-for-in).

### Blocos

`{ … }` é um statement; expressões não têm bloco (o `{` de expressão é literal de mapa).
`if`/`while` recebem **um** statement (por isso as chaves quando há mais de uma instrução).

## Pontos finos

- **Ponto e vírgula é opcional** no fim da linha, no EOF ou antes de um `}` de fechamento
  (ADR-0011); duas instruções na mesma linha ainda exigem `;`. No REPL, o `;` final pode ser
  omitido quando a entrada termina (`_end_statement`).
- `val` **exige inicializador** (`val x;` é erro). `var` pode omitir (`var x;` → `nil`).
- Parâmetros são **`val` implícitos**; `var` antes do nome libera a reatribuição:
  `fn f(x, var y)`. `val` explícito em parâmetro não é aceito.
- Métodos de classe aceitam `fn` **opcional**; a forma canônica continua sem `fn`, porque
  o corpo da classe já marca a declaração:

  ```lox
  class Foo {
    bar(a) { return a; }
    fn baz(a) { return a; }   # aceito; mesma AST
  }
  ```

### Imports

```lox
import std.lists
import dtos.dtoA as dto
from std.strings import trim
from dtos.dtoA import DtoA as Dto
```

- `import caminho [as alias]` liga o último segmento (ou o alias) como namespace.
- `from caminho import nome [as alias] [, nome ...]` liga nomes públicos.
- Imports só no topo, antes de qualquer outro statement; sem `*`, sem reexportação.
- Caminho são identificadores separados por `.`; `std` é root reservado.
- Módulo é arquivo `.lx`; pasta é só namespace (sem `__init__`/`index`).
- Módulo não é valor: `val m = std.lists` é erro.

- Limites do parser: no máximo **255 argumentos** por chamada e **255 parâmetros** por
  função. Ao ultrapassar, o erro é reportado mas o parser continua (os argumentos são
  descartados da AST).
- `this` e `super` são palavras-chave: `super` só aparece como `super.metodo`.
- Não existem: `break`/`continue`, `switch` (use `match`), operador ternário no estilo
  `?:` (use `a if c else b`), `+=`, `++` e `catch` (use `except`). `match` com
  enums ([ADR-0041](../adr/0041-enums-match.md)) e lambdas ([ADR-0022](../adr/0022-lambdas.md))
  existem; listas, mapas e interpolação existem desde os
  [ADR-0015](../adr/0015-listas-tipadas.md), [ADR-0017](../adr/0017-mapas-hash.md) e
  [ADR-0019](../adr/0019-interpolacao.md).
- `fn` pode aparecer em qualquer posição de declaração, inclusive dentro de bloco.
