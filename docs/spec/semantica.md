---
sources:
  - loxia_core/execution/**
  - loxia_core/semantics/**
  - loxia_core/loader/**
  - std/**
---

# Semantics

Observable behavior of the interpreter. Implementation: [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py),
[`loxia_core/semantics/resolver.py`](../../loxia_core/semantics/resolver.py), [`loxia_core/execution/environment.py`](../../loxia_core/execution/environment.py),
[`loxia_core/execution/lox_function.py`](../../loxia_core/execution/lox_function.py), [`loxia_core/execution/lox_class.py`](../../loxia_core/execution/lox_class.py),
[`loxia_core/execution/lox_instance.py`](../../loxia_core/execution/lox_instance.py), [`loxia_core/execution/values.py`](../../loxia_core/execution/values.py).

## Execution

A program is a list of declarations executed **in order**. A compile error
(lexical, syntax or resolver) prevents the entire execution. A runtime error stops the
program at the point where it occurred; whatever was already printed remains. Since
[ADR-0026](../adr/0026-freeze-1.0.md), an **uncaught** runtime error is fatal (exit 70);
`try`/`raise` ([ADR-0042](../adr/0042-excecoes.md)) capture explicit exceptions and runtime
errors, and `Result` covers expected errors. Type/syntax errors exit 65.

The boundary between the two channels is [ADR-0135](../adr/0135-politica-de-erro.md): a **defect**
(division by zero, `R1015`, invalid index) surfaces as `RuntimeError` and is fatal unless caught;
an **expected failure** is a `Result[T, E]` value in the signature; `raise`/`except` is for
**user control flow**. A function declares one channel: a function returning `Result` does not
raise for the same failure. The naming rule (core uses the plain name, raising shell uses the
`OrRaise` suffix) is the target for **new** shells; no stdlib function uses `OrRaise` yet — `json`
migrates in ADR-0135's M2. The stdlib is migrating to "no raise for expected failure": today the
allowlist by nature is `asserts`, `contracts`, `test`, `property`, and the remaining raises are
tracked in M2-M3 by `tests/test_stdlib_error_policy.py`. There is no `main` entry point today: a discarded `Err` is just a value and does not change
the exit code. When an entry point returning `Result` exists ([#142](https://github.com/loxia-lang/loxia/issues/142)),
an unhandled `Err` will print `error: <msg>` to stderr and exit **70** (same code as an
uncaught runtime error); that is the decided target, not current behavior.

Call depth is limited to **10,000 Lox activations** (function, method, lambda,
`init` and constructor); the next is `R1015` (`Stack overflow.`), exit 70, catchable by
`try`/`except RuntimeError`, with position and stack trace
([ADR-0077](../adr/0077-limite-de-pilha.md),
[ADR-0089](../adr/0089-stack-trace-de-runtime.md)). Native calls and `Exception`/`RuntimeError`
constructors do not count. A `try`/`finally` that crosses the overflow restores
the depth before the handler continues.

The REPL executes one line at a time, **keeping variables, functions and classes** between lines.
A pure expression such as `1 + 1` is wrapped in `print(1 + 1)` and shows `2`; declarations
(`var`, `fn`, `class`) print nothing.

## Values

| Value | Origin | `stringify` |
| --- | --- | --- |
| `nil` | `nil`, `var` without initializer, `return;` | `nil` |
| `true`/`false` | literals, comparisons | `true`/`false` |
| `Int` | literals without `.`/exponent, integer arithmetic | decimal (`42`, `-3`) |
| `Float` | literals with `.`/exponent, `/`, mixing with `Float` | round-trip (`42.0`, `2.5`) |
| `List` | `[...]` literal | `[1, 2, 3]` (strings quoted inside the list) |
| `Map` | `{...}` literal | `{"a": 1, "b": 2}` (insertion order) |
| `Range` | `a..b`, `a..=b`, `range(a, b, step)` | `<range 0..10>`, `<range 0..=10>` |
| `Bytes` | `Bytes.fromText`/`fromList`/`fromHex`/`fromBase64` | `0x<lowercase hex>` |
| string | literals, `+`, interpolation | contents |
| function | `fn` | `<fn name>` |
| native function | `len` | `<native fn>` |
| class | `class` | class name |
| instance | class call | `Name instance` |

Numbers are **`Int` (i64) or `Float` (f64)** — [ADR-0006](../adr/0006-int-float-separados.md).
`print(3)` shows `3` and `print(3.0)` shows `3.0`: the type comes from the literal. The
complete rules are in this document and in
[ADR-0006](../adr/0006-int-float-separados.md).

### Truthiness

Only `nil` and `false` are falsy. `0`, `0.0`, `""`, lists and maps (including empty ones) are
**truthy**.

### Equality (`==`, `!=`)

- `nil == nil` → `true`; `nil` vs anything else → `false`;
- `Int` and `Float` compare by numeric value, with promotion: `1 == 1.0` → `true` (the `Int`
  is converted to `Float`; above `2^53` the conversion may lose precision, as in
  LLVM);
- `Range` compares **structurally** (`start`, `end`, `step`, `inclusive`):
  `(0..3) == (0..3)` → `true` and `(0..2) != (0..=2)`;
- `List` compares **structurally**, element by element, including nested lists and with
  numeric equality (`[1, 2] == [1, 2.0]` → `true`). Different lengths are
  `false`; cycles are handled with a set of visited pairs;
- `Map` compares **structurally, regardless of insertion order**:
  `{"a": 1, "b": 2} == {"b": 2, "a": 1}` → `true`; the number of entries and the equality of
  each value count, with a cycle guard. `Map` is not hashable;
- `true == 1` → `false` (a boolean is never a number);
- strings compare by content; `Bytes` compares by content (O(n), identity short-circuit) and `b == s` is `false` (different types);
- functions, classes and instances compare by **identity** (the same object);
- `NaN != NaN` (IEEE); no literal produces `NaN` today.

### Number formatting

- `Int` → decimal, no decimal places (`42`, `-3`);
- `Float` → the shortest representation that round-trips to the same `double`, **always**
  distinguished from `Int`: `2.0`, `-0.0`, `3.14`, `0.30000000000000004`;
- Python scientific notation starting at the corresponding magnitude (`1e+20`, `1e-07`);
- `NaN`, `inf` and `-inf` are the texts for non-finite `Float`; `inf` only appears through
  `Float` overflow (division by zero is an error);
- formatting is a golden-case contract: `42` and `42.0` are different outputs.

Lists format as `[1, 2, 3]`; strings inside lists are quoted and escaped
(`["a\nb"]`); a list that contains itself prints `[[...]]`. Maps format as
`{"a": 1, "b": 2}` in insertion order, with quoted/escaped strings; a map that contains
itself prints `{"self": {...}}`. Outside a list/map, a string remains unquoted.

## Variables, `val` and `var`

- `val x = expr;` creates an **immutable** binding and **requires an initializer**.
- `var x;` creates a mutable binding with `nil`; `var x = expr;` does the same with a value.
- `Nil` não é um tipo de **armazenamento** (variável, parâmetro ou campo): use `Any` ou
  `T?`. `-> Nil` continua válido como retorno.
- Under `--check`, every binding is **monomorphic**: `var x = 1` is `Int` forever; `x = 2.0`
  is an error. `var x = nil` without an annotation is an error (`Can't infer type of 'x' from nil; add an
  annotation.`); use `var x: Int? = nil` or `var x: Any = nil`. A mutable field with a
  `nil` initializer follows the same rule; `val x = nil` is allowed. See
  [ADR-0024](../adr/0024-mutacao-monomorfica.md).
- Immutability belongs to the **name**, not the value: `val list` can still have mutable
  contents (`list.push(1)` is allowed).
- Assigning to a local `val` (or to an immutable parameter) is a **compile error**:
  `'x' is immutable; declare it with 'var' to allow assignment.`
- Assigning to a **global** `val` is a **runtime** error (same message, exit 70): globals are
  not tracked by the resolver.
- A global `val` **cannot be redeclared** (`val x = 1; var x = 2;`): runtime error
  `Can't redeclare immutable variable 'x'.` A global `var` remains redeclarable; `var`
  followed by `val` is allowed and the name becomes immutable.
- In a local scope (block, function, `for`), redeclaring the same name in the same scope is a
  compile error: `Already a variable with this name in this scope.` (applies to `val` and `var`).
- Nested blocks may **shadow** names from outer scopes (including `val`).
- Reading a local variable in its own initializer is an error:
  `Can't read local variable in its own initializer.` (a global becomes
  `Undefined variable` at runtime).
- `fn` and `class` declarations create **mutable** bindings (separate open decision).
- The resolver records the **distance** of each local access; globals continue to be
  looked up at runtime in the global environment. This guarantees lexical scope: a closure reads the
  variable from where it was **declared**, not from where it is called.

Canonical example:

```lox
var a = "global";
{
  fn showA() { print(a); }
  showA();        // global
  var a = "block";
  showA();        // global (not "block")
}
```

## Operators

| Operator | Types | Result |
| --- | --- | --- |
| `not` | any | negates truthiness |
| `-` | number | negation (on `Int`, with wrapping; debug checks overflow) |
| `~` | `Int` | 64-bit complement (`~x == -x - 1`) |
| `+` | two numbers **or** two strings | addition with promotion / concatenation |
| `-` `*` | two numbers | arithmetic with promotion; `Int` wraps (debug checks) |
| `/` | two numbers | division **always `Float`** (`4 / 2` → `2.0`) |
| `//` | `Int` | truncated integer division; zero divisor is an error |
| `%` | two numbers | truncated remainder (sign of the dividend); `fmod` if a `Float` is involved |
| `**` | numbers | `Int ** Int` → `Int`; any `Float` → `Float`; right-associative |
| `&` `\|` `^` | `Int` | bitwise operations on 64 bits |
| `<<` `>>` `>>>` | `Int` | shift; `>>` arithmetic, `>>>` logical; count `0..63` |
| `<` `<=` `>` `>=` | two numbers | boolean (promotion; with `NaN`, everything is `false`) |
| `==` `!=` | any | equality |
| `and` `or` | any | short-circuit, returns the operand |
| `a if c else b` | any condition | chooses one branch; evaluates only the chosen one |
| `a ?? b` | any | returns `a`, or `b` if `a` is `nil` |
| `a?.b` | nullable object | `nil` if `a` is nil; otherwise accesses `b` |
| `a as T` | `Int`/`Float`/`Any`/class/list/map | explicit cast; fails at runtime if it cannot convert |

- `Int op Float` promotes the `Int` to `Float` (`1 + 2.0` → `3.0`); `Float → Int` is never
  implicit.
- **`--debug`** checks `Int` overflow in `+ - * ** -`, `INT_MIN // -1` and `INT_MIN % -1`;
  overflow is a fatal error (`Integer overflow.`, exit 70). Without the flag, release wraps.
  Shifts remain bitwise. See [ADR-0028](../adr/0028-overflow-debug.md).
- `+` **does not** mix number and string: `Operands must be two numbers or two strings.`
- Relational comparisons are numeric only: `Operands must be numbers.`
- Division by zero is a **runtime error** (`Division by zero not allowed`), for `Int` and
  `Float` — our decision, different from the book (which would return `inf`/`NaN`).
- Remainder by zero is also a runtime error (`Modulo by zero not allowed`).
- `%` follows C/LLVM: `-7 % 3` → `-1` (sign of the dividend), not `2`.
- `//` is also truncated (`-7 // 2` → `-3`); with `%`, the identity
  `a == (a // b) * b + (a % b)` holds. Overflow of `INT_MIN // -1` wraps; under `--debug` it is
  an error. `INT_MIN % -1` is `0` in release and an error in debug.
- `**`: `2 ** 3` → `Int` 8; `2 ** -1` is an error (`Negative exponent not allowed for integer
  power.`); use `2.0 ** -1` for `0.5`. `2 ** 63` wraps to `INT_MIN`; under `--debug`
  each intermediate multiplication is checked. A negative exponent on `Float` is allowed;
  invalid domain/overflow is an error.
- `~`, `&`, `|`, `^` and shifts are **`Int` only**; `Bool` and `Float` are
  `Operands must be integers.` (unary: `Operand must be an integer.`). `>>>` operates on the
  64-bit unsigned pattern (`-1 >>> 1 == INT_MAX`).
- A shift outside `0..63` is an error (`Shift count must be between 0 and 63.`), not a mask.
- `and`/`or` return the operand value, not a boolean:
  `nil or 2` → `2`; `false and 1` → `false`.
- Evaluation order is left→right; `and`/`or` evaluate the right side only if necessary.
- `a if c else b`: the condition uses truthiness; only one branch is evaluated. The type is the union of the
  branches (`Int`/`Int` → `Int`); the `else` is right-associative.
- `??` is **nil only**: `0 ?? 5` → `0`, `false ?? true` → `false`, `"" ?? "x"` → `""`;
  `or` still uses truthiness. The right side is evaluated only if the left side is `nil`.
- `?.` only protects against `nil`: `nil?.x` → `nil`; `a?.b.c` does not protect `b`; use `a?.b?.c`.
  In `a?.m()`, if `a` is nil, the method and the arguments are not evaluated; if `a` is not
  nil but `m` does not exist, it is still an error. `a?.b = c` is invalid.
- `a?.b ?? c` combines both: `?.` avoids the access and `??` applies the default when the
  result is nil. Without `?.`, `a.b ?? c` still errors if `a` is nil.
- The `?:` elvis operator **does not exist**; `??` is the only coalescing operator.
- Strings: `"..."` is single-line; `"""..."""` is multiline (quotes are free, with no dedent
  and no removal of the first newline); `r"..."`/`r"""..."""` are raw (`\` is literal,
  `${...}` does not interpolate). Non-raw forms process `\n`, `\t`, `\r`, `\"`, `\\`, `\0`,
  `\$` and `\u{XXXX}`; an unknown escape is an error. See
  [ADR-0070](../adr/0070-strings-multilinha-e-raw.md).
- Source and strings are UTF-8; `len(s)` counts **code points**, not bytes. `s[i]` on a string
  **does not exist**: for random access use `chars(s)` (`List[String]`, explicit O(n));
  `for c in s` iterates code points without allocating. Strings compare by content (`==`/`!=`) and
  order by `< <= > >=` in code-point order (= UTF-8 byte order); mixing with a
  number is an error. There is no normalization (`"é" != "e\u{301}"`). Identifiers are ASCII (no
  Unicode normalization); see [ADR-0026](../adr/0026-freeze-1.0.md) and
  [ADR-0035](../adr/0035-strings-texto.md).
- Comments: `#` to the end of the line; `/* ... */` for blocks, nested. `//` is an operator,
  not a comment.

