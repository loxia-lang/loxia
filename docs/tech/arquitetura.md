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

   (caminho `--emit`)     Checker ─────────► Lowerer ──► llvmlite.ir ──► .o ──► cc
                                                                    └─► `--emit=ll`
```

Cada fase depende só da anterior. O **resolver** é obrigatório: sem ele, o interpretador
não sabe a distância das variáveis locais. O **checker** é opt-in (`--check`) e não roda
no caminho normal; tipos são apagados antes da execução.

No caminho do backend (`--emit`, [ADR-0031](../adr/0031-backend-nativo.md)) o checker é
**obrigatório**: o lowering consome tipos concretos. O que ainda não tem representação
(`Float`, `String`, variáveis, funções, classes, `Any`) falha com erro de compilação
explícito — o backend nunca gera código "mais ou menos".

## Módulos

Pacotes por fase (dependência só para baixo):

| Pacote | Fase |
| --- | --- |
| [`src/frontend/`](../../src/frontend) | lexing → tokens → AST → parser; tipos de anotação (`ty.py`) e `ast_printer` |
| [`src/semantics/`](../../src/semantics) | `resolver` (escopos/`depth`) e `checker` gradual |
| [`src/execution/`](../../src/execution) | valores, ambiente, objetos, nativos e `interpreter` |
| [`src/diagnostics/`](../../src/diagnostics) | `errors` e `error_reporter` |
| [`src/backend/`](../../src/backend) | lowering e emissão LLVM (opt-in via `--emit`) |

| Módulo | Responsabilidade |
| --- | --- |
| [`main.py`](../../main.py) | shim de compatibilidade (`python main.py`) |
| [`lox/cli.py`](../../lox/cli.py) | CLI, `Lox.run`, REPL, `--version`, `--dump-ast`, exit codes |
| [`lox/__main__.py`](../../lox/__main__.py) | entrypoint `python -m lox` |
| [`src/frontend/scanner.py`](../../src/frontend/scanner.py) | lexer manual; comentários `#` e `/* */` aninhados |
| [`src/frontend/tokens.py`](../../src/frontend/tokens.py) | `Token(type, lexeme, literal, line)` frozen |
| [`src/frontend/token_type.py`](../../src/frontend/token_type.py) | enum `TokenType` |
| [`src/frontend/keywords.py`](../../src/frontend/keywords.py) | mapa lexema → token |
| [`src/frontend/expr.py`](../../src/frontend/expr.py) | nós de expressão + `Visitor` Protocol + `accept` |
| [`src/frontend/stmt.py`](../../src/frontend/stmt.py) | nós de statement + `Visitor` Protocol + `accept` |
| [`src/frontend/parser.py`](../../src/frontend/parser.py) | recursive descent + recuperação; `;` opcional no fim da linha; `elif`, `fn` e `[T]` |
| [`src/backend/llvm_ir.py`](../../src/backend/llvm_ir.py) | única fronteira com o `llvmlite` (módulo, target machine, object file) |
| [`src/backend/lower.py`](../../src/backend/lower.py) | coordenação do lowering: programa, statements, expressões, aritmética e controle de fluxo |
| [`src/backend/lower_model.py`](../../src/backend/lower_model.py) | tipos, valores, bindings e layouts de campo/classe (ABI do ADR-0048) |
| [`src/backend/lower_base.py`](../../src/backend/lower_base.py) | contexto compartilhado pelos mixins do lowering |
| [`src/backend/lower_functions.py`](../../src/backend/lower_functions.py) | funções, lambdas, captura e ABI de closure |
| [`src/backend/lower_variables.py`](../../src/backend/lower_variables.py) | slots, células, atribuição e escopo |
| [`src/backend/lower_optionals.py`](../../src/backend/lower_optionals.py) | `T?`, coerções, unwrap e igualdade opcional |
| [`src/backend/lower_strings.py`](../../src/backend/lower_strings.py) | strings, interpolação, `str`/`repr`/`len` e display |
| [`src/backend/lower_class_layout.py`](../../src/backend/lower_class_layout.py) | planejamento de layout, campos e inicializadores constantes |
| [`src/backend/lower_class_codegen.py`](../../src/backend/lower_class_codegen.py) | descritor, vtable, construtor, bound methods, `super`, `is`/`as` |
| [`src/backend/lower_instances.py`](../../src/backend/lower_instances.py) | leitura/escrita de campos, bitmap e `get`/`set` |
| [`src/backend/lower_calls.py`](../../src/backend/lower_calls.py) | chamadas, classes chamáveis, métodos e `?.` com curto-circuito |
| [`src/backend/driver.py`](../../src/backend/driver.py) | `--emit=ll|obj|exe` e link com o `cc` do sistema |
| [`runtime/runtime.c`](../../runtime/runtime.c) | runtime C: `lox_print_*`, `lox_panic`, guardas de `//` e `%` |
| [`src/semantics/resolver.py`](../../src/semantics/resolver.py) | escopos léxicos, validações estáticas, `depth` |
| [`src/execution/interpreter.py`](../../src/execution/interpreter.py) | execução; `globals`, `environment`, `locals` |
| [`src/execution/environment.py`](../../src/execution/environment.py) | escopos encadeados (`values` + `enclosing`) |
| [`src/execution/values.py`](../../src/execution/values.py) | `stringify` única |
| [`src/execution/numeric.py`](../../src/execution/numeric.py) | `Int`/`Float`, promoção, wrapping, `//`, `**` e bits |
| [`src/frontend/ty.py`](../../src/frontend/ty.py) | tipos (`Ty`), `TyVar`, `GenericFnTy`, uniões, `T?`, `FnTy` e helpers |
| [`src/semantics/checker.py`](../../src/semantics/checker.py) | checker estático gradual (`--check`) |
| [`src/execution/type_test.py`](../../src/execution/type_test.py) | teste dinâmico de tipo para `x is T` |
| [`src/execution/lox_range.py`](../../src/execution/lox_range.py) | `Range` lazy (start, end, step) |
| [`src/execution/lox_tuple.py`](../../src/execution/lox_tuple.py) | `LoxTuple` imutável (tuplas) |
| [`src/execution/lox_exception.py`](../../src/execution/lox_exception.py) | `Exception`/`LoxRuntimeError` e valores de exceção |
| [`src/execution/lox_list.py`](../../src/execution/lox_list.py) | `List` mutável: elementos, `version`, `push`/`pop`, índice |
| [`src/execution/lox_map.py`](../../src/execution/lox_map.py) | `Map` mutável: entradas, `version`, `get`/`has`/`remove`/`keys`/`values` |
| [`src/diagnostics/error_reporter.py`](../../src/diagnostics/error_reporter.py) | coleta/impressão de diagnósticos |
| [`src/diagnostics/errors.py`](../../src/diagnostics/errors.py) | `ParseError`, `LoxRuntimeError`, `NativeError`, `ReturnSignal` |
| [`src/execution/lox_callable.py`](../../src/execution/lox_callable.py) | Protocol `min_arity`/`max_arity`/`call` |
| [`src/execution/prelude.py`](../../src/execution/prelude.py) | nomes dos builtins globais reservados |
| [`src/execution/lox_function.py`](../../src/execution/lox_function.py) | função de usuário + closure + `bind` |
| [`src/execution/lox_class.py`](../../src/execution/lox_class.py) | classe (métodos, herança, `init`) |
| [`src/execution/lox_instance.py`](../../src/execution/lox_instance.py) | instância (campos + métodos ligados) |
| [`src/execution/natives/len.py`](../../src/execution/natives/len.py) | `len(xs)` / `len(m)` / `len(s)` |
| [`src/execution/natives/repr.py`](../../src/execution/natives/repr.py) | `repr(x)` |
| [`src/execution/natives/range.py`](../../src/execution/natives/range.py) | `range(a, b, step)` |
| [`src/execution/natives/str.py`](../../src/execution/natives/str.py) | `str(x)` |
| [`src/execution/native_module.py`](../../src/execution/native_module.py) | namespace nativo somente leitura (`Int`, `Float`, `math`) |
| [`src/execution/natives/parse.py`](../../src/execution/natives/parse.py) | `Int.parse`/`Float.parse` (`T?`, sem crash) |
| [`src/execution/natives/math.py`](../../src/execution/natives/math.py) | `math.*` determinístico (abs/min/max/clamp/floor/ceil/round/trunc/sqrt) |
| [`src/execution/natives/modules.py`](../../src/execution/natives/modules.py) | montagem dos namespaces nativos |
| [`src/frontend/ast_printer.py`](../../src/frontend/ast_printer.py) | dump S-expression (debug/testes) |

