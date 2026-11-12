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
| [`src/lox_list.py`](../../src/lox_list.py) | `List` mutável: elementos, `version`, `push`/`pop`, índice |
| [`src/lox_map.py`](../../src/lox_map.py) | `Map` mutável: entradas, `version`, `get`/`has`/`remove`/`keys`/`values` |
| [`src/error_reporter.py`](../../src/error_reporter.py) | coleta/impressão de diagnósticos |
| [`src/errors.py`](../../src/errors.py) | `ParseError`, `LoxRuntimeError`, `NativeError`, `ReturnSignal` |
| [`src/lox_callable.py`](../../src/lox_callable.py) | Protocol `min_arity`/`max_arity`/`call` |
| [`src/prelude.py`](../../src/prelude.py) | nomes dos builtins globais reservados |
| [`src/lox_function.py`](../../src/lox_function.py) | função de usuário + closure + `bind` |
| [`src/lox_class.py`](../../src/lox_class.py) | classe (métodos, herança, `init`) |
| [`src/lox_instance.py`](../../src/lox_instance.py) | instância (campos + métodos ligados) |
| [`src/natives/clock.py`](../../src/natives/clock.py) | `clock()` |
| [`src/natives/len.py`](../../src/natives/len.py) | `len(xs)` / `len(m)` / `len(s)` |
| [`src/natives/repr.py`](../../src/natives/repr.py) | `repr(x)` |
| [`src/natives/range.py`](../../src/natives/range.py) | `range(a, b, step)` |
| [`src/natives/str.py`](../../src/natives/str.py) | `str(x)` |
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

## Listas

- `LoxList` envolve `list[object]` e um `version` incremental; `push`/`pop`/`set` mudam a
  versão. `get_method(name)` devolve um `LoxCallable` ligado (`ListPushMethod`/
  `ListPopMethod`), e o `Get` do interpretador aceita `LoxInstance` ou `LoxList`.
- `ListLiteral`, `Index` e `IndexSet` são nós de expressão; `Index`/`IndexSet` carregam o
  token `[` para o diagnóstico. `IndexSet` é o alvo de `xs[i] = v` (o parser transforma
  `Index` em `IndexSet` quando vê `=`).
- `for-in` usa `_iterate_list`: confere `version` antes de cada elemento e ao final; mutação
  no meio do laço vira `LoxRuntimeError`.
- `stringify` é recursivo com pilha de identidades (ciclo → `[...]`); igualdade estrutural
  usa um conjunto de pares `(id(a), id(b))`.
- Tipos são apagados: o `LoxList` não conhece `T`; o `Checker` é quem aplica `ListTy`,
  invariância e as assinaturas de `push`/`pop`/`len`.

## Mapas

- `LoxMap` envolve um `dict[_MapKey, object]` (ordem de inserção) e um `version`
  incremental. `_MapKey` é `(tag, valor)` para separar `Bool` de `Int` e restringir chaves a
  `String`/`Int`/`Bool`; qualquer outra chave vira `LoxRuntimeError`.
- `MapLiteral(entries, brace)` guarda pares `(chave, valor)` como expressões; o parser só
  cria esse nó em posição de expressão (no início do statement, `{` é bloco). O
  interpretador avalia chave→valor, da esquerda para a direita, e confere `has` antes de
  inserir, para recusar chave duplicada no literal.
- `Index`/`IndexSet` já eram genéricos: o interpretador despacha para `LoxList` ou
  `LoxMap`. `m.get(k)`/`m.has(k)`/`m.remove(k)`/`m.keys()`/`m.values()` vêm de
  `get_method` (métodos nativos ligados), e `Get` aceita `LoxInstance`, `LoxList` e
  `LoxMap`.
- `for-in` usa `_iterate_map`: snapshot das chaves + conferência de `version` antes de cada
  chave e ao final; mutação no laço vira `LoxRuntimeError`.
- `stringify` de mapa é recursivo com a mesma pilha de identidades de `List` (ciclo →
  `{...}`); igualdade estrutural é independente de ordem e usa `b.find(key)` com o mesmo
  conjunto de pares `(id(a), id(b))`.
- Tipos são apagados no runtime: o `LoxMap` não conhece `K`/`V`; o `Checker` aplica
  `MapTy`, invariância, a restrição de chaves e as assinaturas dos métodos.

## Assinaturas e ordem

- `Checker.check` pré-declara as classes e calcula as assinaturas das **funções de topo**
  antes de checar os corpos. O corpo de uma função pode chamar outra declarada depois,
  inclusive recursão mútua, porque a assinatura já está na tabela
  `_predeclared_by_name`.