## Interpolation

`"text ${expression} more text"` evaluates each expression from left to right and
concatenates the pieces. The conversion is the same `stringify` as `print`:

```lox
val name = "Ana"
print("Hi, ${name}!")        # Hi, Ana!
print("1 + 2 = ${1 + 2}")    # 1 + 2 = 3
print("map: ${{"a": 1}}")    # map: {"a": 1}
print("escape: \${name}")   # escape: ${name}
print("dollar: $5")          # dollar: $5
```

- Any expression is accepted, including a call, an index, a map/list and another interpolated
  string; the result is always `String`.
- `\$` and `\${` produce literal `$`/`${`; outside `${...}`, `$`, `{` and `}` are literals.
- The checker checks each expression; an error inside one is a normal `--check` error.
- Valid in `"..."` and `"""..."""`; in raw strings (`r"..."`), `${...}` is literal text
  ([ADR-0070](../adr/0070-strings-multilinha-e-raw.md)). No format spec.

## Lists

`List[T]` is the language's only sequence: **homogeneous in type**, **mutable in place** and
**invariant**. See [ADR-0015](../adr/0015-listas-tipadas.md).

```lox
val xs: List[Int] = [1, 2, 3]
print(xs[0])          # 1
xs[1] = 20
xs.push(4)
print(len(xs))        # 4
print(xs.pop())       # 4
for x in xs { print(x) }
```

- **Literal**: `[a, b, c]`; `[]` is the empty list. The type is inferred by unifying the
  elements: `[1, 2]` is `List[Int]`, `[1, 2.0]` is `List[Float]` (promotion). Non-numeric
  mixing (`[1, "a"]`) is an error under `--check`; heterogeneity requires an explicit annotation
  (`List[Int | String]` or `List[Any]`). An empty list without an expected type is an error; with explicit
  `Any`, it becomes `List[Any]`.
- **Access**: `xs[i]`, with `i` an `Int` and zero-based. A negative or out-of-range index is a
  runtime error; `xs[i]` on a non-list/non-map is `Only lists and maps can be indexed.`
- **Assignment**: `xs[i] = v` mutates and returns `v`; `v` must be assignable to `T` under
  `--check`; the same index bounds apply at runtime.
- **Methods**: `xs.push(v)` appends to the end and returns `nil`; `xs.pop()` removes and returns the
  last element, and an empty list is an error (`Can't pop from an empty list.`). `xs.len()` does not exist;
  use `len(xs)`.
- **`len`**: `len(xs)` is O(1) and returns `Int`; `len(s)` returns the number of code points in the
  string, `len(b)` the number of bytes in a `Bytes`, and `len(m)` the number of map entries.
  `len` of another type is a runtime error in the
  tree-walk and a type error under `--check`.
- **Iteration**: `for x in xs` traverses in insertion order; mutating the list during the loop is an
  error (`Can't modify a list while iterating over it.`), not a silent snapshot.
- **Equality**: structural (see above). **Stringify**: `[1, 2, 3]`, with strings quoted and
  escaped (`["a\nb"]`) and cycles as `[[...]]`.
- **Aliasing**: lists are references. `val ys = xs` does not copy; mutating `ys` is visible in
  `xs`. `val` freezes the binding, not the contents.
- **Optional**: `List[T]?` and `xs?.push(...)`/`xs?.pop()` work; `len(xs)` and `for` over
  `List[T]?` require `if (xs != nil)` (narrowing) or `??`/`?.`.
- **Erased types**: without `--check`, the list accepts any element at runtime; homogeneity is a
  static contract. There is no runtime type check in `push`.
  The `Int → Float` promotion is also check-only: `xs.push(1)` on `List[Float]` is accepted,
  but the value remains `Int` at runtime (`print(xs)` → `[1, 2.0]`), just like
  `val f: Float = 1`.
- **Limits**: no slice, list `+`, `map`/`filter`, `contains`, `sort` or string indexing in
  v1. A list literal is not a parameter default or a field initializer; in
  `init`, `this.xs = []` works.

## Bytes

`Bytes` is an **immutable, contiguous sequence of bytes 0..255** — binary data, not text.
`String` stays UTF-8 text with `len` in code points; `Bytes` has `len` in bytes and no
UTF-8 validation. See [ADR-0125](../adr/0125-bytes-tipo-binario.md).

```lox
val data = Bytes.fromText("é")   # UTF-8: 2 bytes
print(len(data))                 # 2
print(data[0])                   # 195
print(data)                      # 0xc3a9
print(data.toHex())              # c3a9
```

- **Construction**: `Bytes.empty()`, `Bytes.fromList(xs: List[Int])` (elements 0..255; out of
  range raises `RuntimeError`), `Bytes.fromText(s)` (UTF-8 encode), `Bytes.fromHex(s)` and
  `Bytes.fromBase64(s)` (both `Result[Bytes, BytesError]`). Hex accepts lowercase and
  uppercase; base64 is canonical RFC 4648 (standard alphabet, padding required, no
  whitespace, non-canonical trailing bits rejected).
- **Access**: `b[i]` is an `Int` 0..255; a negative or past-the-end index is a runtime error.
  There is no slice syntax; use `b.slice(start, end)` (half-open, same bounds rules as
  `substr`).
