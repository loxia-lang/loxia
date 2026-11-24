---
sources:
  - loxia_core/diagnostics/**
  - loxia_core/execution/interpreter.py
  - loxia_core/execution/limits.py
  - loxia_core/frontend/scanner.py
  - loxia_core/frontend/tokens.py
  - loxia_core/frontend/parser.py
  - loxia_core/frontend/source_index.py
  - loxia_core/semantics/resolver.py
  - loxia_core/semantics/checker.py
  - loxia_core/loader/loader.py
  - runtime/**
  - loxia/cli.py
  - loxia/cli_args.py
  - loxia/cli_commands.py
  - loxia/engine.py
  - tests/test_diagnostics.py
  - tests/test_provenance.py
---

# Errors

Catalog of what the interpreter reports today, with phase and consequence. Messages are in
English; CLI text remains in Portuguese, and this documentation is in English. The decision behind the format
is in the [ADR-0075](../adr/0075-diagnosticos-estruturados.md).

## Format and exit codes

Every compilation diagnostic has a **stable code** (`error[E3001]`), a position and, in the
`human` format, a source snippet with a caret:

```
example.lx:3:7: error[E2001]: Already a variable with this name in this scope.
  |
3 |   var a = 2;
  |       ^
```

| Phase | `human` format | Exit code |
| --- | --- | --- |
| lexical | `file:line:col: error[E0xxx]: message` + caret | 65 |
| syntax | `file:line:col: error[E1xxx]: message` + caret | 65 |
| resolver | `file:line:col: error[E2xxx]: message` + caret | 65 |
| checker (`--check`) | `file:line:col: error[E3xxx]: message` + caret | 65 |
| backend | `file:line: error[E4xxx]: message` (no column/caret) | 65 |
| runtime | `file:line:col: error[R1xxx]: message` (no caret) | 70 |
| CLI/timeout | `error[C0001]: message` (no location) | 124 |
| missing file | `Erro: Arquivo 'x' não encontrado.` (stderr) | 66 |

Backend internal errors (`E4002`) are prefixed with `internal lowering error:` or
`internal error:`; `E4001` is reserved for declared gaps (`... is not supported by
the backend yet.`). C compiler failures are sanitized so temporary paths are not leaked.

- `human` (default) shows header + snippet; `short` shows only the header; `json` shows
  the v1 envelope; `--json-lines` emits `start`/`diagnostic`/`summary` per line. Em `fmt`
  com vários alvos, `--json` agrega num único envelope (com o total no `summary`) e
  `--json-lines` num único `start` + um único `summary`. Flags:
  `--error-format=human|short|json`, `--json`, `--color=auto|always|never` (respects
  `NO_COLOR`) and `--max-errors N` (default 20; `0` = unlimited).
- **Warnings** (`W1xxx`, today `W1001` local never read) have `severity: warning`, exit 0 and
  appear in the `summary`; `-Werror` turns them into an error (exit 65) only in `check`/`build`.
  `run` does not emit warnings to preserve I1 (the binary does not have them).
- `--timeout=MS` applies to `run`/`check`; the timeout is `C0001` + exit 124. `--watch` only in
  `check`; changes re-emit diagnostics with an incremental `revision`.
- Compilation errors go to **stderr** (`check`'s JSON goes to stdout). In `run`, stdout is the
  program's; in `build --emit=ll`, stdout is the IR's — that is why the JSON of these commands
  stays on stderr.
- Compilation (lexing, parser, resolver and checker): the program **does not execute**. The
  parser recovers (`synchronize`) and the resolver walks the whole AST, so one run can list
  several errors; they come out sorted by `(file, offset, code)` and without duplicates.
- Runtime: stops at the **first** uncaught error. Without `try`, the error is **fatal**
  (exit 70) and whatever was already printed remains ([ADR-0026](../adr/0026-freeze-1.0.md)).
  Inside `try`, the error becomes a catchable `RuntimeError` and `except ... as e` exposes
  `e.message` and `e.site` (`file:line:column` of the throw, `""` when unknown)
  ([ADR-0042](../adr/0042-excecoes.md), [ADR-0120](../adr/0120-localizacao-de-falha-em-excecoes.md));
  `Result` is the explicit alternative for expected errors
  ([ADR-0041](../adr/0041-enums-match.md)). The runtime uses the
  **same header** as compilation (`file:line:col: error[CODE]:`), without a caret — the
  binary can run without the source. When the position is synthetic (internal field), the
  header degrades to `error[CODE]: message`. After the header come the stack trace
  frames ([ADR-0089](../adr/0089-stack-trace-de-runtime.md)).
- In the REPL there is no exit code; the line with the error is discarded and the session
  continues. The file is `<repl>`.
- The displayed path is relative to the CWD; if the file is outside the CWD, only the basename.
  An absolute path never appears (I3). `std.*` modules use the logical name
  (`std/strings.lx`) so as not to depend on the CWD or collide with a user file.
- A **compilation** error in a module points to the module's file, with a snippet and caret for
  that file: the token carries the origin, so the checker and the resolver do not inherit the
  entry file. The **runtime** error also points to the module, because the frame carries the
  function's file (ADR-0089).

### Runtime stack trace

An uncaught runtime error prints, after the header, one frame per Lox activation (innermost
first). The name is the function's display name (`f`, `init`, `<lambda>`, `C` in the
constructor) and the position is the **call site** — where that activation was called:

```text
mod.lx:2:12: error[R1002]: Division by zero not allowed
  at inner (main.lx:7:14)
  at outer (main.lx:9:3)
```

- The innermost frame is the one that was executing the error; its position is the call that
  activated it. The top (script code) is not a frame.
- More than 10 frames: it shows the **5 innermost**, a line
  `  ... N frames omitted` and the **5 outermost** (`TRACE_HEAD`/`TRACE_TAIL` in
  [`limits.py`](../../loxia_core/execution/limits.py)). The trimming is deterministic.
- `--error-format=short` keeps one line per diagnostic and **omits** the frames; `json`
  exposes them in `trace` (`frames[]`, `omitted`, `head`). In the binary the format is always
  the human one.
- The runtime error in a module points to the function's file (not the entry one). A caught
  exception prints nothing; `raise;` re-raises from the point of the `raise`.
- `R1015` has a position: the declaration of the function whose activation overflowed
  ([ADR-0089](../adr/0089-stack-trace-de-runtime.md), which revisits
  [ADR-0077](../adr/0077-limite-de-pilha.md)).

### Labels, notes and help

The model already had `labels`, `notes` and `help`; now they have producers in resolution and
checker errors. `E2001` (duplicate variable) and `E2002` (assignment to `val`) point to the
previous declaration with a second snippet (`-`):

```text
dup.lx:3:7: error[E2001]: Already a variable with this name in this scope.
  |
3 |   val a = 2
  |       ^
  |
2 |   val a = 1
  |       - first declared here
```

`E3003` (undefined name) gains `help` when there is a close visible name — the suggestion is
deterministic (sorted candidates) and ignores mangled module symbols:

```text
suggestion.lx:2:7: error[E3003]: Undefined variable 'nam'.
  |
2 | print(nom)
  |       ^^^
help: did you mean 'name'?
```

**Type** errors gain a provenance note when the value has a name or path
(`Variable`, `Get`, `Index`, `Call`) and the caret points to the destination — the variable
name, the call parenthesis, the `=`. The note shows the source text and the line of the
**start of the expression**, normalized to one line and truncated at 80 characters
([ADR-0099](../adr/0099-notas-de-proveniencia.md)):

```text
provenance.lx:6:5: error[E3001]: Expected Int, found String.
  |
6 | val total: Int = person.name
  |     ^^^^^
note: the value comes from `person.name` (line 6)
```

The note covers annotated `val`/`var`, destructuring, field, `return`, assignment, call
arguments, `len`/`chars`/`math.*`, list index and map key/value. Literals and compound
expressions do not get a note (it would only repeat the caret); without the source loaded,
no note is emitted. Arity, undefined name, property and runtime errors do not use
provenance.

`--error-format=short` remains one line (without labels/notes/help); `json` always includes
all three. A label without the source loaded degrades to `note: file:line:col: message`.

### JSON envelope (v1)

`schema_version` is an integer and changes only on a breaking change. `span.start`/`end` are
half-open; `column` is 1-based in code points and `offset` is 0-based in UTF-8 bytes.
`summary.suppressed` counts the diagnostics cut by `--max-errors`.

```json
{
  "schema_version": 1,
  "command": "check",
  "success": false,
  "exit_code": 65,
  "diagnostics": [
    {
      "code": "E2001",
      "phase": "resolver",
      "severity": "error",
      "message": "Already a variable with this name in this scope.",
      "span": {
        "file": "example.lx",
        "start": { "line": 3, "column": 7, "offset": 24 },
        "end": { "line": 3, "column": 8, "offset": 25 }
      },
      "labels": [],
      "notes": [],
      "help": null,
      "trace": null,
      "fixes": []
    }
  ],
  "summary": { "errors": 1, "warnings": 0, "suppressed": 0 }
}
```

`fixes` is an additive list (it may stay empty): each item has `applicability`
(`safe`/`unsafe`), `message` and `edits[]` with `span` + `new_text`. W1001/W1002 and local
E3004 emit `safe`; E3003, E2001, E2002, E2009, E3002, E3015, E3016, E3018 and E3004 in a
public API emit `unsafe`; `safe` is only applied automatically when there is proof of
behavior preservation
([ADR-0093](../adr/0093-cli-agent-friendly-e-reparo.md), analysis in
[`tech/fixes.md`](../tech/fixes.md)).

`trace` is `null` outside the runtime; in a runtime error it has the frames already trimmed:

```json
"trace": {
  "frames": [
    { "name": "f", "file": "main.lx", "line": 7, "column": 14 }
  ],
  "omitted": 0,
  "head": 0
}
```

## Codes

Codes identify **families**, not messages; they are never reused and the catalog is
closed (emitting a code outside this list does not compile). `E3000` stays reserved for
generic semantic errors, but every checker diagnostic now names a specific family; a new
checker error must pass an explicit code. The per-phase tables below are **generated**
from `loxia_core/diagnostics/codes.py` (`make codes`); do not edit them by hand.

Family choice follows the cause: a value that cannot have members is `E3001`, while a
missing member on a valid receiver is `E3003`; `is` on an unsupported type is `E3007`
(operator), while `as` is `E3013` (cast); `init` return values are `E3017` in the checker
(the resolver's `E2003` covers the same source when it runs first).

| Range | Phase | Meaning |
| --- | --- | --- |
| `E0xxx` | lexical | scanner |
| `E1xxx` | syntax | parser |
| `E2xxx` | resolver | scopes and declarations |
| `E3xxx` | checker | types and semantics |
| `E4xxx` | backend | lowering/emission |
| `R1xxx` | runtime | interpretation and binary |

<!-- codes:start -->
### Lexicon

| Code | Family |
| --- | --- |
| `E0001` | unexpected character |
| `E0002` | unterminated string |
| `E0003` | invalid string escape |
| `E0004` | invalid numeric literal (separator or literal overflow) |
| `E0005` | unterminated block comment |
| `E0006` | unterminated interpolation |
| `E0007` | invalid Unicode escape |

### Syntax

| Code | Family |
| --- | --- |
| `E1001` | unexpected token (the `Expect …` family) |
| `E1002` | invalid assignment target (including `?.` in assignments) |
| `E1003` | limit of 255 parameters/arguments |
| `E1004` | invalid declaration (`val` without initializer, non-constant default, …) |
| `E1005` | invalid type annotation (`List`/`Map` arity, union in `is`, generic) |
| `E1006` | invalid literal (map at the start of a statement) |
| `E1007` | invalid `match` |

### Resolver

| Code | Family |
| --- | --- |
| `E2001` | duplicate variable in scope |
| `E2002` | assignment to `val`/immutable parameter |
| `E2003` | invalid `return` (top level or value in `init`) |
| `E2004` | `this` outside a class |
| `E2005` | `super` outside a class or without a superclass |
| `E2006` | invalid inheritance (class inherits from itself) |
| `E2007` | field conflict (duplicate or with a method) |
| `E2008` | local read in its own initializer |
| `E2009` | assignment to a `val` field |
| `E2010` | `break`/`continue` outside a loop |
| `W1001` | local declared and never read (warning) |
| `W1002` | import declared and never used (warning) |

### Checker

| Code | Family |
| --- | --- |
| `E3000` | reserved generic semantic error (no checker path emits it) |
| `E3001` | type mismatch |
| `E3002` | arity (calls, destructuring or pattern binding) |
| `E3003` | undefined name (variable, property or field) |
| `E3004` | missing annotation |
| `E3005` | unknown type, class or superclass |
| `E3006` | value is not callable |
| `E3007` | invalid operands |
| `E3008` | invalid list (common type, empty element, index) |
| `E3009` | invalid map (key, common type) |
| `E3010` | invalid iteration |
| `E3011` | generic type inference |
| `E3012` | generic feature not supported yet |
| `E3013` | invalid cast |
| `E3014` | builtin/reserved name redefined |
| `E3015` | override/method conflict |
| `E3016` | field not initialized |
| `E3017` | invalid declaration (type param, enum, `init`) |
| `E3018` | missing return on some path |
| `E3019` | `math.*` argument |
| `E3020` | type arguments (generic/enum/class arity) |
| `E3021` | not supported by the interpreter |
| `E3022` | capability requires the Rust toolchain (cargo) at run/build |
| `E3023` | non-exhaustive match |
| `E3024` | unreachable match arm |

### Backend

| Code | Family |
| --- | --- |
| `E4001` | not supported by the backend yet |
| `E4002` | backend internal error/verification/link |
| `E4003` | generic instantiation budget exceeded |

### Runtime

| Code | Family |
| --- | --- |
| `R1000` | generic runtime error |
| `R1001` | value is not callable |
| `R1002` | division or modulo by zero |
| `R1003` | undefined variable |
| `R1004` | undefined property, field or variant |
| `R1005` | runtime arity |
| `R1006` | invalid operands or index type |
| `R1007` | index out of bounds |
| `R1008` | key not found in map |
| `R1009` | assignment to immutable binding |
| `R1010` | uncaught exception |
| `R1011` | invalid cast |
| `R1012` | invalid iteration or mutation during iteration |
| `R1013` | field not initialized |
| `R1014` | invalid value (map key, superclass, …) |
| `R1015` | call depth above the limit |

### CLI

| Code | Family |
| --- | --- |
| `C0001` | execution timeout exceeded |
| `C0002` | lockfile or dependency state (missing, stale, not fetched) |
| `C0003` | project scaffolding (existing target, conflict, git) |
| `C0004` | manifest edit refused (unsupported shape, conflict) |

<!-- codes:end -->

## Lexical

| Message | When |
| --- | --- |
| `Unexpected character: X` | character outside the alphabet (e.g. `@`, `$`) |
| `Unexpected character: ! (use 'not' for negation).` | lone `!`; negation is `not` ([ADR-0068](../adr/0068-not-substitui-bang.md)) |
| `Unterminated string.` | `"`/`"""` without closing until EOF |
| `Unterminated string; multiline strings use '"""'.` | line break inside `"..."` ([ADR-0070](../adr/0070-strings-multilinha-e-raw.md)) |
| `Unterminated interpolation.` | `${...}` without `}` until EOF |
| `Unknown escape sequence '\q'.` | unknown string escape |
| `Invalid Unicode escape.` | invalid `\u{...}` or outside `0..10FFFF` |
| `Unterminated block comment.` | `/*` without `*/` until EOF |

## Syntax

Messages in the `Expect … .` pattern; the most common ones:

| Message | When |
| --- | --- |
| `Expect expression.` | `primary` found no start of expression |
| `Expect expression; '//' is integer division, and comments start with '#'.` | `//` where an expression is expected (it is not a comment) |
| `Type unions in 'is' need parentheses: 'is (A \| B)'.` | `x is Int \| String` without parentheses in the union |
| `Unexpected ':'. Map literals can't start a statement; use 'val m = { ... }' or parentheses.` | `{ "a": 1 }` at the start of a statement |
| `Expect end of interpolation.` | leftover token after the `${...}` expression |
| `Expect 'else' after conditional expression.` | ternary without `else` |
| `Expect property name after '?.'.` | `a?.` without a name |
| `Can't assign through optional chaining.` | `a?.b = 1` |
| `Expect ';' after expression.` | bare expression without `;` on the same line |
| `Expect ';' after variable declaration.` | `var`/`val` without `;` on the same line |
| `Expect ';' after return value.` | `return` followed by another statement on the same line (before `}` or a new line, the `;` is optional) |
| `Expect ';' after 'break'.` | `break` followed by another statement on the same line |
| `Expect ';' after 'continue'.` | `continue` followed by another statement on the same line |
| `Expect ')' after if condition.` | `if`/`elif` without `)` |
| `Expect ')' after condition.` | `while` without `)` |
| `Expect ')' after arguments.` | call without `)` |
| `Expect ')' after expression.` | grouping without `)` |
| `Expect '(' after ...` | `if`, `while`, function/method declaration |
| `C-style 'for' was removed; use \`for x in range(n)\` or a \`while\` loop.` | `for (init; cond; incr)` |
| `Float patterns are not supported; use Int, String, Bool or nil.` | `match x { 1.5 => ... }` |
| `Expect '{' before function body.` / `method body.` | function without `{` |
| `Expect '{' before class body.` | class without `{` |
| `Expect '}' after block.` / `after class body.` | block/class without `}` |
| `Expect variable name.` | `var`/`val` without an identifier |
| `Expect initializer for 'val' declaration.` | `val x;` without `=` |
| `Expect function name.` / `method name.` | `fn`/method without a name |
| `Expect parameter name.` | missing parameter |
| `Expect class name.` | `class` without a name |
| `Expect superclass name.` | `class B(` without a name |
| `Expect ')' after superclass.` | `class B(A` without `)` |
| `Expect ';' after field declaration.` | field without `;` |
| `Field initializer must be a constant.` | `var x = 1 + 2;` in the class body |
| `Default value must be a constant.` | `fn f(x = 1 + 2)` |
| `Required parameter can't follow an optional parameter.` | `fn f(a = 1, b)` |
| `Variadic parameter must be last.` | `fn f(...xs, y)` |
| `Type aliases can't be generic yet.` | `type BoxAlias[T] = ...` |
| `Spread argument must be last.` | `f(...xs, 2)` |
| `Expect '.' after 'super'.` | `super` without a dot |
| `Expect superclass method name.` | `super.` without a name |
| `Expect property name after '.'.` | `obj.` without a name |
| `Expect index expression.` | `xs[]` |
| `Expect ']' after index.` | `xs[0` without `]` |
| `Expect ']' after list elements.` | `[1, 2` without `]` |
| `List expects 1 type argument(s), got 0.` | `val xs: List = [];` |
| `Unknown generic type 'list'. Did you mean 'List'?` | `list[int]` (lowercase name) |
| `Invalid assignment target.` | `1 = 2`, `f() = 3` |
| `Can't have more than 255 arguments.` | giant call |
| `Can't have more than 255 parameters.` | giant function |

