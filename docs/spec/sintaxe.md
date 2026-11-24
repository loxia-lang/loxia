---
sources:
  - loxia_core/frontend/parser.py
  - loxia_core/frontend/keywords.py
  - loxia_core/frontend/ast_printer.py
  - loxia_core/loader/manifest.py
---

# Syntax

Grammar of the current parser ([`loxia_core/frontend/parser.py`](../../loxia_core/frontend/parser.py)) — recursive descent,
one function per precedence level.

> This is the **implemented Lox**. The target syntax of the language itself
> (`break`/`continue`, for example) is tracked in [`../roadmap.md`](../roadmap.md).
> `fn`, `elif`, the optional `;`, ternary, `??`, `?.`, interpolation, escapes, `not`,
> nested destructuring, `"""` and raw strings already exist; `val`/`var` have existed since
> ADR-0005.


Trailing comma is accepted (and canonical in the formatter) in parameters, calls,
lists, maps and tuples **when the formatter lays the construct out multiline** (ADR-0136);
enums and `match` remain without a trailing comma.

## Grammar (EBNF)

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
pattern        → IDENTIFIER | destructure ;   (* recursive: (a, (b, c)) *)

type           → unionType ;
unionType      → postfixType ( "|" postfixType )* ;
postfixType    → primaryType ( "?" )* ;
primaryType    → IDENTIFIER ( "[" type ( "," type )* "]" )?
               | "(" type "," type ( "," type )* ")"   (* tuple *)
               | "(" type ")" ;

statement      → exprStmt
               | forStmt
               | ifStmt
               | returnStmt
               | whileStmt
               | tryStmt
               | raiseStmt
               | block ;

terminator     → ";"? ;   (* see "Optional semicolon" *)

exprStmt       → expression terminator ;
forStmt        → "for" IDENTIFIER "in" expression statement ;
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
assignment     → conditional ( "=" assignment )? ;   (* target: variable, property or index *)
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
               | "(" expression ( "," expression )+ ")"   (* tuple *)
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

`try` requires at least one `except`/`finally`; `raise` without an expression only inside
`except` (rethrows). `except Exception as e` is the catch-all and must be last.

`enum` declares namespaced variants (`Color.Green`, `Shape.Circle(1.0)`); `match` is an
expression and requires an exhaustive enum (see [`semantica.md`](semantica.md)). `Result` is a built-in
enum with `Ok(T)`/`Err(E)`.

`INTERPOLATED_STRING` is the literal `"text ${expression} more text"`; the expression is any
`expression` and may contain another interpolated string. `\${` and `\$` escape the dollar sign.

Parameter defaults and field initializers are **constants in v1** (literal,
`nil`, `true`/`false`, `-` of a numeric literal or parentheses around that). Required
parameters come before optional ones; fields may appear before or after methods.

Type annotations are optional for the interpreter (which ignores them); in `--check`
mode functions need annotations on all parameters and on the return (lambdas in `val`
may infer and generalize; see T4). `T?` is sugar for
`T | Nil`; `Int` is non-null. `List[T]` and `Map[K, V]` are the only generics: the name is
capitalized, `List`/`Map` without arguments is an error and `list[int]`/`map[...]` too (with
a capitalization suggestion). In `Map[K, V]`, `K` must be `String`, `Int`, `Bool` (or a
union of those); `Map[Float, V]`, `Map[List[T], V]` etc. are type errors.

Function types are written `fn(Int, String) -> Bool`; `fn()` has no parameters. The arrow
binds to the return type, so `fn(Int) -> Int | Nil` returns `Int | Nil`. For the function
itself to be optional, use parentheses: `(fn(Int) -> Int)?`. See
[ADR-0021](../adr/0021-tipos-de-funcao.md).

Lambdas use `fn` in expression position:

```
lambda := "fn" "(" params? ")" ("->" type)? ( "=>" expression | block )
```

```lox
val double = fn(x: Int) => x * 2
val sum = fn(a: Int, b: Int) { return a + b }
aplicar(fn(x) => x * 2, 3)
```