- **Methods**: `slice`, `concat(other)`, `toList()`, `toText()`, `toHex()`, `toBase64()`.
  They are called with `b.slice(...)`; a method reference (`val f = b.toHex`) works in the
  interpreter and is a declared backend gap (PENDING), like `List.push`.
- **Text conversion**: `toText()` is strict UTF-8 and returns `Result[String, BytesError]`;
  invalid input is never replaced. `BytesError` is a built-in enum with
  `InvalidHex(message)`, `InvalidBase64(message)` and `InvalidUtf8(message)`, available
  without an import; match it to get the detail.
- **`len` and equality**: `len(b)` counts bytes; `b == c` is structural and O(n), with an
  identity short-circuit; `b == s` is `false`. Bytes in `Any`, `List`, `Bytes?` and `?.`
  work like any other value.
- **Not a `Map` key**: keys remain `String`, `Int` and `Bool` ([ADR-0017](../adr/0017-mapas-hash.md));
  `Map[Bytes, V]` is a checker error. Use `toHex()` as a key when grouping by content.
- **No literal or slice syntax**: `b"..."` and `b[a..z]` are not part of the language
  ([ADR-0066](../adr/0066-orcamento-e-gate-sintatico.md)).
- **Iteration**: `for byte in b` yields each byte as an `Int` 0..255; `b.toList()` copies
  when a `List[Int]` is needed.

## Tuples

`(1, "a")` is a tuple of arity 2; the type is `(Int, String)`. Tuples have **2+ elements**
(no `()` and no `(x,)`), are **immutable** and **covariant per element**: `(Dog, Int)` is
assignable to `(Animal, Int)` and `(Int, String)` to `(Any, Any)`. See
[ADR-0030](../adr/0030-tuplas.md) and [ADR-0036](../adr/0036-tuplas-implementacao.md).

```lox
val par: (Int, String) = (1, "a")
print(par[0])                 # 1
val (n, s) = par            # destructuring
print(s)                      # a
print(len(par))               # 2
```

- **Literal and type**: `(a, b)`; parentheses without a comma remain grouping. The type
  `(Int, String)` can nest (`(Int, (String, Bool))`) and be returned from functions.
- **Access**: `t[0]`, `t[1]`; the index must be an `Int`. A **literal** index outside the range is
  a `--check` error (`Tuple index 2 out of bounds for length 2.`); a **dynamic** index
  has type `Int | String` (union of the elements) and runtime bounds
  (`Tuple index 5 out of bounds for length 2.`). No negative index.
- **Destructuring**: `val (a, b) = t`, `var (c, d) = t` and an optional annotation
  (`val (a, b): (Int, String) = t`). The pattern **nests** (`val (a, (b, c)) = t`,
  [ADR-0069](../adr/0069-destructuring-aninhado.md)); each level requires a tuple (or a union of
  tuples of the same arity) and reports the arity error locally. `Any` only with an annotation;
  a duplicate name at any level is an error.
- **Equality**: structural, element by element (`(1, "a") == (1.0, "a")` → `true`).
- **Stringify**: `(1, "a")`, with quoted/escaped strings, recursively; `(...)` if there is a
  cycle through a list/map.
- **Immutability**: `t[0] = x` is an error (`Only lists and maps can be indexed.`).
- **Iteration**: `for x in t` traverses the elements; the type of `x` is the union of the items
  (`(Int, String)` → `Int | String`).
- **`is`/`as`**: `x is (A, B)` tests arity and each position; `x as (A, B)` is a checked cast
  (accepts `Any`; fails at runtime if the shape does not match).
- **Outside v1**: tuples are not hashable or `Map` keys; the backend covers them in L6.

## Maps

`Map[K, V]` is the language's associative collection: **homogeneous**, **mutable in place** and
**invariant** in `K` and `V`. See [ADR-0017](../adr/0017-mapas-hash.md).

```lox
val ages: Map[String, Int] = {"Ana": 32}
print(ages["Ana"])            # 32
print(ages.get("Bia"))        # nil
print(ages.get("Bia") ?? 0)   # 0
ages["Bia"] = 28
print(ages.has("Bia"))        # true
print(len(ages))              # 2
for name in ages { print(name) }     # Ana, Bia (insertion order)
```

- **Literal**: `{ key: value, ... }`; `{}` is the empty map in expression position. The
  keys are **expressions**: `{ name: 1 }` uses the variable `name`; `{ "name": 1 }` uses the
  string. At the start of a statement, `{` still opens a block — for a standalone map,
  use `val m = ...` or parentheses. A repeated key in the literal is a runtime error
  (`Duplicate key in map literal.`); to update, use `m[k] = v`.
- **Inference**: without an annotation, keys and values must have a common type
  (`{"a": 1, "b": 2.0}` → `Map[String, Float]`); non-numeric mixing requires an annotation
  (`Map[String, Int | String]` or `Map[String, Any]`). `{}` without context is an error under
  `--check`; with an expected `Map[K, V]`, it is accepted.
- **Keys**: `String`, `Int`, `Bool` and explicit unions of those types. `Bool` is distinct from
  `0`/`1` (`{true: "a", 1: "b"}` has two keys). `Float` is not a key in v1 (the relation
  `1 == 1.0` would require canonicalization); `nil`, `List`, `Map`, `Range`, classes and functions
  are not either. Without `--check`, the restriction applies at runtime
  (`Map keys must be strings, integers or booleans.`). **Hash consistent with `==`**: the
  accepted keys compare and hash by the same notion — `Bool` has its own tag (it does not
  collide with `0`/`1`), `String` compares by content and `Int` by value; since `Float` is
  rejected on entry, `1 == 1.0` never becomes two entries or breaks lookup.
- **Access**: `m[k]` returns `V` and is an **error** if the key does not exist
  (`Key not found in map.`). `m.get(k)` returns `V?` (`nil` if absent); `m.has(k)` returns
  `Bool` and distinguishes absent from a `nil` value. `m[k]` on a non-map/non-list is
  `Only lists and maps can be indexed.`
- **Assignment**: `m[k] = v` inserts or updates and returns `v`; under `--check`, `k` must be
  assignable to `K` and `v` to `V`.
- **Methods**: `m.remove(k)` removes and returns `V` (an absent key is an error);
  `m.keys()`/`m.values()` return new `List[K]`/`List[V]`, in insertion order (a snapshot,
  not a view). `m.len()` does not exist; use `len(m)`.
- **Iteration**: `for k in m` traverses **keys** in insertion order; mutating the map during the
  loop is an error (`Can't modify a map while iterating over it.`), including updating the value of
  an existing key. `(k, v)` pairs do not have a method yet (`entries`); `for k in m` gives the keys.
- **Equality**: structural and order-independent (see above). **Stringify**:
  `{"a": 1, "b": 2}` with quoted/escaped strings and cycles as `{"self": {...}}`.
- **Aliasing**: maps are references. `val n = m` does not copy; mutating `n` is visible in `m`.
  `val` freezes the binding, not the contents. Maps **are not** hashable and cannot be keys.
- **Optional**: `Map[K, V]?` and `m?.get(...)`/`m?.has(...)` work; `len(m)` and `for` over
  `Map[K, V]?` require `if (m != nil)` (narrowing) or `??`/`?.`.
- **Limits**: no `clear`, `entries`, `map`/`filter`, `contains` or map `+` in v1.
  Without `--check`, types are erased: the runtime does not validate `V` in `m[k] = v`, only the
  key type; homogeneity is a static contract.

## Ranges and for-in

`a..b` creates a **half-open** `Range` (`a` included, `b` exclusive) and `a..=b` an
**inclusive** range (`b` included), with `Int` bounds only;
`range(a, b, step)` does the same with an explicit step (including negative). A Range is a
lazy, reusable value: it does not materialize elements and each `for` creates its own iteration.

```lox
for i in 0..4 { print(i); }       // 0 1 2 3
for i in 0..=4 { print(i); }      // 0 1 2 3 4
for i in range(5, 0, -2) { ... }  // 5 3 1
for i in 5..2 { ... }             // empty
```

- Sources accepted today: `Range` (produces `Int`), `String` (produces a 1-code-point `String`),
  `List[T]` (produces `T`, in insertion order), `Map[K, V]` (produces `K`, the keys, in
  insertion order), a tuple (produces the union of the elements) and classes/interfaces with
  `iter()` + `next() -> T?`.
- The iterable is evaluated **once**, before the loop binding; bounds are evaluated once,
  left to right.
- The loop variable is a **new `val` per iteration**: reassigning it is a compile error and
  closures capture the value of that iteration.
- Mutating the collection during iteration is **forbidden**: on `List`/`Map` it is a runtime error
  (`Can't modify a list while iterating over it.` /
  `Can't modify a map while iterating over it.`); `Range`/`String` are immutable.
- User iterator: `for x in e` calls `e.iter()` **once**; the result must have
  `next() -> T?`; `nil` terminates and any other value becomes `x` (type `T`). The protocol is
  structural (it does not require `implements`); the iterator class may be generic
  (`iter() -> BoxIter[T]`, `next() -> T?`). `next() -> Any?`, `next() -> Nil`, `iter()`/
  `next()` with parameters and a return that is not an iterator are checker errors. `nil` as an
  element is not representable, because it is the end sentinel. See
  [ADR-0082](../adr/0082-iterador-de-usuario.md).
- `Range` is truthy, prints as `<range a..b>` (or `<range a..b step s>`) and compares
  structurally.
- Runtime errors: `Can only iterate over a range, a list, a map or a string.`,
  `iter() must return an instance with next() -> T?.`,
  `iter() must take no arguments.`, `next() must take no arguments.`,
  `Range bounds must be integers.`, `range() arguments must be integers.`,
  `range() step can't be zero.`; wrong arity uses the standard message
  (`Expected 3 arguments but got N.`).

## Statements

