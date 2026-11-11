# Erros

Catálogo do que o interpretador reporta hoje, com fase e consequência. Mensagens são em
inglês; o texto de CLI e a documentação em português.

## Formato e exit codes

| Fase | Formato | Exit code |
| --- | --- | --- |
| léxico | `[line N] Error: mensagem` | 65 |
| sintaxe | `[line N] Error at 'token': mensagem` (ou `at end`) | 65 |
| resolver | `[line N] Error at 'token': mensagem` | 65 |
| runtime | `mensagem` + `\n[line N]` | 70 |
| arquivo ausente | `Erro: Arquivo 'x' não encontrado.` (stderr) | 66 |

- Erros vão para **stderr**; a saída do programa, para stdout.
- Compilação: o programa **não executa**. O parser se recupera (`synchronize`) e o resolver
  percorre a AST inteira, então uma execução pode listar vários erros.
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
| `Expect ';' after value.` | `print` sem `;` |
| `Expect ';' after expression.` | expressão solta sem `;` |
| `Expect ';' after variable declaration.` | `var` sem `;` |
| `Expect ';' after return value.` | `return` sem `;` |
| `Expect ';' after loop condition.` | `for` sem `;` na condição |
| `Expect ')' after for clauses.` | `for` sem `)` |
| `Expect ')' after if condition.` | `if` sem `)` |
| `Expect ')' after condition.` | `while` sem `)` |
| `Expect ')' after arguments.` | chamada sem `)` |
| `Expect ')' after expression.` | agrupamento sem `)` |
| `Expect '(' after ...` | `for`, `if`, `while`, declaração de função/método |
| `Expect '{' before function body.` / `method body.` | função sem `{` |
| `Expect '{' before class body.` | classe sem `{` |
| `Expect '}' after block.` / `after class body.` | bloco/classe sem `}` |
| `Expect variable name.` | `var` sem identificador |
| `Expect function name.` / `method name.` | `fun`/método sem nome |
| `Expect parameter name.` | parâmetro ausente |
| `Expect class name.` | `class` sem nome |
| `Expect superclass name.` | `class B <` sem nome |
| `Expect '.' after 'super'.` | `super` sem ponto |
| `Expect superclass method name.` | `super.` sem nome |
| `Expect property name after '.'.` | `obj.` sem nome |
| `Invalid assignment target.` | `1 = 2`, `f() = 3` |
| `Can't have more than 255 arguments.` | chamada gigante |
| `Can't have more than 255 parameters.` | função gigante |

## Resolver

| Mensagem | Quando |
| --- | --- |
| `Already a variable with this name in this scope.` | `var a` repetido no mesmo escopo; parâmetro + `var a`; parâmetro repetido |
| `Can't read local variable in its own initializer.` | `{ var a = a; }` |
| `Can't return from top-level code.` | `return` fora de função |
| `Can't return a value from an initializer.` | `return valor;` dentro de `init` |
| `Can't use 'this' outside of a class.` | `this` fora de método |
| `A class can't inherit from itself.` | `class A < A` |
| `Can't use 'super' outside of a class.` | `super.m` fora de classe |
| `Can't use 'super' in a class with no superclass.` | `super.m` em classe sem `<` |

## Runtime

| Mensagem | Quando |
| --- | --- |
| `Undefined variable 'x'.` | leitura/atribuição de nome inexistente |
| `Operand must be a number.` | `-"a"` |
| `Operands must be numbers.` | `1 < "a"` |
| `Operands must be two numbers or two strings.` | `1 + "a"` |
| `Division by zero not allowed` | `/ 0` |
| `Can only call functions and classes.` | `1()` |
| `Expected N arguments but got M.` | aridade de função/classe |
| `Only instances have properties.` | `1.x` |
| `Only instances have fields.` | `1.x = 2` |
| `Undefined property 'x'.` | campo/método inexistente; `super.x` inexistente |
| `Superclass must be a class.` | `class B < A` com `A = 1` |

## Como testar

- Casos golden em [`tests/cases/errors/`](../../tests/cases/errors) usam marcadores
  `// expect error:` (65) e `// expect runtime error:` (70). Ver
  [skill `lox-testing`](../../.dsh/skills/lox-testing/SKILL.md).

## Próximo passo (não implementado)

Códigos estáveis (`E0xxx`…`E4xxx`), spans com coluna, dedup/cascata, `--error-format=json`,
`fixes[]` e renderizador humano compartilhado — desenho em
[`../../IDEIAS.md`](../../IDEIAS.md) I-4 e [`../../TODO.md`](../../TODO.md) §3.1.
