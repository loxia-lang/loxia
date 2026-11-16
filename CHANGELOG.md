# Changelog

Todas as mudanças relevantes da linguagem/interpretador. O escopo de cada versão está em
[`ESCOPO.md`](ESCOPO.md); decisões fechadas em [`docs/decisoes.md`](docs/decisoes.md).

## [Não lançado]

### Adicionado

- **LSP-0** ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)): `loxia lsp` em Python,
  JSON-RPC sobre stdio sem dependências, `initialize`/`shutdown`/`exit`, full sync
  `didOpen`/`didChange`/`didClose`, `publishDiagnostics` com code/severity/range/
  relatedInformation/help/trace e `documentSymbol` (classes, métodos, campos, enums,
  variantes, interfaces, funções e variáveis). **LSP-1 básico**: `SymbolIndex` +
  `Resolver.references` para `hover` (assinatura/tipo/doc) e `textDocument/definition`
  de variáveis, funções, classes, campos/métodos e variantes. Completion/format/code
  actions (LSP-2) ficam pendentes.
- **Estilo e formatter mínimo** ([ADR-0092](docs/adr/0092-estilo-e-formatter.md)):
  `docs/guia-estilo.md` normativo e `lox fmt` Python (indentação de bloco, `;` de fim de
  linha, newline final, preservação de strings/comentários), com `fmt --check` (exit 1 se
  mudaria) e `fmt --stdin`. `fn` em método, trailing comma, reflow e dogfood Lox ficam
  pendentes.
- **Doc comments `///` e `lox doc`** ([ADR-0091](docs/adr/0091-doc-comments-e-geracao-de-docs.md)):
  doc Markdown anexada a funções/métodos, classes, interfaces, enums/variantes, campos,
  type alias e `val`/`var`; `lox doc arquivo [--json]` gera a referência sem executar o
  programa. A grammar TextMate ganhou o scope de doc; a spec léxica documenta o vínculo
  (linha em branco quebra). Docs obrigatórias da stdlib/builtins e geração do site ficam
  pendentes.
- **CLI agent-friendly (core)** ([ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md)):
  subcomandos `run`/`check`/`build`/`ast`/`explain`/`capabilities` (flags antigas
  preservadas), `--json`/`--json-lines` (`start`/`diagnostic`/`summary`), `--stdin` +
  `--file-name`, `--timeout` em `run`/`check` (exit `124` + `C0001`), `--watch` restrito a
  `check` e `-Werror`/`W1001` (local não lido) em `check`/`build`, nunca em `run`.
  `capabilities --json` publica versão, comandos, códigos e limites; `explain <code>`
  consulta o catálogo. `fixes[]`/`lox fix`, `W1002`, `fmt`, `doc` e `lsp` ficam pendentes.
- **Diagnósticos com labels e sugestão**: `E2001`/`E2002` apontam a declaração anterior
  (`- first declared here`) e `E3003` ganha `help: did you mean '…'?` com candidatos
  visíveis ordenados. `human` renderiza o segundo trecho, `note:` e `help:`; `short`
  continua uma linha; JSON já expunha os campos.
- **Diagnósticos: fonte do módulo e stack trace de runtime** ([ADR-0089](docs/adr/0089-stack-trace-de-runtime.md)):
  erro de compilação e de runtime em módulo aponta o arquivo do módulo (`Token.file`), e
  todo erro de runtime não capturado imprime frames default-on no formato
  `  at <nome> (<arquivo>:<linha>:<col>)`, com os 5 frames mais internos + 5 mais externos
  e elisão acima de 10. O binário reproduz o mesmo stderr (I1). `R1015` ganhou a posição
  da declaração; `--error-format=json` expõe `trace` e `short` omite os frames.
- **Distribuição**: `pip install loxia` / `uv tool install loxia` entrega o comando `loxia`,
  a stdlib e o `runtime.c` no wheel (hatchling, `force-include`; resolução em
  `loxia_core/bundle.py`). `tests/test_install.py` (`pytest -m install`) prova o layout
  instalado fora do repo; release no PyPI via Trusted Publishing
  ([ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md)).

- **Limite de pilha** ([ADR-0077](docs/adr/0077-limite-de-pilha.md)): 10.000 chamadas
  Lox ativas nos dois motores, erro `R1015`/`Stack overflow.` capturável por
  `try`/`except RuntimeError`, restauração da profundidade em `try`/`finally` e reserva de
  pilha no binário via `setrlimit`. Chamadas nativas e construtores de exceção embutida
  não contam; construtor + `init` contam duas ativações.