| Statement | Effect |
| --- | --- |
| `expr;` | evaluates and discards |
| `{ … }` | new scope |
| `if (c) s elif (c) s else s` | executes the branch according to truthiness; `elif` is `else if` |
| `while (c) s` | repeats while truthy |
| `for x in e s` | iterates `e` (Range/String/List/Map/Tuple today); `x` is `val` per iteration |
| `return expr?;` | unwinds up to the function call |

C-style `for (init; cond; incr)` was removed ([ADR-0138](../adr/0138-remocao-for-c-style.md));
use `for-in` or `while`.

The `;` is optional at the end of the line (or EOF); two statements on the same line still require
it. Expression continuation requires the operator at the **end** of the line; an operator at the
start of the next line begins another statement. A `return` alone on the line returns `nil`.

## Functions

- `print(value)` is a builtin function `Any -> Nil`: it writes `stringify(value)` and a
  newline. It is not a statement or keyword; it can be nested (`print(print(1))`),
  used in `return` and as any expression. `print(a, b)` is an arity error
  ([ADR-0085](../adr/0085-print-como-funcao.md)).
- Declaration: `fn name(params) { body }`; the name is defined **before** the body, so the
  function can be recursive; functions in the same scope can call each other (runtime
  resolution for globals, distance for locals).
- Parameters are **immutable by default** (implicit `val`). `fn f(var x)` allows
  reassigning `x`; without `var`, assignment is a compile error.
- A parameter may have a **constant default**: `fn f(a, b = 10)`. Required parameters come before
  optional ones; after a default, all following parameters need a default.
- Call: evaluates the **callee** first and the arguments left to right; then
  checks that it is callable and the arity.
- Not callable: `Can only call functions and classes.`
- Wrong arity: fixed arity uses `Expected N arguments but got M.`; with defaults,
  `Expected at least N arguments but got M.` or `Expected N to M arguments but got K.`
- Closures: the function captures the environment where it was **declared** (by reference). Captured
  variables remain mutable.
- `return;` returns `nil`. `return` at the top level of the program is a compile error:
  `Can't return from top-level code.` To return a value, it must be on the same
  line as `return`; a `return` alone on the line returns `nil`.
- Parameters and body locals share the same scope: declaring `var a` when a
  parameter `a` exists is an error (the same redeclaration message).
- `clock()` **does not exist in 1.0**: time is ambient input and would violate I3. A
  `time` module that is explicitly non-deterministic is left for later. The deterministic prelude is
  `args`, `chars`, `charCodeAt`, `fromCodePoint`, `join`, `len`, `str`, `repr`, `range`,
  `substr`, `Int`, `Float`, `math`, `io`, `os` and `time`.
- `len(x)` accepts `List`, `Map` or `String`; it returns `Int` (O(1) for list/map, code
  points for string). Another type is an error:
  `len() expects a string, a list or a map.`
- `chars(s)` requires `String` and returns `List[String]` with the code points (each one is a
  1-cp string); explicit O(n). `chars("café")` → `["c", "a", "f", "é"]`; another type is an error.
- `substr(s, start, end)` requires `String`/`Int`/`Int` and returns the substring by code
  points; `0 <= start <= end <= len(s)`, otherwise a runtime error.
- `join(parts, sep)` requires `List[String]` and `String` and returns the linear concatenation.
- `charCodeAt(s, index)` returns the code point (`Int`) at the position; out of bounds is an error.
- `fromCodePoint(codePoint)` requires a valid `Int` (0..0x10FFFF, no surrogates) and returns
  a 1-code-point `String`.
- OS kernel: `args()` returns `List[String]` with the arguments after the script/binary;
  `io.readFile(path)`, `io.write(text)`, `io.writeErr(text)`, `io.writeFile(path, text)`,
  `io.readLine()` and `os.getenv(name)` are ambient (input/FS); `os.exit(code)` exits
  with 0..255; `time.now()`/`time.sleep(ms)` are ambient.
- `process.*` (POSIX, ambient): `spawn(argv) -> Int` starts without a shell (0 = failure);
  `stdin/stdout/stderr(handle) -> Int`; `wait(handle) -> Int` (negative = signal);
  `kill`/`close(handle)`; `read(handle, n) -> String?` (up to `n` bytes, always on a UTF-8
  boundary); `write(handle, text) -> Bool`; `poll(handles, timeoutMs) -> List[Int]` (readable
  streams/EOF and exited processes; `timeout < 0` = infinite, `0` = non-blocking).
  Kernel 19 → 29 ([ADR-0095](../adr/0095-processos-streams-poll.md)).
- `io.write`/`io.writeErr` flush on every call (in both engines) and `io.flush()`
  forces stdout and stderr: a process can read the output before EOF
  ([ADR-0094](../adr/0094-kernel-io-flush-e-read-utf8.md)).
- `io.readUtf8(n)` reads **exactly** `n` bytes from stdin (0..n-1 and decodes strict
  UTF-8): `n < 0` is an error; `n == 0` returns `""` without touching stdin; immediate EOF
  returns `nil`; EOF in the middle or invalid bytes are a `RuntimeError` (`R1000`) with the call
  position. Mixing `io.readUtf8` with `io.readLine`/`io.readAll` in the interpreter is
  undefined (distinct buffer layers); use a single style
  ([ADR-0094](../adr/0094-kernel-io-flush-e-read-utf8.md)).
- `io.readLine`/`io.readAll` decode UTF-8 **strictly**, regardless of locale:
  invalid bytes are a `RuntimeError` with `expects UTF-8 input.`, never echoed.
- `str(x)` returns the display form (a top-level string without quotes); `repr(x)` returns the
  debug form (quoted/escaped string). Both accept any value, have arity 1 and return
  `String`; inside lists both use the same formatting today. Global builtins are
  immutable: redefining `chars`/`charCodeAt`/`fromCodePoint`/`join`/`len`/`str`/`repr`/
  `range`/`substr`/`Int`/`Float`/`math` in the global scope is
  an error; a local and a parameter may shadow them. `clock` is no longer a builtin; it can be used
  as an ordinary name.
- `range(start, end, step)` is a native of arity 3 and requires `Int`; it returns `Range`.
### Conversions and `math`

Casts are explicit with `as`; there is no implicit conversion:

```lox
val i = 3.9 as Int        # 3 (truncates toward zero)
val f = 3 as Float        # 3.0
val d = anyValue as Dog   # runtime check
```

- `Int as Float` rounds to f64 (may lose precision above `2^53`).
- `Float as Int` truncates toward zero; `NaN`, `Inf` or outside `[INT_MIN, INT_MAX]`
  is a fatal error (`Can't cast this Float to Int.`).
- `Any as T` checks at runtime: numbers convert to `Int`/`Float`; classes, lists and
  maps use the same check as `is`. `Any` é **top type**: `T` é atribuível a `Any`, mas
  `Any` não é atribuível implicitamente a `T` (armazenamento, argumento, retorno ou
  índice); escreva `x as T` ou estreite com `is`/nil.
- `T as T` is the identity; `as Any` returns the value. A union target (`Int?`, `Int | String`)
  does not exist yet; use narrowing/`is`.
- A string does not become a number through a cast; use `parse`.

```lox
val n = Int.parse("42")      # Int? (nil if invalid)
val f = Float.parse("3.14")  # Float?
```

`Int.parse`/`Float.parse` are members of the native `Int`/`Float` namespaces; invalid text,
empty text, text with spaces or out of range returns `nil`. There is no `42.toString()`; use `str`.

`math` is a read-only native namespace:

```lox
math.abs(x)   math.min(a, b)   math.max(a, b)   math.clamp(x, lo, hi)
math.floor(x) math.ceil(x)     math.round(x)    math.trunc(x)
math.sqrt(x)
```

- `abs/min/max/clamp` accept `Int`/`Float` and promote on mixing; `min/max` take two
  arguments; `clamp` requires `low <= high`.
- `floor/ceil/round/trunc` return `Int`; they require a finite value in the i64 range. `round`
  rounds halfway away from zero.
- `sqrt` returns `Float`; a negative value becomes `NaN`.
- `abs(INT_MIN)` wraps in release and is an error under `--debug`.
- **Outside 1.0**: `log`, `exp`, `sin`, `cos`, `tan`, `pow` and `math.pi`; they depend on libm
  and are outside I3. See [ADR-0029](../adr/0029-conversoes-math.md).

- Lambdas: `fn(x) => expr` (expression body, implicit return) and `fn(x) { ... }`
  (block with `return`), with an optional `-> Type` before the body. They are closures over the
  environment where they were evaluated; `this`/`super` are lexical and `return` returns from the lambda.
  Parameters follow the function rules, but **defaults are an error**. `print` of a lambda outputs
  `<lambda>`. Typing is in “Types and `--check`”. See
  [ADR-0022](../adr/0022-lambdas.md).

## Types and `--check`

Type annotations exist in the AST, but the **interpreter ignores them**: types are erased at
runtime. Checking is opt-in via the CLI (`--check`), which does not execute the program.

```lox
fn sum(a: Int, b: Int = 10) -> Int {
  return a + b;
}

val x = sum(1);               // Int inferred, no annotation
val name: String? = nil;      // String | Nil
val label = name or "unnamed";  // String (truthy removes Nil)
```

- Under `--check`, functions and methods require annotations on **all parameters and on the
  return type**; `init` does not declare a return. A parameter/field without an annotation and without an initializer
  is an error; a local without an initializer too. Lambdas in `val` can infer parameters and
  generalize the scheme (T4); `fn` remains an explicit contract. See
  [ADR-0033](../adr/0033-inferencia-t3c-t4.md) and [ADR-0034](../adr/0034-t3c-revertido.md).
- Top-level function signatures are known **before** the bodies: one function can
  call another declared later, including mutual recursion. Top-level code still follows the
  statement order: calling a function before its declaration is still an error; class methods and
  fields follow the class order. See
  [ADR-0020](../adr/0020-assinaturas-explicitas.md).