- A tabela só é consultada quando `_function_depth > 0` (dentro de um corpo). Statements de
  topo continuam na ordem: chamar uma função antes da declaração dela ainda é erro.
- A assinatura é calculada uma vez e guardada por nó de AST (`_signatures`); o
  `visit_function_stmt` reutiliza o mesmo `FnTy` em vez de recalcular.
- Métodos e campos de classes não são antecipados; seguem a ordem de visita da classe.
  Ver [ADR-0020](../adr/0020-assinaturas-explicitas.md).
- Anotações de função (`fn(Int) -> Int`) viram `FnTy` no parser e são resolvidas em
  `_resolve_type`. `_assignable_fn` aplica contravariância nos parâmetros e covariância no
  retorno; um `ClassObjectTy` também é atribuível à assinatura do seu `init`, então uma
  classe pode ser passada como fábrica. Ver [ADR-0021](../adr/0021-tipos-de-funcao.md).

## Lambdas

- `Lambda(Expr)` guarda `keyword`, `params`, `body` e `return_type`. O parser transforma
  `=> expr` em `body = [Return(arrow, expr)]`; bloco usa o corpo normal. O runtime não
  precisa saber a diferença.
- `LoxFunction` aceita `Function | Lambda`; a lambda é uma closure sobre o ambiente onde
  foi avaliada (`visit_lambda_expr`), e `__str__` devolve `<lambda>`.
- O resolver reutiliza `_resolve_function` para lambda: muda `_current_function` para
  `FUNCTION`, mas **não** muda `_current_class`; `this`/`super` continuam sendo resolvidos
  no escopo do método que envolve a lambda.
- O checker usa `_lambda_type`. O tipo esperado (`FnTy`) preenche parâmetros sem anotação;
  o retorno é coletado por `_check_function_body(..., collect_returns=True)` e inferido; o
  flag `preserve_class` mantém `this`/`super` visíveis. Parâmetro sem contexto é erro;
  mistura de retornos não-nil exige anotação.
- `AstPrinter.visit_lambda_expr` imprime `(lambda (params) [-> Tipo] corpo)`.
  Ver [ADR-0022](../adr/0022-lambdas.md).

## Narrowing

- O checker mantém `_scopes` (declarações) e `_narrowings` (refinamentos), uma pilha
  paralela. Cada entrada de `_narrowings` guarda `(índice_do_escopo_da_declaração, Ty)`,
  para um refinamento antigo não vazar para uma variável redefinida em escopo interno.
- `_find_decl` acha a declaração mais próxima; `_lookup` procura refinamento do nível mais
  interno até a declaração (com o índice batendo) e cai para o tipo declarado.
- `_refinements(cond, truth)` reconhece `x == nil`, `x != nil`, `if (x)` por truthiness e
  `!`; `_check_branch` empilha um nível temporário e `_always_returns` decide se o ramo
  oposto persiste após um retorno antecipado.
- `_invalidate` remove o nome de todos os níveis ativos quando há atribuição. É
  conservador: perder refinamento é seguro; manter um refinamento inválido não seria.
- Runtime não participa; `T?` continua apagado.

## Interpolação

- `Scanner._string` reconhece `${` e delega a expressão a `_scan_expression_tokens`, que
  escaneia em um buffer de tokens próprio, conta chaves internas (mapa/bloco) e ignora
  strings/comentários. O token `INTERPOLATED_STRING` guarda `list[str | list[Token]]`.
- `Parser._interpolated_string` cria um sub-`Parser` por buffer e chama
  `parse_expression`; o resultado é `InterpolatedString(parts, token)`, com trechos de texto
  e nós de expressão.
- `Interpreter.visit_interpolated_expr` avalia cada expressão da esquerda para a direita e
  concatena com `stringify`; `Checker` infere cada parte e devolve `String`; `Resolver`
  resolve as subexpressões.
- `\$` e `\${` são escapes de texto; `$` sem `{` é literal. O AST printer mostra
  `(interp "texto" expr ...)`.

## Builtins e sombreamento

- `Interpreter.__init__` define `clock`, `len`, `range`, `repr` e `str` com
  `mutable=False`; `_reject_immutable_redeclaration` recusa redefinição no escopo global.
- O checker tem a mesma lista em `src/prelude.py::BUILTIN_NAMES`: `_define` reporta
  `Can't redefine builtin 'x'.` quando o escopo é o global; `visit_class_stmt` faz a
  checagem própria porque classes são pré-declaradas.
- Escopos locais (parâmetro, bloco, `for`) podem sombrear o nome normalmente; a resolução
  léxica já existente cuida do resto.

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
