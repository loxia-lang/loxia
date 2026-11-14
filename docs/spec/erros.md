---
sources:
  - src/diagnostics/**
  - src/execution/interpreter.py
  - src/frontend/scanner.py
  - src/frontend/parser.py
  - src/semantics/resolver.py
  - src/semantics/checker.py
  - lox/cli.py
  - tests/test_diagnostics.py
---

# Erros

Catálogo do que o interpretador reporta hoje, com fase e consequência. Mensagens são em
inglês; o texto de CLI e a documentação em português. A decisão por trás do formato está no
[ADR-0075](../adr/0075-diagnosticos-estruturados.md).

## Formato e exit codes

Todo diagnóstico de compilação tem um **código estável** (`error[E3001]`), posição e, no
formato `human`, um trecho da fonte com caret:

```
exemplo.lox:3:7: error[E2001]: Already a variable with this name in this scope.
  |
3 |   var a = 2;
  |       ^
```

| Fase | Formato `human` | Exit code |
| --- | --- | --- |
| léxico | `arquivo:linha:col: error[E0xxx]: mensagem` + caret | 65 |
| sintaxe | `arquivo:linha:col: error[E1xxx]: mensagem` + caret | 65 |
| resolver | `arquivo:linha:col: error[E2xxx]: mensagem` + caret | 65 |
| checker (`--check`) | `arquivo:linha:col: error[E3xxx]: mensagem` + caret | 65 |
| backend | `arquivo:linha: error[E4xxx]: mensagem` (sem coluna/caret) | 65 |
| runtime | `arquivo:linha:col: error[R1xxx]: mensagem` (sem caret) | 70 |
| arquivo ausente | `Erro: Arquivo 'x' não encontrado.` (stderr) | 66 |

- `human` (padrão) mostra cabeçalho + trecho; `short` mostra só o cabeçalho; `json` mostra
  o envelope v1. Flags: `--error-format=human|short|json`, `--color=auto|always|never`
  (respeita `NO_COLOR`) e `--max-errors N` (default 20; `0` = ilimitado).
- Erros de compilação vão para **stderr** (JSON de `check` vai para stdout). Em `run`, o
  stdout é do programa; em `build --emit=ll`, o stdout é do IR — por isso o JSON desses
  comandos fica em stderr.
- Compilação (léxico, parser, resolver e checker): o programa **não executa**. O parser se
  recupera (`synchronize`) e o resolver percorre a AST inteira, então uma execução pode
  listar vários erros; eles saem ordenados por `(arquivo, offset, código)` e sem duplicatas.
- Runtime: para no **primeiro** erro. Na 1.0 o erro de runtime é **fatal** (exit 70):
  não há `try`/`catch`/`Result`; o que já foi impresso permanece
  ([ADR-0026](../adr/0026-freeze-1.0.md)). O runtime usa o **mesmo cabeçalho** da
  compilação (`arquivo:linha:col: error[CODIGO]:`), sem caret — o binário pode rodar sem a
  fonte. Quando a posição é sintética (campo interno), o cabeçalho degrada para
  `error[CODIGO]: mensagem`.
- No REPL não há exit code; a linha com erro é descartada e a sessão continua. O arquivo é
  `<repl>`.
- O caminho exibido é relativo ao CWD; se o arquivo estiver fora do CWD, só o basename.
  Caminho absoluto nunca aparece (I3).

### Envelope JSON (v1)

`schema_version` é inteiro e muda só em ruptura. `span.start`/`end` são half-open; `column`
é 1-based em code points e `offset` é 0-based em bytes UTF-8. `summary.suppressed` conta os
diagnósticos cortados por `--max-errors`.

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
        "file": "exemplo.lox",
        "start": { "line": 3, "column": 7, "offset": 24 },
        "end": { "line": 3, "column": 8, "offset": 25 }
      },
      "labels": [],
      "notes": [],
      "help": null
    }
  ],
  "summary": { "errors": 1, "warnings": 0, "suppressed": 0 }
}
```

## Códigos

Códigos identificam **famílias**, não mensagens; nunca são reaproveitados e o catálogo é
fechado (emitir um código fora daqui não compila). A cauda longa do checker usa `E3000`
até ser refinada em códigos mais específicos. As tabelas por fase abaixo são **geradas** a
partir de `src/diagnostics/codes.py` (`make codes`); não edite à mão.

| Faixa | Fase | Significado |
| --- | --- | --- |
| `E0xxx` | léxico | scanner |
| `E1xxx` | sintaxe | parser |
| `E2xxx` | resolver | escopos e declarações |
| `E3xxx` | checker | tipos e semântica |
| `E4xxx` | backend | lowering/emissão |
| `R1xxx` | runtime | interpretação e binário |

<!-- codes:start -->
### Léxico

| Código | Família |
| --- | --- |
| `E0001` | caractere inesperado |
| `E0002` | string não terminada |
| `E0003` | escape de string inválido |
| `E0004` | literal numérico inválido (separador ou overflow de literal) |
| `E0005` | comentário de bloco não terminado |
| `E0006` | interpolação não terminada |
| `E0007` | escape Unicode inválido |

### Sintaxe

| Código | Família |
| --- | --- |
| `E1001` | token inesperado (a família `Expect …`) |
| `E1002` | alvo de atribuição inválido (inclui `?.` em atribuição) |
| `E1003` | limite de 255 parâmetros/argumentos |
| `E1004` | declaração inválida (`val` sem inicializador, default não constante, …) |
| `E1005` | anotação de tipo inválida (arity de `List`/`Map`, união em `is`, genérico) |
| `E1006` | literal inválido (mapa no início de um statement) |
| `E1007` | `match` inválido |

### Resolver

| Código | Família |
| --- | --- |
| `E2001` | variável duplicada no escopo |
| `E2002` | atribuição a `val`/parâmetro imutável |
| `E2003` | `return` inválido (topo do programa ou valor em `init`) |
| `E2004` | `this` fora de classe |
| `E2005` | `super` fora de classe ou sem superclasse |
| `E2006` | herança inválida (classe herda de si) |
| `E2007` | conflito de campo (duplicado ou com método) |
| `E2008` | leitura de local no próprio inicializador |
| `E2009` | atribuição a campo `val` |

### Checker

| Código | Família |
| --- | --- |
| `E3000` | erro semântico genérico (fallback do checker) |
| `E3001` | tipo incompatível |
| `E3002` | aridade de chamada |
| `E3003` | nome indefinido (variável, propriedade ou campo) |
| `E3004` | anotação ausente |
| `E3005` | tipo, classe ou superclasse desconhecida |
| `E3006` | valor não chamável |
| `E3007` | operandos inválidos |
| `E3008` | lista inválida (tipo comum, elemento vazio, índice) |
| `E3009` | mapa inválido (chave, tipo comum) |
| `E3010` | iteração inválida |
| `E3011` | inferência de tipo genérico |
| `E3012` | recurso genérico ainda não suportado |
| `E3013` | cast inválido |
| `E3014` | builtin/nome reservado redefinido |
| `E3015` | override/conflito de método |
| `E3016` | campo não inicializado |
| `E3017` | declaração inválida (type param, enum, `init`) |
| `E3018` | retorno ausente em algum caminho |
| `E3019` | argumento de `math.*` |
| `E3020` | argumentos de tipo (arity de genérico/enum/classe) |

### Backend

| Código | Família |
| --- | --- |
| `E4001` | não suportado pelo backend ainda |
| `E4002` | erro interno/verificação/link do backend |

### Runtime

| Código | Família |
| --- | --- |
| `R1000` | erro de runtime genérico |
| `R1001` | valor não chamável |
| `R1002` | divisão ou módulo por zero |
| `R1003` | variável indefinida |
| `R1004` | propriedade, campo ou variante indefinido |
| `R1005` | aridade em runtime |
| `R1006` | operandos ou índice de tipo inválido |
| `R1007` | índice fora dos limites |
| `R1008` | chave ausente no mapa |
| `R1009` | atribuição a binding imutável |
| `R1010` | exceção não capturada |
| `R1011` | cast inválido |
| `R1012` | iteração inválida ou mutação durante a iteração |
| `R1013` | campo não inicializado |
| `R1014` | valor inválido (chave de mapa, superclasse, …) |

<!-- codes:end -->

## Léxico

| Mensagem | Quando |
| --- | --- |
| `Unexpected character: X` | caractere fora do alfabeto (ex.: `@`, `$`) |
| `Unexpected character: ! (use 'not' for negation).` | `!` sozinho; a negação é `not` ([ADR-0068](../adr/0068-not-substitui-bang.md)) |
| `Unterminated string.` | `"`/`"""` sem fechamento até EOF |
| `Unterminated string; multiline strings use '"""'.` | quebra de linha dentro de `"..."` ([ADR-0070](../adr/0070-strings-multilinha-e-raw.md)) |
| `Unterminated interpolation.` | `${...}` sem `}` até EOF |
| `Unknown escape sequence '\q'.` | escape de string desconhecido |
| `Invalid Unicode escape.` | `\u{...}` inválido ou fora de `0..10FFFF` |
| `Unterminated block comment.` | `/*` sem `*/` até EOF |

## Sintaxe

Mensagens no padrão `Expect … .`; as mais comuns:

| Mensagem | Quando |
| --- | --- |
| `Expect expression.` | `primary` não encontrou começo de expressão |
| `Expect expression; '//' is integer division, and comments start with '#'.` | `//` onde se espera expressão (não é comentário) |
| `Type unions in 'is' need parentheses: 'is (A \| B)'.` | `x is Int \| String` sem parênteses na união |
| `Unexpected ':'. Map literals can't start a statement; use 'val m = { ... }' or parentheses.` | `{ "a": 1 }` no início de um statement |
| `Expect end of interpolation.` | sobrou token depois da expressão de `${...}` |
| `Expect 'else' after conditional expression.` | ternário sem `else` |
| `Expect property name after '?.'.` | `a?.` sem nome |
| `Can't assign through optional chaining.` | `a?.b = 1` |
| `Expect ';' after value.` | `print` sem `;` na mesma linha |
| `Expect ';' after expression.` | expressão solta sem `;` na mesma linha |
| `Expect ';' after variable declaration.` | `var`/`val` sem `;` na mesma linha |
| `Expect ';' after return value.` | `return` seguido de outro statement na mesma linha (antes de `}` ou de nova linha, o `;` é opcional) |
| `Expect ';' after loop condition.` | `for` sem `;` na condição |
| `Expect ')' after for clauses.` | `for` sem `)` |
| `Expect ')' after if condition.` | `if`/`elif` sem `)` |
| `Expect ')' after condition.` | `while` sem `)` |
| `Expect ')' after arguments.` | chamada sem `)` |
| `Expect ')' after expression.` | agrupamento sem `)` |
| `Expect '(' after ...` | `for`, `if`, `while`, declaração de função/método |
| `Expect '{' before function body.` / `method body.` | função sem `{` |
| `Expect '{' before class body.` | classe sem `{` |
| `Expect '}' after block.` / `after class body.` | bloco/classe sem `}` |
| `Expect variable name.` | `var`/`val` sem identificador |
| `Expect initializer for 'val' declaration.` | `val x;` sem `=` |
| `Expect function name.` / `method name.` | `fn`/método sem nome |
| `Expect parameter name.` | parâmetro ausente |
| `Expect class name.` | `class` sem nome |
| `Expect superclass name.` | `class B(` sem nome |
| `Expect ')' after superclass.` | `class B(A` sem `)` |
| `Expect ';' after field declaration.` | campo sem `;` |
| `Field initializer must be a constant.` | `var x = 1 + 2;` no corpo da classe |
| `Default value must be a constant.` | `fn f(x = 1 + 2)` |
| `Required parameter can't follow an optional parameter.` | `fn f(a = 1, b)` |
| `Expect '.' after 'super'.` | `super` sem ponto |
| `Expect superclass method name.` | `super.` sem nome |
| `Expect property name after '.'.` | `obj.` sem nome |
| `Expect index expression.` | `xs[]` |
| `Expect ']' after index.` | `xs[0` sem `]` |
| `Expect ']' after list elements.` | `[1, 2` sem `]` |
| `List expects 1 type argument(s), got 0.` | `val xs: List = [];` |
| `Unknown generic type 'list'. Did you mean 'List'?` | `list[int]` (nome minúsculo) |
| `Invalid assignment target.` | `1 = 2`, `f() = 3` |
| `Can't have more than 255 arguments.` | chamada gigante |
| `Can't have more than 255 parameters.` | função gigante |