- Locals and expressions are inferred: `val x = f()` does not need a type.
- Types: `Int`, `Float`, `Bool`, `String`, `Nil`, `Any`, `Never`, `Range`, classes,
  `List[T]`, `Map[K, V]`, function types `fn(Int) -> Int`, unions `A | B` and `T?`
  (= `T | Nil`). `Int` is non-null. `List[T]` and `Map[K, V]` are invariant:
  `List[Int]` is not `List[Float]` or `List[Any]`; `Map[String, Int]` is not
  `Map[String, Any]`.
- Type alias: `type UserId = Int` is **transparent** and non-generic; the name expands to the
  target in any annotation, `List`/`Map`, tuple, union, `T?`, function type, `is`/`as` and
  interface bound. Aliases are top-level, may reference later declarations and
  other aliases, and cycles/collisions are errors. `UserId` and `Int` are the same type: there is no
  nominal type, constructor or runtime distinction. `class C(Alias)` and
  `class C implements Alias` still require the real class/interface name. See
  [ADR-0039](../adr/0039-decisoes-tipos-pendentes.md) and
  [ADR-0084](../adr/0084-type-alias.md).
- Function types: parameters are **contravariant** and the return is **covariant**;
  defaults count as an arity range. A class (`Animal`) is assignable to the
  signature of its constructor (`fn(String) -> Animal`), but an instance (`: Animal`)
  is not. See [ADR-0021](../adr/0021-tipos-de-funcao.md).
- Variadics: the last parameter may be `...xs: T`; inside the body `xs` is `List[T]`.
  Valid in functions, methods, interfaces and lambdas; `init` is rejected in v1. The call
  accepts extras (`f(1, 2, 3)`) or a **final spread** (`f(a, ...xs)`), which fills
  only the rest and requires the fixed parameters explicitly; `f(...xs)` is only valid without fixed parameters. The type of the
  spread is `List[T]`; `f(...xs, 2)` and a spread in the middle are parser errors. Defaults on the
  fixed parameters still apply. See [ADR-0083](../adr/0083-variadicos.md).
- Generic functions introduce type parameters (`T`, `U`) that may appear in
  `List[T]`, `Map[String, T]`, `fn(T) -> U`, unions and `T?`. The checker creates a fresh
  type variable per declaration and resolves the call by unification: arguments and the expected
  type (return, annotated `val`, function argument) fill in the `T`s. If any are left
  without inference, it is an error (`Can't infer type argument(s) 'T'.`). There are no constraints,
  declared variance, explicit type application or `T` in a `Map` key without a constraint;
  `Any` does not infer `T`. `val f = fn(x) => x` is generalized (T4); a `fn` parameter still
  requires an annotation (T3c rejected). At runtime types are erased; the backend monomorphizes
  ([ADR-0027](../adr/0027-generics-t3b.md), [ADR-0033](../adr/0033-inferencia-t3c-t4.md),
  [ADR-0034](../adr/0034-t3c-revertido.md)).
- Lambdas: `fn(x) => expr` and `fn(x) { ... }`. The expression body becomes an implicit
  return; the block requires `return`. The expected type fills in unannotated parameters
  (`aplicar(fn(x) => x * 2, 3)`); without context, in `val`, the parameters are inferred as
  type variables and the scheme is generalized (`val id = fn(x) => x` works for `Int` and
  `String`); `var` still requires context. The return is inferred;
  mixing non-nil `return`s requires `-> T`; a block that may fall through adds `Nil`,
  and a declared non-nil return requires all paths. Defaults in a lambda parameter are
  an error. `this`/`super` are lexical and `return` returns from the lambda. `print` of a lambda outputs
  `<lambda>`. See [ADR-0022](../adr/0022-lambdas.md).
- Generic functions: `fn id[T] (x: T) -> T { ... }`. The type parameters are declared
  between the name and `(` and are valid in annotations and in the body (`T`, `List[T]`, `Map[String, T]`,
  `fn(T) -> U`). The body is checked **once**. Without bounds, only universal operations are valid
  (`==`, `str`/`repr`, assignment, lists/maps, calling passed functions); `a + b` and
  `len(x)` on `T` are errors until a bound exists. The call infers by unifying the
  arguments and the expected type; `id(1)` ⇒ `T = Int`. Inference is left to right:
  a lambda before the argument that fixes `T` needs an annotation. There is no
  `id[Int] (1)` or generic function as a value (`val f = id` is an error); zero-arg requires
  context (`val xs: List[Int] = empty();`). Recursion with the same type arguments is
  allowed; polymorphic recursion is rejected. Generic methods do not exist yet.
  The runtime erases `T`; the backend monomorphizes (ADR-0027). See
  [ADR-0027](../adr/0027-generics-t3b.md).
- Function constraints: `fn max[T: Ord]`, `fn sum[T: Ord + Num]`,
  `fn juntas[T: A + B]`. `Ord` applies to `Int`/`Float`/`String` and enables
  `< <= > >=` between two values of the same `T`; `Num` applies to `Int`/`Float` and enables
  `+ - * % **` and unary `-` (not `/`, `//` or bitwise). An interface bound enables the interface's
  methods on `x`; two interfaces with the same method with different signatures are
  ambiguous. At the call site, each concrete type argument must satisfy the bound (`Bool`,
  `Any`, unions and optionals do not satisfy it); a `TyVar` from another generic satisfies it only if
  it carries the same bound. Bounds exist only on **functions** in v1; classes/enums with
  `[T: ...]` are parser errors. The runtime erases bounds; the backend monomorphizes like
  T7. See [ADR-0081](../adr/0081-constraints-generics.md).
- Lists: `[1, 2]` infers `List[Int]`; `[1, 2.0]` infers `List[Float]`; `[]` requires an expected
  type; non-numeric mixing requires an explicit annotation. `push`/`xs[i] = v` check the
  element; `xs[i]` checks that the index is `Int`; `len` checks list/string/map. `xs.pop()` and
  `xs[i]` return `T`.
- Maps: `{"a": 1}` infers `Map[String, Int]`; keys and values need a common type;
  `{}` requires an expected type; `m[k]` checks `k` against `K` and returns `V`; `m[k] = v` checks
  `v`; `m.get(k)` returns `V?`; `m.has(k)` returns `Bool`; `m.remove(k)` returns `V`;
  `m.keys()`/`m.values()` return `List[K]`/`List[V]`; `for k in m` binds `k: K`; `len(m)`
  is `Int`. Only `String`, `Int`, `Bool` (and unions of those) are valid keys; `Map[Float, V]`
  is a type error.
- Interpolation: each expression is checked normally and the result is `String`; any
  type is converted by `stringify`.
- Promotion is `Int → Float` only in checking; `Float → Int` will require an explicit cast.
- Functions and methods with a **non-nil** return must return on all paths under
  `--check` (`Function 'f' must return Int on all paths.`); `return;` in that case is an error.
  Nilable types, `Any`, `Never` and `<error>` are excluded. See
  [ADR-0023](../adr/0023-soundness-do-checker.md).
- A call error identifies the argument: `Argument 2: Expected String, found Int.`
  Passing the class where an instance is expected is reported as
  `Expected an instance of Animal, found the class Animal.`
- Conditions use **truthiness** (any type); `and`/`or` return the operand. The checker
  types `or` as `truthy(A) | B` and `and` as `falsy(A) | B`; `not` returns `Bool`.
- `expr is T` returns `Bool` and tests the value at runtime: primitives, class/subclass,
  `List[T]`/`Map[K, V]` (including elements; O(n)) and unions. For a class, the identity is the
  **class object** ([ADR-0044](../adr/0044-identidade-classe.md)): `Derived() is Base`
  is true, but a local class with the same name is not the global class. `Any` is always
  true, `Never` always false; function types are rejected under `--check`. A class
  as a value is not an instance (`Animal is Animal` is `false`). In the expression, a union on the
  right side requires parentheses (`x is (Int | String)`); see
  [ADR-0067](../adr/0067-desambiguacao-sintatica.md) and
  [ADR-0025](../adr/0025-is-e-narrowing.md).
- Narrowing: `if (x != nil)`, `if (x == nil)`, `if (x)`, `if (x is T)` and `not` around them
  refine `x` in the branch; `if (x == nil) { return }` refines the rest of the block. `and` in the true
  branch and `or` in the false branch combine refinements; `while` applies the true refinement
  to the body. `val` and `var` narrow, but an assignment invalidates the refinement.
  Calls that may execute user code (function, method, constructor, function value
  or user iterator) invalidate refinements of a mutable `var` captured by a closure;
  pure native calls (`print`, `len`, `str`, `repr`, `chars`, `range`, `List`/`Map`
  methods) do not. The body of a function/lambda starts without the caller's refinements. **Fields and literal indices** also narrow
  (`p.name`, `xs[0]`, `m["k"]`); mutating the path (`p.name = ...`), the root (`p = ...`),
  **any call** or an assignment to a field/index invalidates all field/index refinements
  (no aliasing; [ADR-0045](../adr/0045-narrowing-representacao.md)), and the normal
  exit of `while (x != nil)` refines the rest of the block through the false branch.
  `if`/`elif`/`else` join the branches that fall through (intersection of keys, union of
  types); a branch that always returns does not contribute. `while`/`for-in` join the entry with the
  body exit (zero iterations) and `try` unions the body and the handlers that fall through.
  Assignment updates the refinement to the assigned type. A dynamic index (`xs[i]`) does not narrow;
  aliasing and full CFG are outside; see [ADR-0018](../adr/0018-narrowing.md),
  [ADR-0025](../adr/0025-is-e-narrowing.md), [ADR-0032](../adr/0032-narrowing-campos-indices.md)
  and [ADR-0086](../adr/0086-narrowing-captura-e-merge.md).
