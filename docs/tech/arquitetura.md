# Arquitetura

Como o interpretador é montado por dentro. Para o comportamento observável, ver
[`../spec/`](../spec/); regras de contribuição ficam no `AGENTS.md` local (não versionado).

## Pipeline

```
fonte .lox
   │
   ▼
Scanner ───────────────► list[Token]
   │                       │
   │                       ▼
   │                    Parser ──────────► list[Stmt] (AST)
   │                       │
   │                       ▼
   │                    Resolver ────────► Interpreter.locals: {Expr: depth}
   │                       │                (erros de escopo vinculante)
   │                       ▼
   └──────────────────► Interpreter ──────► efeitos (print, variáveis, objetos)
```

Cada fase depende só da anterior. O **resolver** é obrigatório: sem ele, o interpretador
não sabe a distância das variáveis locais.

## Módulos

| Módulo | Responsabilidade |
| --- | --- |
| [`main.py`](../../main.py) | CLI, `Lox.run`, REPL, exit codes |
| [`src/scanner.py`](../../src/scanner.py) | lexer manual (estado: `_start`, `_current`, `_line`) |
| [`src/tokens.py`](../../src/tokens.py) | `Token(type, lexeme, literal, line)` frozen |
| [`src/token_type.py`](../../src/token_type.py) | enum `TokenType` |
| [`src/keywords.py`](../../src/keywords.py) | mapa lexema → token |
| [`src/expr.py`](../../src/expr.py) | nós de expressão + `Visitor` Protocol + `accept` |
| [`src/stmt.py`](../../src/stmt.py) | nós de statement + `Visitor` Protocol + `accept` |
| [`src/parser.py`](../../src/parser.py) | recursive descent + recuperação (`synchronize`) |
| [`src/resolver.py`](../../src/resolver.py) | escopos léxicos, validações estáticas, `depth` |
| [`src/interpreter.py`](../../src/interpreter.py) | execução; `globals`, `environment`, `locals` |
| [`src/environment.py`](../../src/environment.py) | escopos encadeados (`values` + `enclosing`) |
| [`src/values.py`](../../src/values.py) | `stringify` única |
| [`src/error_reporter.py`](../../src/error_reporter.py) | coleta/impressão de diagnósticos |
| [`src/errors.py`](../../src/errors.py) | `ParseError`, `LoxRuntimeError`, `ReturnSignal` |
| [`src/lox_callable.py`](../../src/lox_callable.py) | Protocol `arity`/`call` |
| [`src/lox_function.py`](../../src/lox_function.py) | função de usuário + closure + `bind` |
| [`src/lox_class.py`](../../src/lox_class.py) | classe (métodos, herança, `init`) |
| [`src/lox_instance.py`](../../src/lox_instance.py) | instância (campos + métodos ligados) |
| [`src/natives/clock.py`](../../src/natives/clock.py) | `clock()` |
| [`src/ast_printer.py`](../../src/ast_printer.py) | dump S-expression (debug/testes) |

`src` é um pacote normal (`__init__.py`). Os imports são sempre absolutos
(`from src.foo import Bar`) e o programa roda da raiz do repositório.

## Visitor

`Expr` e `Stmt` são Protocols com um método `accept`. Cada nó é um
`@dataclass(frozen=True, eq=False)` que chama `visitor.visit_<no>_<expr|stmt>`.

Adicionar um nó exige **cinco** pontos:

1. dataclass em `expr.py`/`stmt.py` + método no `Visitor`;
2. `accept` no nó;
3. parsing;
4. `Interpreter` (semântica) e `Resolver` (escopo);
5. `AstPrinter` (debug) + caso golden.

O `mypy` strict cobra os métodos dos Protocols; esquecer um passo quebra o type check.

## Identidade da AST