`=>` introduces an expression body (the value is the return); `{ ... }` introduces a block with
an explicit `return`. `-> Type` is optional before any body. Parameters follow the
function rules, **minus defaults** (`fn(x: Int = 1) => ...` is an error). `fn(` in an expression
is a lambda; `fn name(` is a declaration. See [ADR-0022](../adr/0022-lambdas.md).

Type aliases are top-level declarations with **contextual** `type` (it is not a keyword):

```lox
type UserId = Int
type Nomes = List[String]
type Callback = fn(Int) -> Int
```

The target uses the normal type grammar, may reference classes/interfaces/enums/aliases
declared before or after and cannot be generic (`type BoxAlias[T] = ...` is an error). The
alias is transparent: `UserId` and `Int` are the same type in annotations, `is`/`as` and in the
backend. See [ADR-0039](../adr/0039-decisoes-tipos-pendentes.md) and
[ADR-0084](../adr/0084-type-alias.md).

Generic functions declare type parameters between the name and `(`:

```lox
fn id[T] (x: T) -> T { return x; }
fn map[T, U] (xs: List[T], f: fn(T) -> U) -> List[U] { ... }
```

`T`/`U` are ordinary names (ASCII), valid in `: T`, `-> T`, `List[T]`, `Map[String, T]`,
`fn(T) -> U` and in the body. There is no explicit type application: `id(1)` infers `T = Int`;
`id[Int] (1)` does **not** exist. Calls without an argument/context that allows inferring every
`T` are an error.

Generic functions may declare **constraints** after `:`, joined by `+`:

```lox
fn max[T: Ord] (a: T, b: T) -> T { ... }
fn juntas[T: A + B] (x: T) -> String { ... }
```

`Ord` and `Num` are built-in constraints; interface names also work. In v1 only
functions accept bounds: `class C[T: Ord]` and `enum E[T: Ord]` are a parser error
(`Constraints on class type parameters aren't supported yet.`). Generic classes
(`class Box[T]`) exist and infer the arguments at the constructor; methods with `[T]`
remain rejected in `--check`. Generic class inheritance (`class C(Box[Int])`) does not
exist yet. See [ADR-0027](../adr/0027-generics-t3b.md),
[ADR-0040](../adr/0040-generics-classes-desenho.md) and
[ADR-0081](../adr/0081-constraints-generics.md).

`expr is Type` is a boolean expression; the right side uses the type grammar and the
operator sits at the comparison level. `is` tests primitives, classes/subclasses,
`List[T]`/`Map[K, V]` (elements included) and unions; function types are rejected in
`--check`. `Animal` as a value is not an instance: `Animal is Animal` is `false`. See
[ADR-0025](../adr/0025-is-e-narrowing.md).

In **expression context** a union requires parentheses: `x is (Int | String)` is valid,
but `x is Int | String` is a syntax error. `|` is also the bitwise operator; without the
parenthesis the parser cannot tell whether it belongs to the type or to the expression. Annotations
(`val x: Int | String`, `-> Int | String`) remain without parentheses, because there no
concurrent expression exists. `as` follows the same type grammar; a union in `as` is
rejected by the checker (`as doesn't support union types`), not by the parser.

The map literal only exists in **expression position** (`val m = {...}`, argument,
`return`, condition). At the start of a statement, `{` opens a **block**:

```lox
val m = {"a": 1}    # map
{ "a": 1 }          # block: ':' is not a valid statement
```

In the second case the parser reports a targeted error (`Unexpected ':'. Map literals can't
start a statement...`) instead of the generic `Expect ';' after expression.`

## Optional semicolon

`;` terminates statements and fields, but may be omitted when the next token starts on
another line, at EOF or at a closing `}`. Two statements on the same line still require
`;`.

```lox
val a = 1
var b = 2
print(a + b)

val c = 1; val d = 2

if (ok) { print("um") }     # `}` closes the statement: `;` is optional before the brace
```

To continue an expression on the next line, leave the **operator at the end** of the line:

```lox
val total = 1 +
  2            # ok: 3
```

Inside `()`, `[]` and expression `{}` the operator may also **start** the line,
because there is no new statement to start there:

```lox
val total = (
  1
  + 2          # ok: 3
)
```

Outside brackets, an operator at the start of the next line does **not** continue the expression; it
starts another statement:

```lox
var x = 1
-2             # separate statement; x remains 1
```

A bare `return` at the end of the line returns `nil`; to return a value, keep it on the
same line as the `return` (before `;`, `}`, or another line, no `;` is needed). A call with `(` must start on the same line as the callee;
breaking before `.` is allowed (property chaining).

`elif` is sugar for `else if`, with the same requirement of parentheses around the condition:

```lox
if (n < 0) print("negative")
elif (n == 0) print("zero")
else print("positive")
```

## Precedence and associativity

From lowest to highest:

| Level | Operators | Associativity |
| --- | --- | --- |
| assignment | `=` | right |
| conditional | `a if c else b` | right on `else` |
| coalescing | `??` | right |
| or | `or` | left |
| and | `and` | left |
| equality | `==` `!=` | left |
| comparison | `<` `<=` `>` `>=` `is T` | left |
| bitwise or | `\|` | left |
| bitwise xor | `^` | left |
| bitwise and | `&` | left |
| range | `..`, `..=` | left |
| shift | `<<` `>>` `>>>` | left |
| term | `+` `-` | left |
| factor | `*` `/` `//` `%` | left |
| cast | `as T` | left |
| unary | `not` `-` `~` | right |
| power | `**` | right; the right side accepts unary |
| call | `()` `.` `?.` `[ ]` | chains to the left |
| primary | literals, `this`, `super.x`, `( … )`, `[ … ]` | — |

`**` is the special case: `-2 ** 2` is `-(2 ** 2)` (power binds tighter than the unary
minus on the left), but `2 ** -1` is allowed. Bitwise operators bind tighter than
`==`/`!=`/comparisons, so `flags & MASK == 0` is `(flags & MASK) == 0`; shifts sit
below `+`/`-`, as in C.

`as` binds tighter than `*` and looser than unary: `-x as Int` is `(-x) as Int` and
`x as Int + 1` is `(x as Int) + 1`. The right side is a `type`; `as Int | String` is a cast
to the union (currently rejected), not a bitwise `|`. See
[ADR-0029](../adr/0029-conversoes-math.md).

Consequences:
- `-a.b()` = `-(a.b())` — the call binds tighter than unary;
- `a = b = c` assigns from right to left;
- `a or b and c` = `a or (b and c)`;
- `not a == b` = `(not a) == b` — `not` binds tighter than `==` (ADR-0068);
- `0..1 + 2` = `0..(1 + 2)` — the term binds tighter than the range; `..=` has the same
  precedence as `..`;
- `0..n < 5` = `(0..n) < 5` — the range binds tighter than the comparison;
- `a ?? b or c` = `a ?? (b or c)`;
- `a ?? b if c else d` = `(a ?? b) if c else d`;
- `a?.b.c` protects only `a`; `a?.b?.c` protects both;
- `a?.b = c` is an error (there is no optional assignment);
- `xs[0]` indexes and `xs[0] = v` assigns; the `[` must be on the **same line** as the
  previous expression, like the call `(`;
- `(1, 2)` is a tuple literal (2+ elements; `(1)` is still grouping and `(1,)` is an error);
  `(1, 2,)` accepts a trailing comma. `f(1, 2)` are two arguments; for a tuple as
  argument, `f((1, 2))`. `val (a, b) = t` and `var (c, d) = t` destructure (annotation
  optional); the pattern nests to any depth (`val (a, (b, c)) = t`), with a
  recursive annotation `(Int, (String, Bool))` ([ADR-0069](../adr/0069-destructuring-aninhado.md)).
- `[1, 2]` is a list literal and `[]` is the empty list; a trailing comma (`[1,]`, `[1, 2,]`)
  is accepted, and the formatter only inserts it in multiline constructs.

`<` is **only** comparison. Inheritance uses parentheses after the class name
(`class B(A)`), with a single superclass; `class B < A` is a syntax error. The superclass
cannot be generic (`class C(Box[Int])` is an error); a generic class may inherit from a
non-generic class.