- Type errors are **compile** errors and prevent execution; exit code 65.
- Current limitations: aliasing/complete effects, generic classes/methods,
  parameter inference without an annotation, union function types/casts in `is`,
  and union casts in `as`; lambdas exist, but without trailing closure, single parameter without
  parentheses or implicit block return. Annotating `Float` does not convert the value at runtime
  (the tree-walk remains dynamic).

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

- `class Name { fields and methods }` creates the class and binds it to the name in the current scope.
- `class Name(Super) { ... }` declares single inheritance; `class Name < Super` is an error.
- Fields are **declared** in the body with `val`/`var`; there are no dynamic fields:
  `obj.x = 1` on an undeclared field is an error (`Undefined field 'x'.`).
- Every declared field must be initialized: by a constant initializer
  (`var age = 0`) or by an assignment in `init`. At the end of `init`, an uninitialized field is a
  runtime error (`Field 'x' must be initialized.`). Under `--check`, every field without an
  initializer must be assigned on **all paths** of `init`; `if`/`else` uses
  intersection, an early `return` requires the fields to be ready and loops do not count as
  definite assignment. See [ADR-0023](../adr/0023-soundness-do-checker.md).
- A `val` field can only be assigned **inside `init`** (and once); outside it the resolver
  reports `Can't assign to immutable field 'x'.` and the runtime also refuses a second
  assignment. A `var` field is mutable in any method.
- A field and a method with the same name, or a redeclared field (including in the subclass), is a
  compile error (`Field 'x' already declared.` / `Field 'x' conflicts with a method.`).
- Classes may be declared in a block/function (local classes); the type name resolves in the
  lexical scope and `is`/`as` compare the class object ([ADR-0044](../adr/0044-identidade-classe.md)).
- Field initializers are constants in v1 and run when the instance is created, before
  `init`.
- Methods **do not** use `fn`; they are functions with `this` bound.
- `this` is **implicit**: methods do not receive `self`.
- `Name(args)` creates an instance, runs `init` (if it exists) and returns the instance.
  The class arity is the `init` range (0 if there is none).
- `init` always returns the instance: `return;` is allowed, `return value;` is a compile
  error (`Can't return a value from an initializer.`).
- `this` only exists inside methods; outside a class it is a compile error
  (`Can't use 'this' outside of a class.`).
- Fields take precedence over methods on read.
- Reading a property that is neither a field nor a method: `Undefined property 'x'.`
- `obj.field = v` requires an instance: `Only instances have fields.`
- Reading a property of a non-instance: `Only instances have properties.`
- A method read as a value remains bound to the instance (`var f = obj.m; f();`).

### Generic classes

```lox
class Box[T] {
  var value: T
  init(value: T) { this.value = value }
  get() -> T { return this.value }
}

val b: Box[Int] = Box(1)   # Box(1) infers Box[Int]
print(b.get())              # 1
```

- `class Box[T]` and `class Pair[A, B]`: `T` is valid in fields, methods, `init` and `this`; the type
  is `Box[Int]`, `Pair[Int, String]` etc. (`T?`, `List[T]` and nesting work).
- `Box(1)` infers the arguments from `init`; with an expected type (`val b: Box[Int] = Box()`),
  the expected type fixes the arguments. Without `init` and without an expected type, it is an error asking for an annotation.
  `Box` without arguments in type position is an arity error.
- The arguments are **invariant**: `Box[Int]` is not `Box[Any]` or `Box[Float]`
  (mutable fields would make covariance unsound). `Any` as an inference argument
  is also rejected: `Box(x)` with `x: Any` asks for an annotation.
- `this` is `Box[T]` and `init` returns `Box[T]`; the runtime erases `T` (`print(Box(1))` →
  `Box instance`).
- Outside the MVP: generic methods (`fn map[U]`), inheritance from `Box[Int]`, constraints on
  classes, explicit type application (applying arguments to the call) and `is`/`as Box[Int]`
  (rejected with an explicit message). See [ADR-0040](../adr/0040-generics-classes-desenho.md).

### Inheritance

- Syntax: `class B(A)` (single inheritance; no `extends`, `:` or `<`).
- Methods and `init` are inherited; the subclass method **overrides** the superclass one
  silently (there is no `override` keyword). Under `--check`, the override signature is
  compared with the superclass one: contravariant parameters, covariant return and defaults
  as an arity range; `init` is excluded. See
  [ADR-0023](../adr/0023-soundness-do-checker.md).
- A subclass **without** `init` inherits the superclass `init`. If the subclass defines `init`, it
  must call `super.init(...)` explicitly; there is no automatic call.
- Fields are inherited; redeclaring a field in the subclass is an error. An inherited `val` cannot be
  reassigned (not even in the subclass `init`); an inherited `var` can.
- Superclass field initializers run when the instance is created, before `init`.
- `super.method(args)` looks up `method` in the superclass and binds it to the current `this` (not to
  the "superclass this").
- `super` may only appear inside a class method **with** a superclass:
  - outside a class → `Can't use 'super' outside of a class.`
  - class without a superclass → `Can't use 'super' in a class with no superclass.`
- Inheriting from itself → compile error: `A class can't inherit from itself.`
- The superclass must be a class at runtime: `Superclass must be a class.`
- Missing `super.method` → `Undefined property 'method'.`

### Interfaces

```lox
interface Shape {
  area() -> Float
  fn name() -> String { return "shape" }
  fn description() -> String { return "${this.name()}:${this.area()}" }
}

class Circle implements Shape {
  val radius: Float
  init(radius: Float) { this.radius = radius }
  area() -> Float { return 3.14159 * this.radius * this.radius }
}

val shape: Shape = Circle(2.0)
print(shape.description())   # shape:12.56636
```

- An interface is **nominal** ([ADR-0080](../adr/0080-interfaces-nominais-implementacao.md)):
  the class declares `implements`; having the right methods is **not** enough (unlike
  `Protocol`/Go). The interface must be declared **before** the class that implements it.
- An interface is a **type, not a value**: `print(Shape)` is an error; `Shape` only appears in an annotation.
- A method is **abstract** (no body) or **default** (with a body). A default is checked
  once, with `this` of the interface type; it can call the other interface methods (which
  dispatch on the class), but it **does not** access fields, `super` or `init`.
- Conformance:
  - the class must declare every abstract method (or inherit a default);
  - the signature must be **exact** with the interface one (parameters and return); the backend ABI uses the
    interface signature in the `itab`, so representation covariance/contravariance
    is not accepted in v1;
  - an own or superclass-inherited method **wins** over the default;
  - two distinct interfaces with the same method require an explicit class override,
    even if the defaults are equal;
  - a field with the name of an interface method is an error.
- Runtime resolution order: class method → superclass → interface defaults in
  `implements` order; it is deterministic.
- Assignability: `Class` is assignable to `Interface` if it implements it directly or
  transitively through the superclass; `Interface` is not assignable to `Class`. `I?`,
  `List[I]`, an interface field/parameter/return are valid; the concrete instance remains
  the value at runtime.
- `is`/`as` with an interface do **not** exist yet: the checker rejects them with a targeted
  diagnostic (`Interface types aren't supported in 'is' yet.`).
- Interfaces have no state, generics or inheritance in v1. In the LLVM backend the feature is
  compiled via ABI B2 from
  [ADR-0080](../adr/0080-interfaces-nominais-implementacao.md): deterministic
  `interface_id` and a `{id, itab}` table in the class descriptor; every implemented class
  (including through inheritance) gets the `itab`, with a default or an override per method.

## Enums and match

```lox
enum Color { Red, Green, Blue }
enum Shape { Circle(Float), Rect(Float, Float) }

val s: Shape = Shape.Circle(2.0)
val area = match s {
  Shape.Circle(r) => 3.14 * r * r
  Shape.Rect(w, h) => w * h
}
```

- `enum Name { Variant, Variant(Type, ...) }` declares a closed type; variants have a
  **positional** payload and are accessed with a namespace (`Color.Green`,
  `Shape.Circle(1.0)`). Enums are declared at the top of the program.
- Enums may be generic (`enum Pair[A, B]`); `Result[T, E]` is built in, with
  `Result.Ok(T)`/`Result.Err(E)`, and cannot be redefined. `Option` remains `T?`.
- Type: `Shape`, `Result[Int, String]`; arguments are invariant. `is`/`as` accept an enum
  without arguments (`x is Color`); with arguments they are rejected (the runtime erases `T`).
- `match` is an **expression**: `match e { Pattern => expr ... }`. v1 patterns:
  `Name.Variant`, `Name.Variant(a, b)` (positional bindings) and `_`. Arms are separated
  by a line, `;` or `,`; using `match` as a statement discards the result.
- Exhaustiveness is **mandatory**: all variants covered or `_`; a missing one is an error
  (`Non-exhaustive match; missing Shape.Rect.`); a duplicate variant/arm after `_` is
  `Unreachable match arm.` The scrutinee must be an enum (not `Any`/union).
- Pattern bindings have the payload type (`Result.Ok(v)` → `v: T`); the type of `match`
  is the union of the arms. Without `--check`, a `match` with no matching arm is a runtime error
  (`No match arm matched.`).
- Equality is structural (enum, variant and payload); `print(Color.Green)` →
  `Color.Green`, `print(Shape.Circle(1.0))` → `Shape.Circle(1.0)`. Enums are not iterable,
  have no `len` and are not `Map` keys.
- Outside v1: literal/`nil` patterns, guards, nesting, `|`, `match` on unions and
  null variants of a generic enum. The backend rejects `enum`/`match` until L6.

## Exceptions

```lox
class MyError(Exception) {
  init(msg: String) { this.message = msg }
}

try {
  raise MyError("falhou")
} except MyError as e {
  print("meu: ${e.message}")
} except RuntimeError as e {
  print("runtime: ${e.message}")
} finally {
  print("sempre")
}
```

- `Exception` is the built-in base; `RuntimeError` is a built-in subclass and represents
  any runtime error (division by zero, index, etc.). The user may declare
  `class MyError(Exception)` with `message`. Every exception also exposes
  `site: String` — `arquivo:linha:coluna` of the throw's caller (for `t.expect(...).toBe(...)`
  this is the `expect` line) or `""` when there is no position
  ([ADR-0120](../adr/0120-localizacao-de-falha-em-excecoes.md)).