## Resolver

| Message | When |
| --- | --- |
| `Already a variable with this name in this scope.` | `val`/`var` repeated in the same scope; parameter + local; repeated parameter |
| `'x' is immutable; declare it with 'var' to allow assignment.` | assignment to a local `val` or immutable parameter (compilation) |
| `Can't read local variable in its own initializer.` | `{ var a = a; }` |
| `Can't return from top-level code.` | `return` outside a function |
| `Can't return a value from an initializer.` | `return value;` inside `init` |
| `Can't use 'break' outside of a loop.` | `break` outside `while`/`for-in` (including inside a lambda in a loop) |
| `Can't use 'continue' outside of a loop.` | `continue` outside `while`/`for-in` |
| `Can't use 'this' outside of a class.` | `this` outside a method |
| `A class can't inherit from itself.` | `class A(A)` |
| `Can't use 'super' outside of a class.` | `super.m` outside a class |
| `Can't use 'super' in a class with no superclass.` | `super.m` in a class without a superclass |
| `Field 'x' already declared.` | field repeated in the same body or in the subclass |
| `Field 'x' conflicts with a method.` | field and method with the same name |
| `Can't assign to immutable field 'x'.` | `this.x = ...` of a `val` field outside `init` |

## Runtime

| Message | When |
| --- | --- |
| `Undefined variable 'x'.` | read/assignment of a nonexistent name |
| `'x' is immutable; declare it with 'var' to allow assignment.` | assignment to a global `val` |
| `Can't redeclare immutable variable 'x'.` | redeclaring a global `val` **or a builtin** (`len`, `str`, `repr`, `range`) |
| `Operand must be a number.` | `-"a"` |
| `Operand must be an integer.` | `~1.0` |
| `Operands must be numbers.` | `1 < "a"` |
| `Operands must be integers.` | `1.0 & 1`, `7 // 2.0`, `1 << 2.0` |
| `Operands must be two numbers or two strings.` | `1 + "a"` |
| `Division by zero not allowed` | `/ 0` or `// 0` |
| `Modulo by zero not allowed` | `% 0` |
| `Negative exponent not allowed for integer power.` | `2 ** -1`; use `2.0 ** -1` |
| `Invalid exponentiation.` | `0.0 ** -1.0`, `(-1.0) ** 0.5` |
| `Exponentiation overflow.` | `1e308 ** 2` |
| `Integer overflow.` | `--debug` with `9223372036854775807 + 1`; exit 70 |
| `Can't cast this Float to Int.` | `math.sqrt(-1.0) as Int` (NaN/Inf/out of range) |
| `Can't cast value to Int.` | `"1" as Int` at runtime |
| `math.floor() requires a finite Float in Int range.` | `math.floor(1e100)`; same for ceil/round/trunc |
| `math.floor() expects numbers.` | `math.floor("1")` at runtime |
| `Shift count must be between 0 and 63.` | `1 << 64`, `1 >> -1` |
| `Can only call functions and classes.` | `1()` |
| `Expected N arguments but got M.` | fixed arity of a function/class |
| `Expected at least N arguments but got M.` | short call with defaults |
| `Expected N to M arguments but got K.` | long call with defaults |
| `Only instances have properties.` | `1.x` |
| `Only instances have fields.` | `1.x = 2` |
| `Undefined property 'x'.` | nonexistent field/method; nonexistent `super.x` |
| `Undefined field 'x'.` | assignment to an undeclared field |
| `Field 'x' must be initialized.` | instance created without initializing the field |
| `Can't assign to immutable field 'x'.` | second assignment to a `val` field |
| `Superclass must be a class.` | `class B(A)` with `A = 1` |
| `Only lists and maps can be indexed.` | `xs[i]`/`xs[i] = v` with a value that is neither a list nor a map |
| `List index must be an integer.` | `xs["0"]` |
| `List index N out of bounds for length M.` | negative index or `>= len(xs)` |
| `Can't pop from an empty list.` | `[].pop()` |
| `Can't modify a list while iterating over it.` | `for x in xs { xs.push(x) }` |
| `Map keys must be strings, integers or booleans.` | `m[1.5]`, `{1.5: 1}`, `m[nil]` |
| `Key not found in map.` | `m["missing"]`, `m.remove("missing")` |
| `Duplicate key in map literal.` | `{"a": 1, "a": 2}` |
| `Can't modify a map while iterating over it.` | `for k in m { m["b"] = 2 }` |
| `len() expects a string, a list or a map.` | `len(3)` |
| `Can only iterate over a range, a list, a map or a string.` | `for x in 42` |
| `iter() must return an instance with next() -> T?.` | `iter()` returns a non-instance |
| `iter() must take no arguments.` / `next() must take no arguments.` | protocol with parameters |

