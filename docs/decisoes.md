# Decisões já tomadas

Registro executivo das decisões **fechadas** que antes ficavam misturadas com as abertas
no `TODO.md` §11. A fonte de verdade continua sendo o ADR (ou o documento indicado); este
arquivo existe para consulta rápida e para o `TODO.md` ficar só com o que ainda precisa de
decisão.

> **Regra:** decisão nova → ADR (quando relevante) + linha aqui. Discussão ainda aberta →
> [`../IDEIAS.md`](../IDEIAS.md)/[`../TODO.md`](../TODO.md) §11; não entra neste arquivo.

## Linguagem e semântica

| Decisão | Resumo | Fonte |
| --- | --- | --- |
| `val`/`var` | `val` imutável e com inicializador; `var` mutável e pode ficar sem valor (`nil`); parâmetros são `val` por padrão e `var x` libera a mutação. | [ADR-0005](adr/0005-val-var-imutabilidade.md) |
| `Int` vs `Float` | Tipos separados: `Int` é i64 e `Float` é f64; promoção só `Int → Float`; `/` sempre `Float`; wrapping de i64. | [ADR-0006](adr/0006-int-float-separados.md), [ADR-0006](adr/0006-int-float-separados.md) |
| Nullability | Non-null por padrão; `T?` é açúcar para `T \| Nil` e aceita `nil` (`D-15`). | [ADR-0010](adr/0010-tipagem-estatica.md) |
| Ranges e `for-in` | `a..b` half-open, só `Int`, lazy e reutilizável; `range(a, b, step)` com passo; `for x in` sobre `Range`/`String`/`List`; variável `val` por iteração. | [ADR-0007](adr/0007-ranges-e-iteracao.md) |
| Listas | Um tipo `List[T]`, homogêneo e **invariante**; mutável in-place (`val` congela o binding); literal `[1, 2]`, `xs[i]`/`xs[i] = v`, `push`/`pop` e `len(xs)`; igualdade estrutural; mutar durante iteração é erro. | [ADR-0015](adr/0015-listas-tipadas.md) |
| Mapas | `Map[K, V]`, homogêneo e invariante; literal `{chave: valor}` (chaves são expressões; `{` no início do statement é bloco); `m[k]` erra se ausente e `m.get(k)` devolve `V?`; chaves `String`/`Int`/`Bool`; `get`/`has`/`remove`/`keys`/`values`; iteração de chaves em ordem de inserção; igualdade estrutural sem ordem. Sem `get(k, default)` — use `??`. | [ADR-0017](adr/0017-mapas-hash.md) |
| Narrowing | `T?` refina em `if`/`elif`/`else`, `x == nil`/`x != nil`, truthiness e early return; `is T`, `while` e `and`/`or` também estreitam; `val` e `var`, com invalidação em atribuição; **campos e índices literais** refinam (`p.nome`, `xs[0]`, `m["k"]`), mutação do caminho/raiz invalida e a saída de `while` refina pelo falso; sem aliasing/CFG. | [ADR-0018](adr/0018-narrowing.md), [ADR-0025](adr/0025-is-e-narrowing.md), [ADR-0032](adr/0032-narrowing-campos-indices.md) |
| Interpolação | `"${expr}"`, qualquer expressão, conversão por `stringify`; `\${` para literal; scanner empacota tokens da expressão. | [ADR-0019](adr/0019-interpolacao.md) |
| Defaults e campos | Defaults posicionais constantes com aridade `[mín, máx]`; campos `val`/`var` declarados no corpo, sem campo dinâmico. | [ADR-0009](adr/0009-defaults-e-campos.md) |
| Herança | `class B(A)` com parênteses (sem `extends`/`:`/`<`); `init` no corpo; `this` implícito; `super.init(...)` explícito. | [ADR-0008](adr/0008-heranca-class-parens.md) |
| Tipagem gradual | Checker opt-in (`--check`), funções anotadas, inferência local, `T?`/uniões, narrowing e truthiness; sem inferência de parâmetro sem anotação. | [ADR-0010](adr/0010-tipagem-estatica.md) |
| Assinaturas explícitas | Parâmetros/retorno obrigatórios; assinaturas de topo pré-declaradas para corpos (recursão mútua), mas o topo segue a ordem dos statements; inferir parâmetro ficou adiado. | [ADR-0020](adr/0020-assinaturas-explicitas.md) |
| Tipos de função | `fn(Int) -> Int` em anotações; parâmetros contravariantes, retorno covariante; classe como construtor (`fn(String) -> Animal`); lambdas em ADR-0022; funções genéricas em ADR-0027. | [ADR-0021](adr/0021-tipos-de-funcao.md) |
| Lambdas | `fn(x) => expr` e `fn(x) { ... }`; tipagem contextual pelo tipo esperado; retorno inferido; mistura não-nil exige anotação; `this`/`super` lexicais; sem defaults/trailing closure. | [ADR-0022](adr/0022-lambdas.md) |
| Soundness do checker | Retorno em todos os caminhos para funções/métodos; `return;` não-nil é erro; todo campo sem inicializador precisa ser atribuído em todos os caminhos do `init`; override compatível (contravariante/covariante), checado depois de todas as classes. | [ADR-0023](adr/0023-soundness-do-checker.md) |
| Mutação monomórfica | Variável tem um tipo só; `var x = nil` sem anotação é erro; use `T?`/`Any`; campo mutável com `nil` idem; `val x = nil` é permitido; sem união/flow-sensitive implícita. | [ADR-0024](adr/0024-mutacao-monomorfica.md) |
| `is T` e narrowing | `x is T` devolve Bool; testa primitivos, classes/subclasses, `List[T]`/`Map[K,V]` e uniões; estreita variáveis e caminhos de campo/índice literal em `if`/`else`, `while`, `and`/`or`; tipos de função recusados. | [ADR-0025](adr/0025-is-e-narrowing.md), [ADR-0032](adr/0032-narrowing-campos-indices.md) |
| Sufixos de literal | Sem `1i64`/`1.0f32`: `1` é `Int` e `1.0` é `Float`; conversão via `as`/parse (`D-2` fechado). | [ADR-0039](adr/0039-decisoes-tipos-pendentes.md) |
| Chave `Float` em `Map` | Não: `1 == 1.0` e hash não canônicos; chaves seguem `String`/`Int`/`Bool`; sem plano de canonicalização. | [ADR-0017](adr/0017-mapas-hash.md), [ADR-0039](adr/0039-decisoes-tipos-pendentes.md) |
| `Option`/`Result` | `Option[T]` é alias de `T?`; `Result[T, E]` é enum/ADT com `Ok`/`Err` ([ADR-0041](adr/0041-enums-match.md)); `throw` segue fatal. | [ADR-0039](adr/0039-decisoes-tipos-pendentes.md), [ADR-0041](adr/0041-enums-match.md) |
| `type` alias | Transparente, não genérico, P3; não cria tipo nominal novo. | [ADR-0039](adr/0039-decisoes-tipos-pendentes.md) |
| `throw`/`raise`/`Never` | `throw` separado não existe; `raise`/`try`/`except`/`finally` implementados no tree-walk ([ADR-0042](adr/0042-excecoes.md)); erros não capturados são fatais; `Never` só interno de fluxo. | [ADR-0026](adr/0026-freeze-1.0.md), [ADR-0042](adr/0042-excecoes.md) |
| Exceções | `try`/`except Tipo as e`/`finally`/`raise`, classes `Exception`/`LoxRuntimeError`, erros de runtime capturáveis como `LoxRuntimeError`; `raise;` no except; backend L6. | [ADR-0042](adr/0042-excecoes.md) |
| Enums e `match` | Enums genéricos com variantes namespaced e payload posicional; `match` expressão exaustivo com `_`; `Result[T,E]` embutido com `Ok`/`Err`; igualdade estrutural. Padrões avançados e backend L6 pendentes. | [ADR-0041](adr/0041-enums-match.md) |
| Classes genéricas (T6a) | MVP: `class C[T]`, `ClassTy(name, args)`, invariante, inferência no construtor; sem métodos/herança genérica, constraints ou `is/as` reificado (pendentes); backend 65 até o L6. | [ADR-0040](adr/0040-generics-classes-desenho.md) |
| Traits | **Nominais**: a classe declara `implements`; checker verifica assinaturas; métodos default fazem parte da v1 futura; sem constraints na v1. Implementação **pós-MVP**, fora do M5 (D-17 fechado). | [ADR-0038](adr/0038-traits-nominais.md) |
| Freeze da 1.0 | Erro de runtime não capturado é fatal (exit 70); `try`/`Result` são pós-freeze ([ADR-0041](adr/0041-enums-match.md), [ADR-0042](adr/0042-excecoes.md)); `clock` sai do prelúdio; strings UTF-8 com `len` em code points (indexação de string fora da 1.0) e identificadores ASCII; `print` continua statement; escopo congelado (single-file, sem módulos/`if`-expr/`match`/traits/`Any` no backend); generics é a exceção do ADR-0027. | [ADR-0026](adr/0026-freeze-1.0.md) |
| Generics T3b | Funções genéricas `fn id[T] (...)`, corpo checado uma vez sem constraints; inferência na chamada (sem `id[Int]`); só funções; monomorfização no backend; recursão polimórfica recusada; função genérica não é valor. | [ADR-0027](adr/0027-generics-t3b.md) |
| Strings (texto) | Acesso a caractere por `chars(s) -> List[String]` (sem `s[i]`); `< <= > >=` por code point e `==`/`!=` por conteúdo; `len` em code points; sem normalização (`"é" != "e\\u{301}"`); identificadores ASCII; parse estrito sem `String.to_int`; builtins de string fora por ora. | [ADR-0035](adr/0035-strings-texto.md) |
| Generalização de lambda | `val f = fn(x) => x` infere parâmetros/retorno e generaliza o esquema (T4); `var` não generaliza; função genérica não é valor (inclusive `print`). Parâmetro de `fn` **continua exigindo anotação**: o T3c (parâmetro implícito) foi implementado e revertido. | [ADR-0033](adr/0033-inferencia-t3c-t4.md), [ADR-0034](adr/0034-t3c-revertido.md) |
| Overflow no debug | `--debug` checa `+ - * ** -`, `INT_MIN // -1` e `% -1`; overflow é erro fatal (exit 70); release continua wrapping; shifts não checam. | [ADR-0028](adr/0028-overflow-debug.md) |
| Conversões e `math` | `as` explícito (`Int`/`Float`/`Any`/classe/lista/mapa); `Float as Int` trunca e falha em NaN/Inf/range; `Int.parse`/`Float.parse` devolvem `T?`; `math.*` determinístico com abs/min/max/clamp/floor/ceil/round/trunc/sqrt; transcendentais fora do I3. | [ADR-0029](adr/0029-conversoes-math.md) |
| Tuplas | `(a, b)`/`(A, B)`, `t[i]` (literal com bounds no `--check`; dinâmico vira união), `val`/`var (a, b) = t` com anotação opcional, 2+ elementos, imutáveis e **covariantes**; igualdade/`len`/formatação; `for-in`/`is`/`as` e backend (L6) pendentes; não hasháveis. | [ADR-0030](adr/0030-tuplas.md), [ADR-0036](adr/0036-tuplas-implementacao.md) |
| Async | **Direção decidida; só as palavras-chave reservadas (sem sintaxe):** `async`/`await` *colored*, stackless, single-thread e determinístico; `Task[T]` embutido e covariante; top-level `await` (sem `async main`); `Task.all` com ordem preservada; sem `.then`/thenables/`race`; falha de tarefa é fatal; sem paralelismo. Entra depois do M7 e só com I/O, antes do M8. | [ADR-0037](adr/0037-async-direcao.md), [IDEIAS I-7](../IDEIAS.md) |
| `fn`/`elif`/`;` | `fn` substitui `fun`; `elif` é açúcar para `else if`; `;` opcional no fim da linha, EOF ou antes de `}`; operador só continua na mesma linha; `return` sozinho devolve `nil`. | [ADR-0011](adr/0011-fn-elif-ponto-e-virgula.md) |
| Comentários, `//`, `**` e bits | `#` e `/* */` aninhado; `//` truncado só `Int`; `**` com precedência matemática e `Int ** Int -> Int`; `& \| ^ ~ << >> >>>` em i64; shift inválido é erro. | [ADR-0012](adr/0012-comentarios-divisao-potencia-bits.md) |
| Ternário, `??`, `?.` e escapes | `a if c else b` (Python-style); `??` só nil; `?.` com optional call e assignment proibido; escapes `\n \t \r \" \\ \0 \u{...}`. Sem `?:`, interpolação, `"""` ou raw ainda. | [ADR-0013](adr/0013-ternario-nil-aware-escapes.md) |
| API da stdlib | Modelo **híbrido**: builtins globais para operações genéricas/protocolos (`len`, `str`, `repr`), métodos para ações específicas (`xs.push/pop`), namespaces nativos para conversão (`Int.parse`/`Float.parse`, `math.*`) e funções livres para composição. Builtins globais são reservados (shadowing só local); sem métodos em primitivos; extensões/UFCS em P3 pós-LLVM. | [ADR-0016](adr/0016-api-stdlib-hibrida.md), [ADR-0029](adr/0029-conversoes-math.md) |