`src` é um pacote normal (`__init__.py`). Os imports são sempre absolutos e apontam para
o pacote da fase (`from src.frontend.expr import Binary`, `from src.execution.numeric
import wrap_int`). O programa roda da raiz do repositório.

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
- `_body_always_returns` vale para funções, métodos e lambdas: retorno não-nil sem caminho
  de retorno é erro. `visit_return_stmt` recusa `return;` em retorno não-nil.
- `_check_field_initialization` roda um dataflow simples (`_init_flow`/`_init_stmt`) sobre o
  `init`: interseção em `if`/`else`, `return` antecipado e laços conservadores; todo campo
  sem inicializador precisa estar atribuído em todos os caminhos.
- `_check_overrides` roda depois de todas as classes e compara cada método com o da
  superclasse via `_assignable` (contravariante nos parâmetros, covariante no retorno).
  Ver [ADR-0023](../adr/0023-soundness-do-checker.md).

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

## Generics

- `Function.type_params` guarda os tokens de `[T, U]`; o parser aceita o bloco só em
  declarações de função, nunca em lambda. O dump imprime `(fn id[T] ...)`.
- O checker tem `FunctionSignature(type_params, type_param_names, fn)`. `_signature` cria
  `TyVar` frescas (`id` único), empilha `_type_param_scopes` e resolve parâmetros/retorno
  com `_resolve_type`; `T` vira `TyVar` em vez de `ClassTy`. O corpo é checado **uma vez**
  com `_check_function_body(..., type_params=...)`; o escopo de tipos fica ativo para
  anotações e lambdas aninhadas.