Nós usam `eq=False`: igualdade e hash são **por identidade**. O resolver usa o próprio nó
como chave em `Interpreter.locals`, como o `HashMap` de identidade do livro. Com igualdade
estrutural, dois `a` na mesma linha (mesmo token) colidiriam. Ver
[ADR-0004](../adr/0004-identidade-dos-nos-de-ast.md).

## Ambientes e resolução

- `Environment` é uma lista ligada (`values: dict[str, object]`, `enclosing`).
- `define` grava no escopo atual; `get`/`assign` sobem a corrente até achar (globais vivem
  no ambiente raiz).
- O resolver mantém uma pilha de escopos `dict[str, bool]` (`False` = declarada, `True` =
  inicializada) e grava em `Interpreter.locals[expr] = distância`.
- Em runtime, variável local usa `environment.get_at(distance, nome)`; global usa
  `globals.get`. Atribuição idem com `assign_at`.
- `distance` é contada a partir do ambiente corrente: 0 = escopo atual.

Consequência: **escopo léxico**. Closure lê a variável do ponto de declaração, não da
chamada.

## Chamadas e objetos

- `LoxCallable` é um `Protocol` `runtime_checkable` com `arity()` e `call(interpreter, args)`.
  `isinstance(x, LoxCallable)` verifica presença dos métodos.
- `LoxFunction` guarda a declaração (`Stmt.Function`) e a `closure`; `call` cria um ambiente
  novo, define os parâmetros e executa o corpo. `bind(instance)` cria um ambiente com
  `this` (usado por métodos e por `super`).
- `LoxClass` guarda `superclass` e `methods`; `find_method` procura na própria classe e
  sobe recursivamente. `call` cria a instância e roda `init`.
- `LoxInstance` tem `fields: dict[str, object]`; `get` procura campo, depois método (e
  devolve o método ligado); `set` grava no campo.
- `return` usa `ReturnSignal`, uma exceção interna capturada por `LoxFunction.call`.
  Não é erro de runtime e não deve vazar para o usuário.

## Diagnósticos

- Um `ErrorReporter` por execução, criado em `Lox.run` e injetado em scanner, parser,
  resolver e interpretador (ver [ADR-0003](../adr/0003-diagnosticos-por-execucao.md)).
- Sintaxe/escopo: `reporter.error(token, mensagem)`; o parser se recupera e o resolver
  continua. Runtime: `raise LoxRuntimeError` e o `interpret` captura.
- Exit codes: 65 (compilação), 70 (runtime), 66 (arquivo).
- Ainda não há spans além da linha, stack trace nem JSON — desenho em
  [`../../IDEIAS.md`](../../IDEIAS.md) I-4.

## REPL

`main.Lox.run_prompt` lê uma linha por vez e chama `run_repl`:

1. `Parser(..., repl=True)` tenta uma expressão pura e, se a linha inteira for expressão,
   embrulha em `Print` (por isso `1 + 1` mostra `2`);
2. senão, faz o parse normal de statements;
3. o resolver roda a cada linha, mas o `Environment` e o `Interpreter.locals` persistem —
   funções/classes definidas antes continuam válidas;
4. o `ErrorReporter` é resetado no início de cada `run`.

O `;` final é opcional quando a entrada termina (`_end_statement`), mas declarações no meio
de um arquivo continuam exigindo `;`.

## Limitações conhecidas

- Sem colunas/spans, sem stack trace, sem códigos de erro.
- Números só `float` (decisão de `Int`/`Float` em [`../../TIPOS.md`](../../TIPOS.md)).
- Recursão limitada pela pilha do Python (sem tail call).
- Sem GC próprio: objetos são coletados pelo Python.
- Sem bytecode/VM: o alvo é LLVM, e o tree-walk é o oráculo (ADR-0002).

## Testes e benchmark

- `tests/` — pytest + golden cases `.lox`; ver a skill
  [`lox-testing`](../../.dsh/skills/lox-testing/SKILL.md).
- `bench/` — harness de performance com baseline; ver AGENTS §6.
