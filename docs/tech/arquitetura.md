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
   │                    Checker ─────────► erros de tipo (só em `--check`)
   │                       │
   ▼                       ▼
   └──────────────────► Interpreter ──────► efeitos (print, variáveis, objetos)
```

Cada fase depende só da anterior. O **resolver** é obrigatório: sem ele, o interpretador
não sabe a distância das variáveis locais. O **checker** é opt-in (`--check`) e não roda
no caminho normal; tipos são apagados antes da execução.

## Módulos

| Módulo | Responsabilidade |
| --- | --- |
| [`main.py`](../../main.py) | shim de compatibilidade (`python main.py`) |
| [`lox/cli.py`](../../lox/cli.py) | CLI, `Lox.run`, REPL, `--version`, `--dump-ast`, exit codes |
| [`lox/__main__.py`](../../lox/__main__.py) | entrypoint `python -m lox` |
| [`src/scanner.py`](../../src/scanner.py) | lexer manual; comentários `#` e `/* */` aninhados |
| [`src/tokens.py`](../../src/tokens.py) | `Token(type, lexeme, literal, line)` frozen |
| [`src/token_type.py`](../../src/token_type.py) | enum `TokenType` |
| [`src/keywords.py`](../../src/keywords.py) | mapa lexema → token |
| [`src/expr.py`](../../src/expr.py) | nós de expressão + `Visitor` Protocol + `accept` |
| [`src/stmt.py`](../../src/stmt.py) | nós de statement + `Visitor` Protocol + `accept` |
| [`src/parser.py`](../../src/parser.py) | recursive descent + recuperação; `;` opcional no fim da linha; `elif` e `fn` |
| [`src/resolver.py`](../../src/resolver.py) | escopos léxicos, validações estáticas, `depth` |
| [`src/interpreter.py`](../../src/interpreter.py) | execução; `globals`, `environment`, `locals` |
| [`src/environment.py`](../../src/environment.py) | escopos encadeados (`values` + `enclosing`) |
| [`src/values.py`](../../src/values.py) | `stringify` única |
| [`src/numeric.py`](../../src/numeric.py) | `Int`/`Float`, promoção, wrapping, `//`, `**` e bits |
| [`src/ty.py`](../../src/ty.py) | tipos (`Ty`), uniões, `T?`, `FnTy` e helpers |
| [`src/checker.py`](../../src/checker.py) | checker estático gradual (`--check`) |
| [`src/lox_range.py`](../../src/lox_range.py) | `Range` lazy (start, end, step) |
| [`src/error_reporter.py`](../../src/error_reporter.py) | coleta/impressão de diagnósticos |
| [`src/errors.py`](../../src/errors.py) | `ParseError`, `LoxRuntimeError`, `NativeError`, `ReturnSignal` |
| [`src/lox_callable.py`](../../src/lox_callable.py) | Protocol `min_arity`/`max_arity`/`call` |
| [`src/lox_function.py`](../../src/lox_function.py) | função de usuário + closure + `bind` |
| [`src/lox_class.py`](../../src/lox_class.py) | classe (métodos, herança, `init`) |
| [`src/lox_instance.py`](../../src/lox_instance.py) | instância (campos + métodos ligados) |
| [`src/natives/clock.py`](../../src/natives/clock.py) | `clock()` |
| [`src/natives/range.py`](../../src/natives/range.py) | `range(a, b, step)` |
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

- `Environment` é uma lista ligada (`values: dict[str, object]`, `_mutable: dict[str, bool]`,
  `enclosing`).
- `define(nome, valor, mutable)` grava no escopo atual; `get`/`assign` sobem a corrente até
  achar (globais vivem no ambiente raiz). `assign`/`assign_at` recusam binding imutável.
- O resolver mantém uma pilha de escopos `dict[str, _VariableInfo]` (`defined`, `mutable`)
  e grava em `Interpreter.locals[expr] = distância`. É aqui que `val` local/parâmetro vira
  erro de compilação; globais ficam para o `Environment`.
- Em runtime, variável local usa `environment.get_at(distance, nome)`; global usa
  `globals.get`. Atribuição idem com `assign_at`.
- `distance` é contada a partir do ambiente corrente: 0 = escopo atual.

Consequência: **escopo léxico**. Closure lê a variável do ponto de declaração, não da
chamada.

## Chamadas e objetos

- `LoxCallable` é um `Protocol` `runtime_checkable` com `min_arity()`, `max_arity()` e
  `call(interpreter, args)`. A faixa cobre parâmetros com default.
  `isinstance(x, LoxCallable)` verifica presença dos métodos.
- `Stmt.Function.params` é uma lista de `Param(name, mutable, default, type_annotation)`, e
  `Stmt.Var` carrega `mutable` e `type_annotation`. Parâmetros são imutáveis por padrão
  (`var` no parser liga `mutable`).
- `LoxFunction` guarda a declaração (`Stmt.Function`) e a `closure`; `call` cria um ambiente
  novo, define os parâmetros (preenchendo defaults constantes) e executa o corpo.
  `bind(instance)` cria um ambiente com `this` (usado por métodos e por `super`).
- `LoxClass` guarda `superclass`, `methods` e `fields: dict[str, FieldInfo]` (campos
  herdados já mesclados); `find_method`/`find_field` sobem recursivamente. `call` cria a
  instância, roda inicializadores de campo e `init`, e valida os campos inicializados.
- `LoxInstance` tem `fields: dict[str, object]` e `_initialized`; `get` procura campo,
  depois método (e devolve o método ligado); `set` recusa campo não declarado e `val` já
  inicializado.
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

O `;` é opcional no fim da linha/EOF em qualquer execução (`_end_statement`); só é
obrigatório quando há outra instrução na mesma linha.

## Limitações conhecidas

- Sem colunas/spans, sem stack trace, sem códigos de erro.
- `Int` (i64) e `Float` (f64) separados; `/` sempre `Float`, `%` truncado, `Int` com
  wrapping — ver [ADR-0006](../adr/0006-int-float-separados.md).
- Recursão limitada pela pilha do Python (sem tail call).
- Sem GC próprio: objetos são coletados pelo Python.
- Sem bytecode/VM: o alvo é LLVM, e o tree-walk é o oráculo (ADR-0002).
- `;` opcional é decidido no parser, não por inserção no scanner; operador no começo da
  linha não continua a expressão (ADR-0011).

## Testes e benchmark

- `tests/` — pytest + golden cases `.lox`; ver a skill
  [`lox-testing`](../../.dsh/skills/lox-testing/SKILL.md).
- `tests/official/` — suíte oficial do Crafting Interpreters (caps. 10–13), adaptada por
  `tests/test_official_suite.py`; 112 passam, 8 são `xfail` documentados.
- `bench/` — harness de performance com baseline; ver AGENTS §6.