## Resolver

| Mensagem | Quando |
| --- | --- |
| `Already a variable with this name in this scope.` | `val`/`var` repetido no mesmo escopo; parâmetro + local; parâmetro repetido |
| `'x' is immutable; declare it with 'var' to allow assignment.` | atribuição a `val` local ou parâmetro imutável (compilação) |
| `Can't read local variable in its own initializer.` | `{ var a = a; }` |
| `Can't return from top-level code.` | `return` fora de função |
| `Can't return a value from an initializer.` | `return valor;` dentro de `init` |
| `Can't use 'this' outside of a class.` | `this` fora de método |
| `A class can't inherit from itself.` | `class A(A)` |
| `Can't use 'super' outside of a class.` | `super.m` fora de classe |
| `Can't use 'super' in a class with no superclass.` | `super.m` em classe sem superclasse |
| `Field 'x' already declared.` | campo repetido no mesmo corpo ou na subclasse |
| `Field 'x' conflicts with a method.` | campo e método com o mesmo nome |
| `Can't assign to immutable field 'x'.` | `this.x = ...` de campo `val` fora do `init` |

## Runtime

| Mensagem | Quando |
| --- | --- |
| `Undefined variable 'x'.` | leitura/atribuição de nome inexistente |
| `'x' is immutable; declare it with 'var' to allow assignment.` | atribuição a `val` global |
| `Can't redeclare immutable variable 'x'.` | redeclarar um `val` global **ou um builtin** (`len`, `str`, `repr`, `range`) |
| `Operand must be a number.` | `-"a"` |
| `Operand must be an integer.` | `~1.0` |
| `Operands must be numbers.` | `1 < "a"` |
| `Operands must be integers.` | `1.0 & 1`, `7 // 2.0`, `1 << 2.0` |
| `Operands must be two numbers or two strings.` | `1 + "a"` |
| `Division by zero not allowed` | `/ 0` ou `// 0` |
| `Modulo by zero not allowed` | `% 0` |
| `Negative exponent not allowed for integer power.` | `2 ** -1`; use `2.0 ** -1` |
| `Invalid exponentiation.` | `0.0 ** -1.0`, `(-1.0) ** 0.5` |
| `Exponentiation overflow.` | `1e308 ** 2` |
| `Integer overflow.` | `--debug` com `9223372036854775807 + 1`; exit 70 |
| `Can't cast this Float to Int.` | `math.sqrt(-1.0) as Int` (NaN/Inf/fora do range) |
| `Can't cast value to Int.` | `"1" as Int` em runtime |
| `math.floor() requires a finite Float in Int range.` | `math.floor(1e100)`; idem ceil/round/trunc |
| `math.floor() expects numbers.` | `math.floor("1")` em runtime |
| `Shift count must be between 0 and 63.` | `1 << 64`, `1 >> -1` |
| `Can only call functions and classes.` | `1()` |
| `Expected N arguments but got M.` | aridade fixa de função/classe |
| `Expected at least N arguments but got M.` | chamada curta com defaults |
| `Expected N to M arguments but got K.` | chamada longa com defaults |
| `Only instances have properties.` | `1.x` |
| `Only instances have fields.` | `1.x = 2` |
| `Undefined property 'x'.` | campo/método inexistente; `super.x` inexistente |
| `Undefined field 'x'.` | atribuição a campo não declarado |
| `Field 'x' must be initialized.` | instância criada sem inicializar o campo |
| `Can't assign to immutable field 'x'.` | segunda atribuição a campo `val` |
| `Superclass must be a class.` | `class B(A)` com `A = 1` |
| `Only lists and maps can be indexed.` | `xs[i]`/`xs[i] = v` com valor que não é lista nem mapa |
| `List index must be an integer.` | `xs["0"]` |
| `List index N out of bounds for length M.` | índice negativo ou `>= len(xs)` |
| `Can't pop from an empty list.` | `[].pop()` |
| `Can't modify a list while iterating over it.` | `for x in xs { xs.push(x) }` |
| `Map keys must be strings, integers or booleans.` | `m[1.5]`, `{1.5: 1}`, `m[nil]` |
| `Key not found in map.` | `m["ausente"]`, `m.remove("ausente")` |
| `Duplicate key in map literal.` | `{"a": 1, "a": 2}` |
| `Can't modify a map while iterating over it.` | `for k in m { m["b"] = 2 }` |
| `len() expects a string, a list or a map.` | `len(3)` |
| `Can only iterate over a range, a list, a map or a string.` | `for x in 42` |