The immutability message appears in **two phases**: compilation for locals/parameters
(65) and runtime for globals (70). The text is the same on purpose.

## Type checker (`--check`)

Strict `--check` requires parameter and return annotations. `--gradual` (and, by default,
the pre-check of `loxia test`) turns the missing-annotation code (`E3004`) into a
**warning** and uses `Any` for that binding: the program is still checked for everything
else and can run; real type errors keep exit 65. In gradual mode `Any` is consistent with
every type (an unannotated value can feed a typed parameter, and a generic instantiated
without evidence gets `Any`), because there is no lowering; strict `--check` still requires
`as` for `Any → T`. `loxia test --no-check` skips the pre-check entirely
([ADR-0142](../adr/0142-check-por-fases.md)).

| Message | When |
| --- | --- |
| `Expected X, found Y.` | assignment/argument/return/field with an incompatible type |
| `Unknown type 'X'.` / `Unknown superclass 'X'.` | annotation with a nonexistent name |
| `Parameter 'x' needs a type annotation.` | parameter without a type in strict `--check` (warning under `--gradual`) |
| `Function 'f' needs a return type annotation.` | function without a return in strict `--check` (warning under `--gradual`) |
| `Field 'x' needs a type annotation.` | field without a type and without an initializer |
| `Can't infer type of 'x'; add an annotation.` | `var` without initializer and without a type |
| `Can only call functions and classes.` | call of a non-callable value |
| `Expected N arguments but got M.` (+ variants with default) | wrong arity |
| `Undefined variable 'x'.` / `Undefined property 'x'.` / `Undefined field 'x'.` | nonexistent name |
| `Can't assign to immutable field 'x'.` | `val` field outside `init` |
| `Operands must be numbers.` / `Operand must be a number.` | arithmetic operator with a non-number |
| `Operands must be integers.` / `Operand must be an integer.` | `//`, bits or `~` with non-`Int` |
| `Operands must be two numbers or two strings.` | `+` mixing types |
| `Range bounds must be integers.` | non-`Int` bound of `..` |
| `Can only iterate over a range, a list, a map or a string.` | `for-in` on a non-iterable type |
| `'C' is not iterable: define iter() returning an iterator with next() -> T?.` | class without `iter()` |
| `iter() must return an iterator with next() -> T?.` | `iter()` returns a type without `next()` |
| `next() must return T?` / `next() must return T? with a concrete T.` | invalid `next()` return |
| `List elements must have a common type; found X and Y. ...` | mixed literal without an annotation |
| `Can't infer the element type of an empty list; annotate it as List[T].` | `val xs = []` |
| `List index must be an integer, found X.` | `xs["0"]` in `--check` |
| `Map keys must be String, Int or Bool.` | `Map[Float, Int]`, `{1.5: 1}` |
| `Map keys must have a common type; found X and Y. ...` | `{1: 1, "a": 2}` without an annotation |
| `Map values must have a common type; found X and Y. ...` | `{"a": 1, "b": "x"}` without an annotation |
| `Can't infer the key and value types of an empty map; annotate it as Map[K, V].` | `val m = {}` |
| `Map method requires a single key/value type.` | union of maps with different `K`/`V` |
| `Expected a string, a list or a map, found X.` | `len(3)` in `--check` |
| `Can't infer type argument(s) 'T'.` | generic call without a context/argument that determines `T` |
| `Can't infer type argument 'T' from Any.` | `Any` argument for a `T` parameter |
| `Recursive type inferred for 'T'.` | `T` would be `List[T]` etc. |
| `Generic function 'id' can't be used as a value yet; ...` | `val f = id`, `id` callback without a call |
| `Generic methods aren't supported yet.` | `get[T] (...)` in a class |
| `Type parameter 'T' is already declared.` | `fn f[T, T]` |
| `Type alias 'A' is recursive.` | `type A = B; type B = A` |
| `Type alias 'A' isn't generic.` | `A[Int]` with `type A = Int` |
| `Type aliases must be declared at the top level.` | `fn f() { type A = Int }` |
| `Name 'A' is already declared.` | alias × class/interface/enum/alias |
| `Variadic parameter can't have a default value.` | `fn f(...xs = 1)` |
| `Variadic parameters aren't supported in 'init' yet.` | `init(...xs)` |
| `Spread arguments are only supported for variadic functions.` | `f(...xs)` in a non-variadic function |
| `Spread arguments only fill the variadic parameter; pass the fixed parameters explicitly.` | `f(...xs)` missing fixed parameters |
| `Expected List[T], found List[U].` | spread with the wrong element |
| `Type parameter can't be named 'Int'.` | reserved type name as a parameter |
| `Polymorphic recursion is not supported yet; ...` | `grow[T]` calling `grow([x])` |
| `Type arguments on a call aren't supported; ...` | `id[Int] (1)` (use inference) |
| `Can't redefine builtin 'x'.` | `fn len`, `val str`, `class range`, `val math` in global scope |
| `Can't cast X to Y.` | `"1" as Int` in `--check` |
| `as doesn't support union types yet; narrow first.` | `1 as Int \| String` |
| `as doesn't support this type yet.` | `x as fn(Int) -> Int` |
| `math.abs() expects numbers.` | `math.abs("1")` |
| `Non-exhaustive match; missing X.` | enum `match` without an arm for every variant |
| `Non-exhaustive match; add a '_' arm.` | literal `match` without `_` |
| `Unreachable match arm.` | wildcard after all variants, or repeated variant/literal |
| `Pattern of type X doesn't match Y.` | `match 1 { "x" => ... }` |
| `Literal patterns only match Int, String, Bool or nil; use an enum variant pattern.` | literal in an enum `match` |
| `Enum variant patterns don't match X; use a literal pattern or '_'.` | variant pattern in a literal `match` |