- `raise Expr` requires an `Exception` instance; `raise;` inside `except` re-raises the
  current exception. Outside `except`, `raise;` is an error.
- `try` is a statement; `except Type as e` is typed, multiple and evaluated in order;
  `except Exception as e` is catch-all and must be last. At least one `except` or
  `finally` is mandatory.
- Runtime errors are converted to `RuntimeError` in `try`; catching specific types
  (`DivisionByZero`) is left for later. `finally` always runs and its
  `return`/`raise` wins over the previous flow.
- Uncaught exception: `file:line:col: error[R1010]: Unhandled exception: <type>:
  <msg>`, exit 70, followed by the stack trace ([ADR-0089](../adr/0089-stack-trace-de-runtime.md)).
  The L6 backend implements `try`/`raise` with the same output ([ADR-0062](../adr/0062-l6-excecoes-unwinding.md)).

## Errors

| Phase | When | Exit code (file) |
| --- | --- | --- |
| lexical/syntax/resolver | before executing | **65** |
| runtime | during execution | **70** |
| file not found | before everything | **66** |

- Compilation format: `file:line:col: error[CODE]: message` + a snippet with a caret
  (`human`) or only the header (`short`); catalog and JSON envelope in
  [`erros.md`](erros.md) ([ADR-0075](../adr/0075-diagnosticos-estruturados.md)).
- Runtime format: `file:line:col: error[CODE]: message` (no caret, same as the binary).
- Messages are in English (compatibility with the book and tests).
- Compile errors are **accumulated** (the parser tries to recover; the resolver reports
  all of them), ordered by `(file, offset, code)`, without duplicates and limited by
  `--max-errors`; runtime errors stop at the first one.
- Error codes are stable; columns, spans, JSON, stack trace, `fixes[]`, provenance
  `notes` and LSP exist
  ([ADR-0075](../adr/0075-diagnosticos-estruturados.md),
  [ADR-0089](../adr/0089-stack-trace-de-runtime.md),
  [ADR-0099](../adr/0099-notas-de-proveniencia.md),
  [ADR-0090](../adr/0090-lsp-escopo-e-hospedagem.md)).
- In the REPL, each line starts with a clean error state and the environment remains.

## Deliberate differences from the book

- Division by zero is an error (the book returns `inf`).
- The REPL accepts an optional trailing `;` and prints the value of expressions.
- `return` at the top level is a compile error as early as ch. 11 (in the book, the resolver does this).
- Numbers are separate `Int` and `Float` (the book uses only `float`); `/` is always `Float`,
  `%` is truncated and `Int` wraps — see [ADR-0006](../adr/0006-int-float-separados.md).
- `val`/`var` do not exist in the book (which has only mutable `var`); see [ADR-0005](../adr/0005-val-var-imutabilidade.md).
- `for x in` and `Range` (`0..10`) do not exist in the book; see
  [ADR-0007](../adr/0007-ranges-e-iteracao.md).
- `List[T]` (literal, indexing, `push`/`pop`, `len` and structural equality) does not exist in the
  book; see [ADR-0015](../adr/0015-listas-tipadas.md).

Everything else follows the book's jlox, including the messages.


## Modules

### stdlib T1

> Per-module reference, generated from the signatures/doc comments and the builtins
> registry: [`../stdlib/`](../stdlib/).

- `std.strings`: `isEmpty`, `isBlank`, `trim`/`ltrim`/`rtrim`, `startsWith`/`endsWith`,
  `contains`/`indexOf`/`lastIndexOf`, `split`/`splitLines`/`lines`/`words`,
  `repeat`, `upper`/`lower`/`capitalize`, `reverse`, `count`, `replaceFirst`/`replaceAll`,
  `slice`, `padStart`/`padEnd`.
- `std.lists`: `isEmpty`, `length`, `map`, `filter`, `each`, `fold`, `reduce`, `any`,
  `all`, `none`, `find`, `findIndex`, `contains`, `indexOf`, `reverse`, `take`, `drop`,
  `slice`, `sum`, `first`, `last`, `count`, `min`, `max`, `getOr`.
- `std.maps`: `entries`/`toList` (`(String, V)` pairs), `fromEntries`, `merge` (the right
  one wins), `pick`, `omit`, `mapValues`, `filterKeys`, `filterValues`, `invert`
  (`Map[String, String]`), `hasValue`, `getOr`. The API is `Map[String, V]`: the checker
  does not yet express generic key constraints (post-MVP); `Int`/`Bool` keys use
  the language methods.
- `std.numeric`: `gcd`/`lcm`, `isPrime`/`primes`, `factorial`, `powMod`, `digitSum`,
  `isEven`/`isOdd`/`sign`, `mean`/`median`/`mode`/`variance`/`stddev` (statistics of
  `List[Int]`; an empty list returns `nil`; population variance) and
  `roundTo`/`toBase`/`fromBase` (base 2..36). An invalid domain (negative `factorial`,
  base out of range) raises `RuntimeError`; invalid `fromBase` returns `nil`.
- `std.asserts`: `assert`, `assertEq`, `assertNotNil` (returns the narrowed value) and
  `fail`; the failure is a `RuntimeError`, catchable by `except RuntimeError as e`.
- `std.results`: `isOk`/`isErr`, `map`/`mapErr`, `unwrapOr`, `andThen` and `toOptional`
  for `Result[T, E]`. Since `andThen` receives `fn(T) -> Result[U, E]`, a lambda that
  constructs `Result.Ok`/`Result.Err` does not infer the generic enum yet; use a named
  function with an annotated return (post-MVP checker gap).
- `lists.sort(xs, compare)` requires `compare: fn(T, T) -> Int` (negative/zero/positive),
  is stable and returns a new list. `sortBy`/`groupBy` do not exist yet.
- `lists.zip`, `flatten`, `flatMap`, `unique`, `chunk` and `partition` are generic;
  `partition` returns `(yes, no)`.
- These functions are pure Lox over the kernel; they are deterministic and enter the T1 corpus.

### stdlib T2

The T2 modules are pure Lox over the kernel and add no syntax
([ADR-0079](../adr/0079-stdlib-t2.md)). The deterministic ones enter the `t2` corpus; the
**ambient** ones ([ADR-0072](../adr/0072-stdlib-batteries.md) §5) are outside I1 and have tests
with fixed input.

- `std.json`: `parse(text) -> Any`, `stringify(value) -> String` and
  `pretty(value, indent = 2) -> String`. Objects become `Map[String, Any]` (insertion
  order), arrays become `List[Any]`, `Int`/`Float` are distinct and `null` becomes `nil`.
  Invalid JSON also becomes `nil`; nesting above 16 is invalid. `stringify`
  raises `RuntimeError` for a non-finite `Float` or a value that is not JSON.
- `std.fmt`: `format(template, List[Any])` with `{}` and `{{`/`}}`, `pad(text, width,
  fill = " ")` (on the left), `commas`, `fixed(value, digits)`, `percent(value, digits = 0)`
  and `bytes(n)` (B/KiB/MiB/GiB/TiB). No locale; extra/missing arguments and `fixed` outside
  0..15 raise `RuntimeError`.
- `std.bytes`: `Builder` (incremental byte a byte over `List[Int]`; `push`, `pushByte`,
  `len`, `build`), `ChunkBuilder` (whole `Bytes` chunks with balanced concatenation; better
  for large blocks), `compare` (lexicographic, returns -1/0/1), encoders `u16be`/`u16le`/
  `u32be`/`u32le`/`u64be`/`u64le` and decoders `readU16be`/`readU16le`/`readU32be`/
  `readU32le`/`readU64be`/`readU64le` (the 64-bit helpers use the two's-complement bit
  pattern; decoders return `Int?`, nil when the bytes do not fit). Pure and deterministic;
  in the `t2` corpus.
- `std.paths` (POSIX, lexical, does not touch the disk): `join` (an absolute second argument wins,
  without normalizing), `dirname`, `basename`, `ext`/`stem` (a leading dot does not count as an
  extension), `normalize` (collapses slashes, resolves `.`/`..`), `isAbsolute` and `split`.
- `std.fs` **ambient**: `readText -> String?`, `readLines -> List[String]?` (drops the
  final newline), `writeText -> Bool`, `appendText -> Bool` (reads and rewrites; creates the
  file if absent), `exists -> Bool` and `listDir -> List[String]?` (sorted, without
  `.`/`..`, `nil` if it is not a readable directory). `File.readBytes(n)` reads up to `n`
  raw bytes (`Ok(nil)` at EOF), without UTF-8 validation.
- `std.io`: `write`/`writeErr` (deterministic), `readLine -> String?`, `readAll ->
  String` and `prompt(message) -> String?` (writes and reads a line); reading is ambient.
  Input that is not valid UTF-8 is a `RuntimeError` (without a traceback), not corrupted text.
- `std.cli`: `parse(args, spec) -> Map[String, Any]` with `spec` as a `List[String]` of
  `flag:NAME`, `option:NAME` and `positional:NAME` entries; accepts `--name value`,
  `--name=value` and `--`; flags become `Bool`, options/positionals become `String` or `nil`.
  `flag`/`option`/`positional` read the result and `usage(program, spec)` generates the text.
  Invalid usage (unknown option, missing value, flag with a value) is a `RuntimeError`.
- `std.sets`: `Set[T]` with `add`, `has`, `remove` (returns `Bool`, no error if absent),
  `len`, `toList` (insertion order), `union`, `intersect`, `difference` and
  `fromList(List[T])`. The internal field is `Map[Any, Bool]`: `T` must be `String`, `Int`
  or `Bool` at runtime; `Set[Float].add` fails with the `Map` key error (generic
  constraints are post-MVP).
