# Changelog

Todas as mudanças relevantes da linguagem/interpretador. O escopo de cada versão está em
[`ESCOPO.md`](ESCOPO.md); decisões fechadas em [`docs/decisoes.md`](docs/decisoes.md).

## [Não lançado]

### Adicionado

- Backend **L6g — defaults como valor**: funções com parâmetros default podem ser passadas como valor; defaults são preenchidos na chamada indireta ([ADR-0057](docs/adr/0057-l6-defaults-as-value.md)).
- Backend **L6f — math e parse**: `math.*`, `Int.parse` e `Float.parse` ([ADR-0056](docs/adr/0056-l6-math-parse.md)).
- Backend **L6e — `Any`**: unbox, `is`/`as`, igualdade dinâmica e `for-in` de tupla; caso `any_casts.lox` promovido ([ADR-0055](docs/adr/0055-l6-any-casts.md)).
- Backend **L6d — tuplas e `chars`**: tuplas boxeadas com destructuring e `chars(s)` sobre code points UTF-8.
- Backend **L6d — tuplas**: runtime boxeado, literal, índice, `len`, igualdade, print e destructuring `val/var (a,b)` ([ADR-0054](docs/adr/0054-l6-tuplas.md)).
- Backend **L6c — mapas**: `Map` com chaves/valores boxeados, `get`/`has`/`remove`/`keys`/`values`, `for-in` de chaves, igualdade independente de ordem, stringify e ciclos ([ADR-0053](docs/adr/0053-l6-mapas.md)).
- Backend **L6b — listas**: `List` com elementos boxeados no runtime, literais,
  índice/atribuição, `push`/`pop`, `len`, `for-in`, igualdade estrutural, `print`/`str`/
  `repr` e ciclos; casos `list_*` promovidos ([ADR-0052](docs/adr/0052-l6-listas.md)).
- Backend **L6a — Range, `for-in` e escalares**: `Range` como valor de runtime,
  `for-in` sobre Range/String, `**`/bits/shifts e `as` numérico; casos `range_value`,
  `for_in`, `bitwise*`, `exponentiation`, `one_line_block` e `optional_semicolons`
  promovidos ([ADR-0051](docs/adr/0051-l6-range-for-in-escalares.md)).
- Backend **T7 — monomorfização de funções e classes genéricas**
  ([ADR-0050](docs/adr/0050-monomorfizacao-t7.md)): o checker publica as instanciações
  (`generic_fn_instances`, `generic_class_sites`) e o lowering gera `id$Int`, `id$String`,
  `Box$Int` etc., sem re-inferência e sem boxing. `generic_functions.lox` e
  `generic_class.lox` promovidos para o nível `t7`; containers e função genérica como valor
  seguem `PENDING`/65.
- Backend **L5c — classes locais com campos/métodos e captura**: construtor local recebe o
  descritor como argumento oculto, com layout/vtable/init próprios; classe local com
  campos, `init`, métodos, `this` e captura de variáveis externas funciona.
- **Spike L6 — `Any` boxeado/união escalar** ([ADR-0049](docs/adr/0049-any-boxeado-spike-l6.md)):
  `{i64 tag, i64 payload}` para `Any` explícito e para uniões escalares/string;
  `??` boxeia o resultado, `print` dinâmico via `lox_print_any`; `any_box.lox` e
  `nil_aware.lox` promovidos ao nível `l6`. Sem unbox/igualdade/casts gerais ainda.
- **Refactor do lowering**: `lower.py` foi dividido em `lower_model`, `lower_base`,
  `lower_functions`, `lower_variables`, `lower_optionals`, `lower_strings`,
  `lower_class_layout`, `lower_class_codegen`, `lower_instances` e `lower_calls`, sem mudança de ABI ou comportamento. A separação
  preserva as representações do ADR-0048 para a futura FFI com C.
- Backend **L5a/L5b — classes e herança** ([ADR-0048](docs/adr/0048-abi-classes-l5.md)):
  métodos `(env, this, params...)`, vtable de closures, descritor de classe, instância
  `{classe, bitmap, slots i64}`, campos `val`/`var` com bitmap de inicialização, bound
  methods, `this`, `init` (defaults no call site), `print`/`str` de classe/instância,
  herança com cópia/override de vtable, `super`/`super.init`, `init` herdado e prefixo de
  campos. `String?`/instância `T?` em campos/parâmetros/retornos usam ponteiro nulo;
  `is`/`as` de classe, classes locais **vazias** e `?.` com receptor opcional também
  funcionam (curto-circuito não avalia argumentos no nil). Classes locais gerais e o
  `nil_aware` completo ficam no L6 (união/`Any`).
- Backend **L2.5 — optionais escalares** ([ADR-0047](docs/adr/0047-optionais-escalares-l2-5.md)):
  `Int?`/`Float?`/`Bool?` como `{i1, T}`, `var x: T?;` nascendo `nil`, `nil` contextual,
  `T?` em parâmetros/retornos/closures, `??`/truthiness/igualdade/`print`/`str`/interpolação
  e **unwrap checado** no uso (sem confiar no narrowing do checker). `var x: Int;` sem
  inicializador continua 65 até o L6.