A mensagem de imutabilidade aparece em **duas fases**: compilação para locais/parâmetros
(65) e runtime para globais (70). O texto é o mesmo de propósito.

## Type checker (`--check`)

| Mensagem | Quando |
| --- | --- |
| `Expected X, found Y.` | atribuição/argumento/retorno/campo com tipo incompatível |
| `Unknown type 'X'.` / `Unknown superclass 'X'.` | anotação com nome inexistente |
| `Parameter 'x' needs a type annotation.` | parâmetro sem tipo no `--check` |
| `Function 'f' needs a return type annotation.` | função sem retorno no `--check` |
| `Field 'x' needs a type annotation.` | campo sem tipo e sem inicializador |
| `Can't infer type of 'x'; add an annotation.` | `var` sem inicializador e sem tipo |
| `Can only call functions and classes.` | chamada de valor não chamável |
| `Expected N arguments but got M.` (+ variantes com default) | aridade errada |
| `Undefined variable 'x'.` / `Undefined property 'x'.` / `Undefined field 'x'.` | nome inexistente |
| `Can't assign to immutable field 'x'.` | `val` de campo fora do `init` |
| `Operands must be numbers.` / `Operand must be a number.` | operador aritmético com não-número |
| `Operands must be integers.` / `Operand must be an integer.` | `//`, bits ou `~` com não-`Int` |
| `Operands must be two numbers or two strings.` | `+` misturando tipos |
| `Range bounds must be integers.` | bound de `..` não-`Int` |
| `Can only iterate over a range, a list, a map or a string.` | `for-in` em tipo não iterável |
| `List elements must have a common type; found X and Y. ...` | literal misto sem anotação |
| `Can't infer the element type of an empty list; annotate it as List[T].` | `val xs = []` |
| `List index must be an integer, found X.` | `xs["0"]` no `--check` |
| `Map keys must be String, Int or Bool.` | `Map[Float, Int]`, `{1.5: 1}` |
| `Map keys must have a common type; found X and Y. ...` | `{1: 1, "a": 2}` sem anotação |
| `Map values must have a common type; found X and Y. ...` | `{"a": 1, "b": "x"}` sem anotação |
| `Can't infer the key and value types of an empty map; annotate it as Map[K, V].` | `val m = {}` |
| `Map method requires a single key/value type.` | união de mapas com `K`/`V` diferentes |
| `Expected a string, a list or a map, found X.` | `len(3)` no `--check` |
| `Can't infer type argument(s) 'T'.` | chamada genérica sem contexto/argumento que determine `T` |
| `Can't infer type argument 'T' from Any.` | argumento `Any` para um parâmetro `T` |
| `Recursive type inferred for 'T'.` | `T` seria `List[T]` etc. |
| `Generic function 'id' can't be used as a value yet; ...` | `val f = id`, callback `id` sem chamada |
| `Generic methods aren't supported yet.` | `get[T] (...)` em classe |
| `Type parameter 'T' is already declared.` | `fn f[T, T]` |
| `Type parameter can't be named 'Int'.` | nome de tipo reservado como parâmetro |
| `Polymorphic recursion is not supported yet; ...` | `grow[T]` chamando `grow([x])` |
| `Type arguments on a call aren't supported; ...` | `id[Int] (1)` (use inferência) |
| `Can't redefine builtin 'x'.` | `fn len`, `val str`, `class range`, `val math` no escopo global |
| `Can't cast X to Y.` | `"1" as Int` no `--check` |
| `as doesn't support union types yet; narrow first.` | `1 as Int \| String` |
| `as doesn't support this type yet.` | `x as fn(Int) -> Int` |
| `math.abs() expects numbers.` | `math.abs("1")` |