- **Heap default de 512 MiB + `--max-heap`** ([ADR-0087](docs/adr/0087-heap-cap-e-self-hosting.md)):
  o hard cap do binário subiu de 128 MiB para 512 MiB e `--emit=exe --max-heap=SIZE`
  embute outro teto no runtime (default `512M`, faixa `32M..8G`). I1 continua até 64 MiB
  de memória viva; o teste de OOM usa um build de 128 MiB e um caso novo prova os 512 MiB.
- **Stdlib T2 completa** ([ADR-0079](docs/adr/0079-stdlib-t2.md)): `std.json`
  (`parse`/`stringify`/`pretty`, ordem de inserção e `Int`/`Float` distintos), `std.fmt`
  (`format`/`pad`/`commas`/`fixed`/`percent`/`bytes`), `std.paths` (POSIX lexical),
  `std.fs` (`readText`/`readLines`/`writeText`/`appendText`/`exists`/`listDir`),
  `std.io` (`write`/`writeErr`/`readLine`/`readAll`/`prompt`), `std.cli`
  (`parse`/`flag`/`option`/`positional`/`usage`), `std.sets` (`Set[T]`), `std.csv`
  (RFC 4180) e `std.convert` (base64/hex sobre UTF-8), com golden, `--check` e corpus
  `t2`. Kernel ganhou `io.readAll`, `fs.exists` e `fs.listDir` (teto 15 → 17, todos
  `ambient`); classes passam a aceitar campos `List`/`Map`/tupla/`Range`/enum, `str(Any)`
  funciona no backend e o runtime C valida chave de `Map` (`R1014`) como o interpretador.
  Exemplo novo: [`exemplos/vendas.lx`](exemplos/vendas.lx).
- **Stdlib T1 completa**: `std.maps` (`Map[String, V]`: `entries`, `fromEntries`,
  `merge`, `pick`, `omit`, `mapValues`, `filterKeys`, `filterValues`, `invert`,
  `hasValue`, `getOr`, `toList`), `std.numeric`, `std.asserts` e `std.results`, com
  golden, `--check` e casos no corpus `t1`; `std.strings` e `std.lists` já estavam.
- **Diagnósticos estruturados** ([ADR-0075](docs/adr/0075-diagnosticos-estruturados.md)):
  modelo único de `Diagnostic` (código de família, fase, severidade e span com
  linha/coluna/offset em bytes), renderizadores `human` (cabeçalho + caret), `short` e
  JSON v1, ordenação/dedup/limite determinísticos e caminho de exibição relativo. Flags
  novas: `--error-format`, `--color` e `--max-errors`. Catálogo em
  [`docs/spec/erros.md`](docs/spec/erros.md). O runtime humano continua no formato do livro
  até a paridade nativa.
- **GC Boehm (M7)** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)): a arena
  de 64 MiB foi substituída por heap coletado (`libgc`), com hard cap de 128 MiB e I1 até
  64 MiB de memória viva; programas que alocam em laço deixam de morrer no teto. O ponto
  exato do `Out of memory.` não é determinístico (coletor conservador), mas canal,
  mensagem e exit code são.
- **Verificação de IR (`mod.verify`)** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)):
  o driver verifica o módulo LLVM antes de emitir `.ll`, `.o` ou executável; IR inválido
  vira `BackendError` (exit 65) com mensagem determinística, nunca binário quebrado.
- **`not` substitui `!`** ([ADR-0068](docs/adr/0068-not-substitui-bang.md)): negação no
  nível unário com a mesma precedência; `!` sozinho agora é diagnóstico dirigido
  (`use 'not' for negation`) e `!=` continua. Quebra deliberada de quem usava `!`.
- **Destructuring aninhado** ([ADR-0069](docs/adr/0069-destructuring-aninhado.md)):
  `val (a, (b, c)) = t`, com anotação recursiva e erros por nível; corrige também a
  captura por closure de nomes destruturados no backend (furo do I4).
- **Strings `"""` e raw** ([ADR-0070](docs/adr/0070-strings-multilinha-e-raw.md)):
  `"""..."""` é a forma canônica de multilinha (aspas livres, sem dedent/newline mágico);
  `r"..."`/`r"""..."""` desligam escapes e interpolação. `"..."` passa a ser de uma linha.

- **Gate e orçamento sintático** ([ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md)):
  toda sintaxe nova passa por quatro perguntas (substituição, decidibilidade local,
  precedência, forma canônica), orçamento de superfície e lista de não-objetivos; o agente
  pergunta ao humano antes de ampliar a gramática. Procedimento na skill `lox-syntax`.
- **Desambiguação sintática** ([ADR-0067](docs/adr/0067-desambiguacao-sintatica.md)):
  `//` onde se espera expressão e mapa no início de statement ganham diagnóstico dirigido;
  operador pode iniciar a linha dentro de `()`, `[]` e `{}` de expressão; `fn` é opcional
  em método; união no lado direito de `is` exige parênteses (`x is (Int | String)`).