- Backend **L4 — closures e valores de função** ([ADR-0046](docs/adr/0046-closures-celulas-l4.md)):
  funções locais e lambdas com tipo concreto, captura por **células** só para variáveis
  capturadas (`env` de ponteiros), ABI uniforme `(i8* env, params...)`, closure
  `{fnptr, env, display}`, chamada indireta, reatribuição de função e
  `print`/`str`/`repr`/interpolação de `<fn f>`/`<lambda>`. Ordem de declaração de topo é
  preservada (chamar antes vira panic 70, sem hoisting). Função com defaults como valor
  continua rejeitada com 65 no L4; spans/stack trace ficam para um ADR próprio.
- Exceções ([ADR-0042](docs/adr/0042-excecoes.md)): `Exception`/`LoxRuntimeError`
  embutidos, `class MyError(Exception)`, `raise expr`/`raise;`, `try` com múltiplos
  `except Tipo as e` e `finally`; erros de runtime capturáveis como `LoxRuntimeError`;
  uncaught exit 70. Backend rejeita com 65 até o L6.
- Enums e `match` ([ADR-0041](docs/adr/0041-enums-match.md)): `enum` com variantes e
  payload posicional, genéricos (`Result[T, E]` embutido com `Ok`/`Err`), construtores
  namespaced (`Cor.Verde`, `Shape.Circle(1.0)`), `match` expressão com bindings e `_`,
  exaustividade rígida e arms inalcançáveis; igualdade estrutural e stringify
  `Enum.Variante(...)`. Backend rejeita com 65 (L6).
- Classes genéricas ([ADR-0040](docs/adr/0040-generics-classes-desenho.md)): `class Box[T]`
  com múltiplos parâmetros, `T` em campos/métodos/`init`/`this`, `Box[Int]` como tipo,
  inferência no construtor (`Box(1)` → `Box[Int]`), argumentos invariantes e erasure no
  runtime. Métodos genéricos, herança de `Box[Int]` e `is/as` com argumentos ficam para
  depois; o backend rejeita classes com 65 (L6).
- Decisões de tipos ([ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md)): sem sufixos
  de literal (`D-2` fechado); `Float` fora das chaves de `Map`; `Option[T]` = `T?`;
  `Result` será enum/ADT com T6c; `type` alias transparente (P3); `throw` segue fatal.
- Tuplas ([ADR-0036](docs/adr/0036-tuplas-implementacao.md)): literal `(a, b)`, tipo
  `(A, B)`, índice `t[i]` (bounds de literal no `--check`; dinâmico vira união), `len`,
  igualdade estrutural, formatação `(1, "a")` e destructuring `val`/`var (a, b) = t` com
  anotação opcional. Covariantes por elemento; `for-in`, `is (A, B)` e `as (A, B)` também
  funcionam; o backend rejeita com 65 (L6).
- Strings: `chars(s)` devolve os code points como `List[String]` (acesso a caractere sem
  `s[i]`, que continua erro) e `< <= > >=` ordenam `String` por code point, no
  interpretador e no backend (`lox_str_compare`). Identificadores continuam ASCII e não há
  normalização ([ADR-0035](docs/adr/0035-strings-texto.md)).
- Checker (T4): `val f = fn(x) => x` infere parâmetros/retorno e generaliza o esquema
  ([ADR-0033](docs/adr/0033-inferencia-t3c-t4.md)); `var` não generaliza. O T3c
  (parâmetro de `fn` sem anotação) foi implementado e **revertido** por conflitar com o
  contrato explícito do ADR-0020 ([ADR-0034](docs/adr/0034-t3c-revertido.md)).
- Checker (T5): narrowing de campos e índices literais (`p.nome`, `xs[0]`, `m["k"]`), com
  invalidação ao mutar o caminho ou a raiz e refino pelo falso na saída de `while`
  ([ADR-0032](docs/adr/0032-narrowing-campos-indices.md)). Continua sem CFG/aliasing.
- Backend nativo **L0** ([ADR-0031](docs/adr/0031-backend-nativo.md)): `--emit=ll|obj|exe`
  compila `print` de `Int`/`Bool`/`nil` com `+ - * // %`, comparações, igualdade e unário
  para binário nativo, usando `llvmlite` como extra opcional (`uv sync --extra llvm`).
- Runtime C (`runtime/runtime.c`): `lox_print_int/bool/nil`, `lox_panic` (exit 70 com o
  mesmo stderr do interpretador) e as guardas de `//`/`%` (zero e `INT_MIN / -1`).
- Teste diferencial (`tests/test_backend.py`): compila cada caso, executa o binário e
  compara stdout, stderr e exit code com o interpretador.
- Erro de compilação explícito (exit 65) para o que o backend ainda não representa
  (`Float`, `String`, variáveis, funções, classes) — nunca lowering silencioso.