## Como testar

- Casos golden em [`tests/cases/errors/`](../../tests/cases/errors) usam marcadores
  `# expect error:` (65) e `# expect runtime error:` (70). O runner ignora as linhas do
  trecho de código ao casar a mensagem, para um `# expect` na mesma linha do código não
  virar falso positivo. Ver [skill `lox-testing`](../../.dsh/skills/lox-testing/SKILL.md).
- `tests/test_diagnostics.py` cobre o modelo e os três renderizadores sem capturar stderr;
  `tests/test_determinism.py` exige bytes idênticos entre seeds.

## O que ainda falta

Já implementado: modelo `Diagnostic`, códigos estáveis, spans (linha/coluna/offset),
`human`/`short`/`json`, dedup/ordenação/cap, caminho relativo determinístico e o mesmo
cabeçalho de runtime no interpretador e no binário
([ADR-0075](../adr/0075-diagnosticos-estruturados.md)).

Pendências registradas no [`../../TODO.md`](../../TODO.md) §3 e no
[`../../IDEIAS.md`](../../IDEIAS.md) I-4:

- stack trace de runtime com frames;
- `notes` de proveniência (ex.: "o valor vem de `pessoa.nome`");
- `fixes[]` com `applicability` e edições, `lox explain`, `lox capabilities`;
- `--json-lines`, warnings/`-Werror` e LSP.