Interfaces are nominal and use **contextual** `implements` after the class header
([ADR-0080](../adr/0080-interfaces-nominais-implementacao.md)):

```lox
interface Shape {
  area() -> Float                 # abstract: no body
  fn name() -> String {           # default: with body; `fn` is optional
    return "shape"
  }
}

class Circle implements Shape { ... }
class Triangle(Figure) implements Shape, Drawable { ... }
```

- `interface` is a keyword and the declaration is **top-level**.
- The body only accepts methods; `init`, fields and `static` are rejected. A method without `{` is an
  abstract signature and ends by the normal optional-`;` rule (end of line, `}` or
  EOF); a method with `{ ... }` is a default.
- `implements` is only special in the class header; anywhere else it remains an
  identifier (`val implements = 1` works).
- No generic interfaces (`interface I[T]`), no interface inheritance (`interface A : B`)
  and no `class C(A, I)`.

## Loops

C-style `for (init; cond; incr)` was removed ([ADR-0138](../adr/0138-remocao-for-c-style.md));
use `for x in ...` or `while`. `for` only introduces `for-in`:

`for-in` becomes the node `ForIn(name, iterable, body)` and does **not** desugar to `while`,
because the interpreter needs to report "not iterable" and the codegen needs the loop per
iterable (Range/String/List/Map/Tuple — `Map` yields the keys). See
[`semantica.md`](semantica.md#ranges-and-for-in).

### Blocks

`{ … }` is a statement; expressions have no block (the expression `{` is the map literal).
`if`/`while` take **one** statement (hence the braces when there is more than one instruction).

## Fine points

- **Semicolon is optional** at the end of the line, at EOF or before a closing `}`
  (ADR-0011); two statements on the same line still require `;`. In the REPL, the final `;` may be
  omitted when the input ends (`_end_statement`).
- `val` **requires an initializer** (`val x;` is an error). `var` may omit it (`var x;` → `nil`).
- Parameters are **implicit `val`**; `var` before the name allows reassignment:
  `fn f(x, var y)`. An explicit `val` on a parameter is not accepted.
- Class methods accept an **optional** `fn`; the canonical form remains without `fn`, because
  the class body already marks the declaration:

  ```lox
  class Foo {
    bar(a) { return a; }
    fn baz(a) { return a; }   # accepted; same AST
  }
  ```

### Imports

```lox
import std.lists
import dtos.dtoA as dto
from std.strings import trim
from dtos.dtoA import DtoA as Dto
```

- `import path [as alias]` binds the last segment (or the alias) as a namespace.
- `from path import name [as alias] [, name ...]` binds public names.
- Imports only at the top, before any other statement; no `*`, no re-export.
- The path is identifiers separated by `.`; `std` is a reserved root.
- `..` and absolute paths are not valid syntax in `import`: the root outside the project is
  declared in `loxia.toml` (`[dependencies]`/`[modules].paths`) or in `--module-path`
  ([ADR-0100](../adr/0100-dependencias-path.md)).
- A module is a `.lx` file; a folder is only a namespace (no `__init__`/`index`).
- A module is not a value: `val m = std.lists` is an error.

- Parser limits: at most **255 arguments** per call and **255 parameters** per
  function. On exceeding, the error is reported but the parser continues (the arguments are
  dropped from the AST).
- `this` and `super` are keywords: `super` only appears as `super.method`.
- These do not exist: C-style `for` (removed in [ADR-0138](../adr/0138-remocao-for-c-style.md);
  use `for-in` or `while`), `break`/`continue`, `switch` (use `match`), a `?:`-style ternary
  operator (use `a if c else b`), `+=`, `++` and `catch` (use `except`). `match` with
  enums ([ADR-0041](../adr/0041-enums-match.md)) and lambdas ([ADR-0022](../adr/0022-lambdas.md))
  exist; lists, maps and interpolation have existed since
  [ADR-0015](../adr/0015-listas-tipadas.md), [ADR-0017](../adr/0017-mapas-hash.md) and
  [ADR-0019](../adr/0019-interpolacao.md).
- `fn` may appear in any declaration position, including inside a block.