- Erro de operando detectado pelo checker (`1 + true`, `-true`, `true // 2`) é rebaixado
  a `lox_panic`: o binário sai com 70 e a mesma mensagem do interpretador, inclusive
  depois de já ter impresso stdout (ADR-0031, decisão 9).
- Backend **L1**: `Float` desboxado (`double`), promoção `Int → Float`, `/` sempre `Float`,
  `%` de `Float`, comparações com semântica de `NaN` e `if`/`while`/blocos.
- Impressão de `Float` pela menor representação que faz round-trip, com as convenções do
  `repr` do Python, validada por fuzz contra `repr()` (400 bit patterns + especiais) e
  independente de locale (`lox_init` fixa `LC_NUMERIC=C`).
- Manifesto do corpus diferencial (`tests/corpus_manifest.py`) com os níveis `l0` e `l1`.
- 15 golden cases de `tests/cases` e 3 de `exemplos/` anotados (54 de 78 em `tests/cases`
  passam no `--check` agora; antes eram 39).
- Backend L2 (variáveis): `val`/`var` com `alloca` local e global para o topo, atribuição,
  escopo de bloco e sombreamento; o `for` C-style (desaçucarado pelo parser) já compila.
  O tipo do binding é o tipo do valor em runtime — `val f: Float = 2` guarda `Int`, como
  no interpretador (anotação não converte).
- Backend L2 (funções): declaração de topo, chamada direta, `return`, recursão e defaults
  resolvidos no call site; `Nil` vira `void`. Aridade errada e variável indefinida viram
  `lox_panic` com a mensagem do interpretador (stdout e exit code preservados).
- Backend L2b (açúcar): ternário, `and`/`or` e `??` com blocos + `phi`, curto-circuito
  preservado e dobra de literais (`false and x`, `true or x`); `for-in` fica para o L3/L6
  por depender de `Range`/`List`/`String`.
- Backend L3 (strings): `String` como `{byte_len, cp_len, data}` em globais constantes,
  concatenação (`lox_str_concat`), igualdade (`memcmp`), `len` em code points e `print`;
  arena de 64 MiB com panic determinístico.
- Backend L3 (interpolação): `"${expr}"` com `stringify` de `Int`/`Float`/`Bool`/`nil`/
  `String` (`lox_str_from_*`), `str()` e `repr()` com citação e escapes (`lox_str_quote`).

### Mudado

- `docs/spec/garantias.md`: I1 passa a valer para o corpus declarado e cobre stderr.
- `pyproject.toml`: extra `llvm` (`llvmlite>=0.50`); o interpretador continua sem
  dependências.

## [1.0.0] — 2026-11-12

**1.0.0 é a versão de referência da linguagem no tree-walk.** Não há backend nativo
publicado; o LLVM L0–L2 é pós-1.0. A release é local (sem publicação externa).

### Adicionado

- Interpretador tree-walk completo dos caps. 4–13: scanner, parser, resolver, funções,
  closures, classes, `this`, `super` e herança.
- `val`/`var` com imutabilidade de binding, parâmetros imutáveis e `var` explícito.
- `fn`, `elif`, `;` opcional, ternário, `??`, `?.`, interpolação e escapes.
- `Int`/`Float` separados, promoção só `Int → Float`, `//`, `%`, `**` e bits i64.
- Ranges, `for-in`, `List[T]` e `Map[K, V]`.
- Defaults, campos declarados, lambdas e tipos de função.
- Checker gradual `--check`: anotações, inferência local, `T?`, uniões, `is T` e narrowing.
- Generics T3b: funções `fn id[T]`, inferência na chamada, sem constraints.
- Conversões D-8: `as` explícito, `Int.parse`/`Float.parse` → `T?` e `math.*`
  determinístico.
- `--debug` com checagem de overflow de `Int`; release continua wrapping.

### Mudado

- Freeze da 1.0: erro de runtime fatal (exit 70), sem `try`/`Result`.
- `clock` removido do prelúdio; prelúdio determinístico (`len`, `str`, `repr`, `range`,
  `Int`, `Float`, `math`).
- Strings UTF-8 com `len` em code points; identificadores ASCII.
- `print` continua statement; single-file.
- `Any` permanece na linguagem, mas o backend L0–L2 o rejeita.

### Fora da 1.0

Backend LLVM, tuplas, classes/métodos genéricos, constraints/traits, módulos/stdlib,
contratos/JSON, `Result`/`try`, variádicos, trailing closure, `match`/enums, diagnósticos
com spans/caret e transcendentais de `math`. Ver [`ESCOPO.md`](ESCOPO.md).

### Verificação

- `make check` verde: **678 passed + 8 xfailed**, ruff e mypy strict limpos.
- Suíte oficial adaptada: 112 pass + 8 `xfail` intencionais.
- Benchmarks dentro do limite de regressão do baseline.
- `uv run main.py --version` → `pylox 1.0.0`.