- `std.csv`: `parse(text) -> List[List[String]]?` (RFC 4180; accepts CRLF/LF, quotes with
  `""`, newlines inside a field; `nil` if malformed) and `stringify(rows) -> String` (CRLF,
  final newline, quoting when needed; an empty list generates empty text and an empty row is
  an error).
- `std.utf8`: `byteLen(text) -> Int` (UTF-8 bytes), `utf16Len(text) -> Int` and
  `utf16Column(text, index) -> Int` (UTF-16 width of the prefix of `index` code points,
  limited to `0..len(text)`). Pure Lox over `charCodeAt`, deterministic, in the `t2` corpus.
- `std.proc` **ambient** (POSIX, [ADR-0095](../adr/0095-processos-streams-poll.md)):
  `Stream` (`read`, `write`, `close`), `Process` (`stdin`/`stdout`/`stderr`, `wait`,
  `kill`, `close`), `Output` (`code`, `stdout`, `stderr`), `spawn(argv) -> Process?` and
  `run(argv, stdin = "", timeoutMs = 0) -> Output?`. No shell; `run` drains stdout/stderr
  with `poll`, kills on timeout and returns `nil`; `stdin` has the practical limit of the pipe
  buffer (~64 KiB). Outside the I1/I3 corpus.
- `std.iter`: `enumerate(items)`, `zip(left, right)`, `sum(List[Int])`,
  `sumFloat(List[Float])`, `contains`, `any`, `all` and `find` (the first match or `nil`).
  The `Step[T]` enum (`Step.Item(value)`) allows iterating `nil` elements:
  `next() -> Step[T]?` terminates on `nil` and the body matches `Step.Item(value)`.
- `std.rand`: `Rand(seed)` (xorshift64*), `nextInt`, `int(min, max)` inclusive,
  `float` in `[0, 1)`, `bool` and `shuffle(items, r)`; deterministic by seed.
- `std.log` **ambient**: `Level` enum (`Debug`/`Info`/`Warn`/`Error`) and `Logger`, which
  writes `[LEVEL] message` to stderr; no timestamp.
- `std.hash`: `fnv1a32`, `fnv1a64` and `djb2` over the **UTF-8 bytes**; `sha256(text) ->
  String` (hex) and `sha256Bytes(Bytes) -> Bytes` (raw 32 bytes) are the cryptographic
  digests. The 64-bit fnv returns the bit pattern in i64 (it may be negative).
- `std.collections`: generic `Stack`, `Queue`, `Deque` and `PriorityQueue` (heap with an
  explicit comparator `fn(T, T) -> Bool`).
- `std.timex` **UTC-only**: `daysFromCivil`, `civilFromDays`, `iso`, `parseIso` (strict,
  returns `Int?`), `addDays` and `parts`; no timezone and no clock.
- `std.property` ([ADR-0098](../adr/0098-property-based-testing.md)): `Gen[T]` with
  `generate`/`shrink`, `forAll(gen, check, runs = 100, seed = 0)` and generators
  `int`, `intRange`, `bool`, `float`, `stringOf`, `listOf[T]` (with
  `listOfInt`/`listOfString` as aliases) and `oneOf`; a failure shrinks the counterexample and
  reports the seed.
- `std.test` ([ADR-0096](../adr/0096-testes-biblioteca-e-runner.md)): `Suite` (explicit state,
  because a module does not accept top-level `var`) with `describe`, `it` (runs immediately),
  `beforeEach`/`afterEach` (scoped to `describe`; outer→inner `before`,
  inner→outer `after`, even on failure), `skip`, `report` (TAP + 0/1) and `done`
  (`os.exit(report())`); matchers `expect` (`toBe`/`notToBe`), `expectGt/Ge/Lt/Le`
  (`T: Ord`), `expectNil`/`expectNotNil`, `expectList`/`toContain`,
  `expectString`/`contains`, `expectRaise`; `TestFailure`/`Skip` and `Recorder`. No
  reflection/registry; `--filter=`/`--only=` and `--list` (only prints `# test <name>`) come
  from `args()`. The test body is `fn() -> Nil`; an unhandled exception becomes `not ok`.
- `std.convert`: `toInt`/`toFloat` (`T?`), `toBool` (`"true"`/`"false"`),
  `base64Encode/Decode` and `hexEncode/Decode`. They are text-based and operate on the
  UTF-8 bytes of the text; decoding bytes that are not valid UTF-8 (or malformed text)
  returns `nil`. Hex is lowercase. For raw binary use `Bytes`/`std.bytes`.

Instance fields may have a container type (`List`, `Map`, tuple, `Range`, enum) since
ADR-0079; `Any` as a field is not yet supported by the backend.

Bundled native modules ([ADR-0126](../adr/0126-modulo-nativo-embutido-sqlite.md),
[ADR-0131](../adr/0131-regex-motor-rust-dois-modos.md)) live in `bundled/` and are imported by
the short name (`import regex`). The name is reserved: it wins over a project file with the
same name. Today: `regex`.

- `regex.compile(pattern, caseless = false, multiline = false, dotall = false, extended =
  false) -> Result[Regex, RegexError]` uses the linear engine (guaranteed linear time);
  `regex.compileFull(...)` enables backreferences and lookaround with a fixed backtracking
  limit; `tryCompile`/`tryCompileFull` return `nil` instead of the error. `Regex.isMatch`,
  `find(text)`, `findFrom(text, start)`, `findAll(text)`, `replace`, `replaceAll`, `split`
  and `close` (idempotent; there is no finalizer). `Match` carries group 0 (`text`, `start`,
  `end`) and `groups: List[String?]` for groups 1..n. Replacement expands `$0`..`$9`,
  `$name` and `${name}` (escape as `\${name}`: `${...}` is string interpolation) and
  `$$`; an unmatched group expands to the empty string. Match offsets count code points;
  `RegexError.offset` is a **byte** offset for the syntax error (`-1` when the failure is
  not a syntax error); when both engines reject the pattern they report the same byte, taken
  from the linear parser so a delegated fragment's relative span never leaks.
  `RegexError.kind` is one of `syntax`, `arguments`, `mode`, `size` or `engine`. A pattern
  that exceeds the per-program compiled-memory limit is `size`, and an analysis/
  unsupported-pattern error (left recursion, non-constant lookbehind) is `engine`; the Rust
  engine's allocations are outside the binary's Boehm heap cap (ADR-0131 §2.1). Exceeding the
  backtracking limit raises `RuntimeError`.
  The module requires the Rust
  toolchain: without `cargo`, `run`/`build` refuse with `E3022` before executing, while
  `check` stays engine-agnostic.


- A module is a `.lx` file; a folder is a path namespace, not a module.
- Modules contain only imports, `fn`, `class` and `enum`; no `val`/`var` or top-level
  statement. Import is static, with no initialization order.
- `import m`/`import m as x` creates a namespace; `from m import name [as y]` binds public names.
- A top-level name starting with `_` is private to the module; outside it `_x` is an error, including
  through the namespace (`m._x`).
- `std.` resolves in the bundle; user modules are relative to the project root.
- Without `loxia.toml`, the root is the entry's directory. With a manifest, the root is the manifest
  folder and the order is: project → dependencies → `[modules].paths` → `--module-path` →
  `std` ([ADR-0100](../adr/0100-dependencias-path.md)).
- `[dependencies] acme = { path = "../acme" }` makes `import acme.foo` look for
  `../acme/foo.lx` (the package name is not the directory name). The path is relative to the
  manifest and must exist; `std` is a reserved name and `import acme` alone is an error.
- `loxia.lock`, next to the manifest, pins each dependency by name, origin, optional
  `[package].version` (`X.Y.Z`) and the `sha256` of its `.lx` tree ([ADR-0104](../adr/0104-lock-e-frozen.md)).
  It is generated by `loxia lock` (canonical bytes: entries sorted by name, fixed key order,
  relative posix paths, no timestamp) and verified by `loxia lock --check` (exit `1` when
  stale) and `loxia fetch`.
- `--frozen` resolves dependencies only from the lock: a missing lock (when dependencies
  exist), a missing/extra package, or a different path/version/hash is an error `C0002`
  (exit 65). Without `--frozen`, `path` dependencies are read live from disk.
  `--offline` forbids the network and `--cache-dir` selects the dependency cache
  (default `.loxia/cache/` in the project root). `run`, `check`, `build`, `ast` and `test`
  never access the network; only `loxia lock` and `loxia fetch` may, and `--offline`
  forbids it there too. Only the root manifest declares dependencies: the lock is flat,
  `std` and `[modules].paths` never appear in it.
- A git dependency is `acme = { git = "https://github.com/acme/acme", rev = "v1.2.3" }`
  ([ADR-0105](../adr/0105-dependencias-git.md)). `rev` is required and is a full commit or a
  tag (never a branch); exactly one of `path`/`git` is allowed. `loxia lock` resolves the tag
  to a commit and records `git`, `rev`, `commit`, `version` (required in the dependency's
  `loxia.toml`) and the tree `sha256`. `loxia fetch` populates the cache (bare mirror plus a
  clean `git archive` checkout, no `.git`/hooks/submodules); `run`/`check`/`build` use the
  locked commit only and fail with `C0002` when the checkout is missing ("run `loxia fetch`").
  `--offline` restricts `lock`/`fetch` to the cache, and `file://` URLs are dev/test only and
  stored verbatim in the lock.
- A dependency imports its own package by name (`acme.base`) or another declared
  dependency; it does not see the project or `[modules].paths`. `[modules].paths` are loose
  roots (vendor/monorepo): `import shared.util` resolves `<root>/shared/util.lx`.
- `..` and absolute paths remain forbidden in `import`; they only appear in the manifest
  `path` or in `--module-path`. The same module in two roots is an **ambiguity error**
  (never “first wins”), with relative paths in the diagnostic.
- No `*`, no re-export and no module as a value.
- A module is **pure by construction**: only top-level declarations, so importing executes no
  effect; an unused import is `W1002` and removing the line is `safe` (fix).