- **I4 — `--check` limpo compila** ([ADR-0059](docs/adr/0059-i4-check-limpo-compila.md)):
  o checker é a fonte única dos tipos; um programa aceito no `--check` não pode falhar no
  `--emit` por tipo/coerção, só pela lacuna declarada. Gate novo em `tests/test_backend.py`
  varre o corpus inteiro.
- **Orçamento de memória como contrato** ([ADR-0060](docs/adr/0060-orcamento-de-memoria.md)):
  arena de 64 MiB sem `free` documentada em `docs/spec/garantias.md` e teste que prova a
  falha determinística (`exit 70`, `Out of memory.`) e a assimetria com o interpretador.
- **Gate de documentação** (`tests/test_docs_consistency.py`, `docs/_hooks/`): ADR com
  numeração única/sequencial e no índice, página de spec com `sources:` que casam com
  arquivos reais, flags do CLI cobertas pelo README, bloco de níveis **gerado** do
  manifesto e lista de frases defasadas proibidas. Frescor derivado do git com ledger em
  `docs/log.md` (skill `lox-docs`).

- Backend **generics com lambda contextual**: checker publica o `FnTy` concreto da lambda em argumento genérico; `generics.lox` promovido.
- Backend **`is` com união parentetizada**: `x is (Int | String)` compara tags/classes e fecha `is_union_parens.lox`.
- Stdlib **T1**: `std.lists.sort` estável (comparador de 3 vias), `zip`, `flatten`, `flatMap`, `unique`, `chunk` e `partition` ([ADR-0076](docs/adr/0076-std-lists-sort.md)).
- Stdlib **T1 (base)**: `std.strings` e `std.lists` em Lox sobre as primitivas; casos `t1` no corpus.
- Imports/módulos: arquivo=módulo, pasta=namespace, `_` privado verificado, `from`/`as`, desugar e display preservado.
- Kernel **13.2**: `args`, `io.*`, `os.*`, `time.*` e `main(argc, argv)`; tabela única cobre as 14 primitivas.
- Kernel **13.3/13.4**: cache preguiçoso de code points no `LoxStr`, `substr`/`join`/`charCodeAt`/`fromCodePoint` e tabela única de primitivas ([ADR-0071](docs/adr/0071-primitivas-de-runtime.md)); `bench/cases/string_scan.lox` cai para 9,1 ms no nativo.
- Backend **L7b (parte)**: passes de IR `-O2` antes de emitir objeto e `make bench-native`
  com speedup contra o baseline do interpretador; `returns_twice` no `_setjmp`.
- Backend **L6k — função genérica como valor**: lambda genérica especializada no call site (`val id = fn(x) => x; id(1)`), com cache e unboxed; `generic_lambda_value.lox` promovido.
- Backend **L6j — exceções/unwinding**: frames `setjmp`/`longjmp`, `try`/`except`/`finally`, `raise`, classes sintéticas `Exception`/`LoxRuntimeError` e erros de runtime capturáveis; `exceptions.lox` promovido ([ADR-0062](docs/adr/0062-l6-excecoes-unwinding.md)).
- Backend **L6i — enums/`match`/`Result`**: `LoxEnumValue` com descritor, construtores de variante, `match` por variante, igualdade/print e tag `ENUM`; `enums.lox` e `result.lox` promovidos ([ADR-0061](docs/adr/0061-l6-enums-match.md)).
- Backend **L6h — loop/nil/Any**: captura por iteração, variável que começa `nil` e índice de `Any`-tupla ([ADR-0058](docs/adr/0058-l6-loop-capture-uninit.md)).
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

- **O nome é Loxia e a extensão é `.lx`** ([ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md)):
  "PyLox" era nome de trabalho desde o [ADR-0014](docs/adr/0014-identidade-e-invariantes.md).
  O pacote virou `loxia/`, o comando `loxia` (`python -m loxia`, `--version` →
  `loxia 1.0.0`), `main.py` mantém `from main import Loxia` e o alias `Lox`, e os fontes
  passaram de `.lox` para `.lx` (373 arquivos; `SOURCE_SUFFIX` no loader). O CLI não valida
  extensão, então scripts antigos continuam rodando; só `import` deixou de resolver `.lox`.
- **`RuntimeError` no lugar de `LoxRuntimeError`** ([ADR-0078](docs/adr/0078-nome-loxia-extensao-lx.md)):
  a classe embutida de erro de runtime perdeu a marca da linguagem — `except RuntimeError
  as e` substitui `except LoxRuntimeError as e` no tree-walk e no backend. A classe Python
  interna (`loxia_core/diagnostics/errors.py::LoxRuntimeError`) mantém o nome de herança do livro,
  e `Exception` continua a base.
