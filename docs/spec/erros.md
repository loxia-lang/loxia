# Erros

Catálogo do que o interpretador reporta hoje, com fase e consequência. Mensagens são em
inglês; o texto de CLI e a documentação em português.

## Formato e exit codes

| Fase | Formato | Exit code |
| --- | --- | --- |
| léxico | `[line N] Error: mensagem` | 65 |
| sintaxe | `[line N] Error at 'token': mensagem` (ou `at end`) | 65 |
| resolver | `[line N] Error at 'token': mensagem` | 65 |
| type checker (`--check`) | `[line N] Error at 'token': mensagem` | 65 |
| runtime | `mensagem` + `\n[line N]` | 70 |
| arquivo ausente | `Erro: Arquivo 'x' não encontrado.` (stderr) | 66 |

- Erros vão para **stderr**; a saída do programa, para stdout.
- Compilação (léxico, parser, resolver e checker): o programa **não executa**. O parser se
  recupera (`synchronize`) e o resolver percorre a AST inteira, então uma execução pode
  listar vários erros.
- Runtime: para no **primeiro** erro.
- No REPL não há exit code; a linha com erro é descartada e a sessão continua.

## Léxico

| Mensagem | Quando |
| --- | --- |
| `Unexpected character: X` | caractere fora do alfabeto (ex.: `@`, `$`, `?`) |
| `Unterminated string.` | `"` sem fechamento até EOF |

## Sintaxe

Mensagens no padrão `Expect … .`; as mais comuns:

| Mensagem | Quando |
| --- | --- |
| `Expect expression.` | `primary` não encontrou começo de expressão |
| `Expect ';' after value.` | `print` sem `;` na mesma linha |
| `Expect ';' after expression.` | expressão solta sem `;` na mesma linha |
| `Expect ';' after variable declaration.` | `var`/`val` sem `;` na mesma linha |
| `Expect ';' after return value.` | `return` sem `;` na mesma linha |
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
| `Can't redeclare immutable variable 'x'.` | redeclarar um `val` global |
| `Operand must be a number.` | `-"a"` |
| `Operands must be numbers.` | `1 < "a"` |
| `Operands must be two numbers or two strings.` | `1 + "a"` |
| `Division by zero not allowed` | `/ 0` |
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
| `Operands must be two numbers or two strings.` | `+` misturando tipos |
| `Range bounds must be integers.` | bound de `..` não-`Int` |
| `Can only iterate over a range, a list or a string.` | `for-in` em tipo não iterável |

## Como testar

- Casos golden em [`tests/cases/errors/`](../../tests/cases/errors) usam marcadores
  `// expect error:` (65) e `// expect runtime error:` (70). Ver
  [skill `lox-testing`](../../.dsh/skills/lox-testing/SKILL.md).

## Próximo passo (não implementado)

Códigos estáveis (`E0xxx`…`E4xxx`), spans com coluna, dedup/cascata, `--error-format=json`,
`fixes[]` e renderizador humano compartilhado — desenho em
[`../../IDEIAS.md`](../../IDEIAS.md) I-4 e [`../../TODO.md`](../../TODO.md) §3.1.