## How to test

- Golden cases in [`tests/cases/errors/`](../../tests/cases/errors) use the markers
  `# expect error:` (65) and `# expect runtime error:` (70). The runner ignores the snippet's
  code lines when matching the message, so that an `# expect` on the same line as the code does
  not turn into a false positive. See [skill `lox-testing`](../../.dsh/skills/lox-testing/SKILL.md).
- `tests/test_diagnostics.py` covers the model and the three renderers without capturing stderr;
  `tests/test_determinism.py` requires identical bytes across seeds.

## What is still missing

Already implemented: `Diagnostic` model, stable codes, spans (line/column/offset),
`human`/`short`/`json`, dedup/ordering/cap, deterministic relative path, the same runtime
header in the interpreter and in the binary
([ADR-0075](../adr/0075-diagnosticos-estruturados.md)), stack trace
([ADR-0089](../adr/0089-stack-trace-de-runtime.md)), provenance `notes`
([ADR-0099](../adr/0099-notas-de-proveniencia.md)), fixes/warnings/JSONL
([ADR-0093](../adr/0093-cli-agent-friendly-e-reparo.md)) and LSP
([ADR-0090](../adr/0090-lsp-escopo-e-hospedagem.md)).

No open diagnostic work item: `E3004` closed with a fix conditioned on the exact
type ([`../tech/fixes.md`](../tech/fixes.md)); what remains of tooling lives in
[`../roadmap.md`](../roadmap.md).