- `_lookup` de uma função genérica devolve `GenericFnTy` (parâmetros + assinatura), não
  `FnTy`. Ela só é válida como callee; `val f = id` e passar `id` como callback são erros.
- `visit_call_expr` delega para `_infer_call`. Se o callee é `GenericFnTy`,
  `_instantiate_generic` renomeia as `TyVar` e `_infer_generic_call`:
  - unifica o retorno com o tipo esperado (quando há);
  - checa argumentos em ordem, usando `_check_generic_argument` (contexto para lambda/
    lista/mapa, unificação para o resto);
  - aplica as substituições, exige que todo `T` tenha sido inferido e devolve o tipo
    concreto.
- `_unify` cobre `TyVar`, `List`, `Map`, `Fn`, uniões e casos concretos via `_assignable`;
  `_occurs` recusa `T = List[T]`; `_substitute` aplica o mapa. Sem constraints, `a + b`
  em `T` continua erro (`_numeric` não aceita `TyVar`).
- `_check_polymorphic_recursion` recusa `f[T]` chamando `f([x])` (muda os argumentos de
  tipo); `f(x)` com os mesmos `T` é permitido.
- O runtime não muda: `T` é apagado; o monomorphization é responsabilidade do backend
  (ADR-0027). Nada de `LoxValue` boxeado no tree-walk.

## Narrowing

- O checker mantém `_scopes` (declarações) e `_narrowings` (refinamentos), uma pilha
  paralela. Cada entrada de `_narrowings` guarda `(índice_do_escopo_da_declaração, Ty)`,
  para um refinamento antigo não vazar para uma variável redefinida em escopo interno.
- `_find_decl` acha a declaração mais próxima; `_lookup` procura refinamento do nível mais
  interno até a declaração (com o índice batendo) e cai para o tipo declarado.
- `_refinements(cond, truth)` reconhece `x == nil`, `x != nil`, `if (x)`, `x is T`,
  `!`, e combina `and` (ramo verdadeiro) / `or` (ramo falso); `_check_branch` empilha um
  nível temporário e `_always_returns` decide se o ramo oposto persiste após retorno
  antecipado. `while` aplica o refinamento verdadeiro ao corpo.
- `x is T` usa `_intersect_types`/`_narrow_to` no ramo verdadeiro e `_narrow_away` no falso
  (remove membros da união totalmente cobertos por `T`); `_merge_refinements` combina
  `and`/`or` por interseção.
- `Is` é um nó de expressão (`left`, `test_type`, `operator`); o interpreter chama
  `matches_type`, que mora em `src/execution/type_test.py` e cobre primitivos, classes/subclasses,
  `List[T]`/`Map[K, V]` (recursivo) e uniões. O runtime não ganha um sistema de tipos
  geral; `matches_type` existe só para `is`.
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

- `Interpreter.__init__` define `len`, `range`, `repr`, `str`, `Int`, `Float` e `math`
  com `mutable=False`; `_reject_immutable_redeclaration` recusa redefinição no escopo
  global. `clock` foi removido da 1.0 ([ADR-0026](../adr/0026-freeze-1.0.md)); pode ser
  nome comum.
- `Int`/`Float`/`math` são `NativeModule` (namespace somente leitura), não classes
  instanciáveis. O checker associa cada nome a `NativeModuleTy(name)` e resolve membros
  em `_native_modules`; o interpreter resolve `visit_get_expr` para o membro.