## Backend nativo (LLVM)

| Decisão | Resumo | Fonte |
| --- | --- | --- |
| Ferramenta | `llvmlite` como **extra opcional** (`uv sync --extra llvm`); object file emitido pelo LLVM embutido e link com `cc`; `.ll` é artefato de inspeção, não etapa de build; lib isolada em `src/backend/llvm_ir.py`. | [ADR-0031](adr/0031-backend-nativo.md) |
| Modelo de valor | Desboxado por tipo concreto (`Int`=i64, `Float`=f64, `Bool`=i1); `Any`/`List` cru/`Map` heterogêneo são erro de compilação até o L6; `lox build` sempre roda checker. | [ADR-0031](adr/0031-backend-nativo.md) |
| `T?` | Ponteiro nulo para referência (`String?`, instância); `{i1, T}` para escalar (`Int?`, `Float?`, `Bool?`); narrowing devolve o `T` cru. | [ADR-0031](adr/0031-backend-nativo.md) |
| Erro de runtime | `lox_panic(linha, msg)`: flush do stdout, mensagem idêntica ao interpretador no stderr e exit 70; `main` devolve 0 no sucesso; traps de hardware proibidos. | [ADR-0031](adr/0031-backend-nativo.md) |
| Erro estático | Diagnóstico que o interpretador levantaria em runtime é **rebaixado a panic site** (ordem de avaliação preservada); o que só existe em compile-time (anotação) continua exit 65. | [ADR-0031](adr/0031-backend-nativo.md) |
| `Float` impresso | Menor representação testando `%.{p}e` + `strtod` (p = 1..17) e aplicando as convenções do `repr` do Python; fuzz contra `repr()`; `printf("%g")` proibido (locale) e `lox_init` fixa `LC_NUMERIC=C`. | [ADR-0031](adr/0031-backend-nativo.md) |
| `String` | Bytes UTF-8 com `byte_len`, `cp_len` e ponteiro; `len` O(1); ASCII detectado por `byte_len == cp_len`; semântica de `s[i]` em code points. | [ADR-0031](adr/0031-backend-nativo.md) |
| Memória | Arena (bump) com teto e panic determinístico; `lox_alloc` é o ponto de troca para Boehm; sem RC (ciclos são permitidos). | [ADR-0031](adr/0031-backend-nativo.md) |
| Generics | Monomorfização lazy com `type_of`/substituição publicados pelo checker, mangling por tipo e limite de instâncias (exit 65). | [ADR-0031](adr/0031-backend-nativo.md) |
| HIR | Normalização leve `AST → AST` (desugar), sem HIR completa no L0–L2; promove quando o lowering duplicar o interpretador. | [ADR-0031](adr/0031-backend-nativo.md) |
| Layout L5 | Instância `{ptr classe, campos base→derivada}`; vtable com prefixo e override no slot; `init` fora da vtable e `super.m` direto; bitmap de inicialização no MVP; classes locais suportadas. | [ADR-0043](adr/0043-layout-l5-classes.md) |
| Identidade de classe | `is`/`as`/`except` comparam o **objeto de classe** e a cadeia de superclasses; ids inteiros só para vtable/mangling/tags; classes locais homônimas são distintas; rebinding segue o binding atual. | [ADR-0044](adr/0044-identidade-classe.md) |
| Narrowing × backend | Lowering usa `storage_types` (declarado, sem narrowing); chamada/atribuição a campo/índice invalida refinos de campo/índice; `types` (fluxo) não define representação. | [ADR-0045](adr/0045-narrowing-representacao.md) |
| L6c — mapas | `Map` com entradas boxeadas, ordem de inserção, chaves Bool/Int/String distintas, `get`/`has`/`remove`/`keys`/`values`, igualdade independente de ordem e ciclos. | [ADR-0053](adr/0053-l6-mapas.md) |
| L6b — listas | `List` como ponteiro para `LoxList` com elementos boxeados; literais, índice, `push`/`pop`, `len`, `for-in`, igualdade e stringify; igualdade promove números e ciclos usam identidade. | [ADR-0052](adr/0052-l6-listas.md) |
| L6a — Range e escalares | `Range` como ponteiro de runtime, `for-in` sobre Range/String, `**`, bits, shifts e `as` numérico; containers/tuplas/Any/enums/exceções seguem. | [ADR-0051](adr/0051-l6-range-for-in-escalares.md) |
| T7 — monomorfização | Checker publica instanciações; uma função/layout LLVM por tipo concreto (`id$Int`, `Box$String`), sem re-inferência e sem boxing; identidade de classe genérica usa o nome-fonte; valor genérico/herança genérica/containers ficam 65/L6. | [ADR-0050](adr/0050-monomorfizacao-t7.md) |
| L6 spike — `Any` boxeado | `{i64 tag, i64 payload}` para `Any` explícito e uniões escalares/string; `??` boxeia o resultado, `print` dinâmico; sem unbox/igualdade/casts gerais. | [ADR-0049](adr/0049-any-boxeado-spike-l6.md) |
| L5 — classes | Método `(env, this, params...)`; vtable de closures; instância `{classe, bitmap, slots i64}`; descritor com super/vtable/init; bound method por thunk; `val` só primeira atribuição no `init`; herança por prefixo de campos e cópia de vtable; `super`/`super.init`; `print` de classe/instância. | [ADR-0048](adr/0048-abi-classes-l5.md) |
| L2.5 — `T?` escalar | `Int?`/`Float?`/`Bool?` como `{i1, T}`, `var x: T?;` nasce nil, `nil` contextual, unwrap checado no uso; `T?` em parâmetros/retornos/células. `var x: Int;` sem init segue 65 até o L6. | [ADR-0047](adr/0047-optionais-escalares-l2-5.md) |
| L4 — closures e células | Sem HIR no L4: lowering direto + passe de captura; capturados viram células no heap e entram no `env`; não capturados continuam em `alloca`. | [ADR-0046](adr/0046-closures-celulas-l4.md) |
| L4 — ABI e valores de função | Todo `fn` de usuário leva `(i8* env, params...)`; closure é `{fnptr, env, display}` na arena; funções locais, lambdas com `FnTy` concreto, chamada indireta e `print`/`str`/interpolação `<fn f>`/`<lambda>`. | [ADR-0046](adr/0046-closures-celulas-l4.md) |
| L4 — defaults e aridade | Chamada direta preenche defaults no call site; função com defaults como valor é rejeitada com 65 no L4; chamada indireta exige aridade exata. | [ADR-0046](adr/0046-closures-celulas-l4.md) |
| L4 — ordem de declaração | Assinaturas de topo são pré-declaradas (recursão mútua), mas o binding só existe quando o statement executa; usar antes vira panic 70, sem hoisting. | [ADR-0046](adr/0046-closures-celulas-l4.md) |
| Diagnósticos no L4 | Spans/caret e stack trace ficam **fora** do L4; o contrato segue `lox_panic(linha, msg)`/`[line N]`; decisão própria antes do L5/L6. | [ADR-0046](adr/0046-closures-celulas-l4.md) |
| Corpus do I1 | Corpus inteiro **anotado** (`tests/cases`, `exemplos/`, `tests/official/cases`); CI sempre com o extra `llvm`; promoção monotônica; suíte do livro entra quando anotada. | [ADR-0031](adr/0031-backend-nativo.md), [`spec/garantias.md`](spec/garantias.md) |

## Processo e escopo

| Decisão | Resumo | Fonte |
| --- | --- | --- |
| Pipeline `\|>`/`:>` | **Rejeitado por enquanto** em 2026-11-11; alternativas e gatilhos de reabertura ficam registrados. | histórico no git |
| Identidade e invariantes | A linguagem se define por **I1** equivalência executável, **I2** nada implícito e **I3** determinismo observável; features passam pelo portão de admissão. | [ADR-0014](adr/0014-identidade-e-invariantes.md), [`spec/garantias.md`](spec/garantias.md) |

## O que ainda não está aqui

Nome/extensão da linguagem, `if`/blocos como expressão, `print` como função, `match`,
exceções vs `Result`, **generics de classes/métodos e constraints**, módulos, contratos e unificação mutável continuam **em aberto** no
[`../TODO.md`](../TODO.md) §11. Tuplas foram implementadas no interpretador/checker ([ADR-0036](adr/0036-tuplas-implementacao.md)); no backend ficam para o L6. Async tem direção decidida, mas implementação pendente ([ADR-0037](adr/0037-async-direcao.md)).