- **Erros de compilação e de runtime mudaram de formato**
  ([ADR-0075](docs/adr/0075-diagnosticos-estruturados.md)): `[line N] Error at 'x': …`
  virou `arquivo:linha:col: error[CODIGO]: …` (+ trecho com caret na compilação). O
  binário nativo reproduz o mesmo cabeçalho no erro de runtime, com linha, coluna e
  código. Exit codes não mudaram (`65`/`70`/`66`/`2`). Quem parseava a linha antiga deve
  migrar para `--error-format=json` (`schema_version: 1`) ou `short`.
- **Contrato de memória** ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md)):
  GC Boehm, hard cap de 128 MiB e I1 até 64 MiB de memória viva; o ponto exato do
  `Out of memory.` deixa de ser determinístico, mas a mensagem e o exit code continuam.
- **`"..."` não aceita mais quebra de linha**: quem escrevia multilinha com `"` usa
  `"""..."""` (erro dirigido aponta a forma canônica). Ver
  [ADR-0070](docs/adr/0070-strings-multilinha-e-raw.md).
- **Promoção `Int → Float` só na aritmética** ([ADR-0059](docs/adr/0059-i4-check-limpo-compila.md)):
  `val x: Float = 2`, `x = 2`, `f(2)`, defaults e `return 2` em `-> Float` passaram a ser
  erro de tipo (Kotlin-like). Escreva `2.0` ou `2 as Float`. A aritmética não mudou
  (`1 + 2.0`, `4 / 2`, `1 == 1.0`).
- **`--check` e `--emit` deixam de divergir**: o furo `var x: Float = 1.5; x = 2`
  (check limpo, binário recusando) virou erro nos dois caminhos, com a mesma mensagem.


- `docs/spec/garantias.md`: I1 passa a valer para o corpus declarado e cobre stderr.
- `pyproject.toml`: extra `llvm` (`llvmlite>=0.50`); o interpretador continua sem
  dependências.

- **Catálogo de códigos gerado**: `docs/spec/erros.md` agora é gerado a partir de
  `Code`/`CODE_DESCRIPTIONS` (`make codes`, incluso em `make docs-sync`); o teste
  `test_catalogo_de_codigos_esta_atualizado` falha se a tabela defasar.

### Corrigido

- **`return` dentro de `try`**: o frame de `try` é desempilhado em toda saída, o valor
  é avaliado antes do `finally`, o `finally` roda uma vez e funções locais/lambdas
  isolam os cleanups. `except ... as e` materializa `LoxRuntimeError` para que
  `e.message` não desreferencie NULL ([commit `c7666fb`]).
- **Igualdade de mapa**: o contador de profundidade não vaza mais em comparações com
  contagens diferentes; `charCodeAt(s, len(s))` vira erro em vez de ler o NUL.
- **`T?` na inferência genérica**: `T?` com `Int?` unifica `T = Int`, não `T = Int?`;
  `assertNotNil` deixa de gerar opcional aninhado no backend.
- **Chamada em contexto esperado publica tipo**: `return math.sqrt(x)` compila; `math.*`
  desembrulha `T?` estreitado antes da chamada nativa.
- **`Any as T` checa a tag no backend**: um `Any` com tipo errado agora vira `R1011`
  (`Can't cast value to T.`) como no tree-walk, em vez de reinterpretar o payload;
  `Int`/`Float` mantêm a promoção numérica. Regressão em `tests/test_backend.py`.
- **Exceções sintéticas com mensagem**: `Exception("x")`/`LoxRuntimeError("x")`
  constroem a instância com `message` (aridade 1), como no tree-walk.
- **Exceção de usuário não capturada**: o binário imprime `Tipo: mensagem`
  (`Unhandled exception: MyError: falhou`), igual ao `stringify` do interpretador.
- **`is`/`as` sobre `Any` agora são recursivos**: listas, mapas, tuplas e enums checam
  elementos, aridade e identidade (enum id / classe id), em vez de só a tag. Corrige
  `["a"] is List[Int]`, `(1, "a") is (Int, Int)`, `Size.Small is Color` e
  `Any as List[Int]`; o `is` de tupla estática com elementos `Any` também deixou de usar
  a comparação estática `same_as`.
- **`is`/`as` estático e opcional**: `5 is Int`, `5 is A` (false, em vez de panic),
  `T?` de escalar/classe/lista (`nil` → false, presente → checagem normal) e classe local
  passam pelo matcher; `T?` é boxeado como `{0,0}`/`{tag,payload}`.
- **Literais aninhados**: `val x: Any = [[1]]`/`{"a": {"b": 1}}` compilam (a checagem de
  tipo morta do literal foi removida; os elementos já eram boxeados).

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