- `as` é um nó `As(left, target_type, operator)` no parser (entre `factor` e `unary`); o
  checker valida targets/`Any` e o interpreter converte/checa em runtime
  ([ADR-0029](../adr/0029-conversoes-math.md)).
- O checker tem a mesma lista em `src/execution/prelude.py::BUILTIN_NAMES`: `_define` reporta
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

## Backend nativo (L0–L4 + L2.5 + L5a/L5b)

O IR é intencionalmente pequeno: `Int` é `i64`, `Float` é `double`, `Bool` é `i1`, `nil`
não tem valor (só afeta o `print`). `+ - *` viram instruções (com `sitofp` na promoção
`Int → Float`); `if`/`while` viram blocos com `br`/`cbranch`. `//`, `%`, `/` e o `%` de
Float chamam o runtime: `INT_MIN / -1` é UB em LLVM (`idiv` trap no x86) e divisão por
zero é erro fatal no interpretador. Esses casos viram `lox_panic`, que reproduz o stderr e
sai com 70.

`Float` impresso usa a menor representação que reconstrói o mesmo bit pattern, com as
convenções do `repr` do Python (`1.0`, `-0.0`, `1e-05`, `1e+16`); `lox_init` fixa
`LC_NUMERIC=C` para não depender de locale (I3). A paridade é policiada por fuzz contra
`repr()` em `tests/test_backend.py`.

Variáveis usam `alloca` (locais) e globais LLVM (topo); o `depth` do resolver decide o
escopo (`depths`), e o tipo do slot é o tipo do **valor** em runtime, não o da anotação —
como no interpretador, `val f: Float = 2` guarda `Int`. Variáveis capturadas por closures
viram **células** na arena (`{ value }`) e são referenciadas por ponteiro; as demais
continuam em `alloca`.

Funções de usuário têm ABI `(i8* env, params...)`; uma closure é `{ fnptr, env, display }`
alocada na arena. Funções de topo têm a assinatura pré-declarada (recursão mútua), mas o
binding global só é inicializado quando o statement executa — usar antes vira
`lox_panic` com `Undefined variable`, como no interpretador. O passe
[`src/backend/captures.py`](../../src/backend/captures.py) decide o que cada função
captura e o que vira célula ([ADR-0046](../adr/0046-closures-celulas-l4.md)); funções
locais, lambdas com tipo concreto e chamadas indiretas usam a mesma closure.

Chamadas diretas ainda preenchem defaults no call site; função com defaults como **valor**
é recusada com exit 65 no L4. `return` e argumentos precisam casar (sem coerção implícita)
e `Nil` vira `void`. Aridade errada vira `lox_panic` com a mensagem montada no compile time
(os números são estáticos), e o corpo roda em blocos próprios com `ret`/`unreachable`.

O spike L6 representa `Any` e uniões escalares como `{i64 tag, i64 payload}`, com
`lox_print_any`; é uma caixa de 16 bytes só no caminho dinâmico (ADR-0049).

O L5 usa uma ABI única de método `(i8* env, i8* this, params...)`, vtable de closures,
descritor de classe `{super, id, name, vtable, n_fields, init, init_min, init_max}` e
instância `{classe, bitmap, slots i64}`; bound methods são thunks. Herança copia a vtable,
prefixa os campos e resolve `super` pela classe onde o método foi declarado
([ADR-0048](../adr/0048-abi-classes-l5.md)). `String?`/instância `T?` usam ponteiro nulo; `is`/`as` de classe e classes locais vazias
funcionam. `?.` com receptor opcional já funciona; classes locais gerais e `nil_aware` (união/`Any`) ficam no L6.

`String` é `{byte_len, cp_len, data}`; literais viram globais constantes (bytes UTF-8 +
header), concatenação aloca na arena de 64 MiB e `len` devolve `cp_len` (code points).
Igualdade é `memcmp`; `print` é um `fwrite`. Interpolação concatena as partes, convertendo
escalares com `lox_str_from_int/double/bool` e `lox_str_nil`; `repr` cita e escapa com
`lox_str_quote`.

`main` gerado devolve `0` no sucesso; sucesso/falha nunca é o valor de retorno de uma
função do usuário. O `--emit=ll` é artefato de inspeção: o build emite object file com o
mesmo LLVM que construiu o módulo e linka com `cc`, sem depender da versão do LLVM do
sistema.

O teste diferencial (`tests/test_backend.py`) compila, executa e compara stdout, stderr e
exit code com o interpretador — o oráculo é sempre o tree-walk.

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
