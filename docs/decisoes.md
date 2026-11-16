---
sources:
  - docs/adr/**
---

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
| Ranges e `for-in` | `a..b` half-open, só `Int`, lazy e reutilizável; `range(a, b, step)` com passo; `for x in` sobre `Range`/`String`/`List`/`Map`/tupla; variável `val` por iteração. | [ADR-0007](adr/0007-ranges-e-iteracao.md) |
| Iterador de usuário | Protocolo estrutural `iter()` + `next() -> T?`: `for x in e` chama `iter()` uma vez e para no primeiro `nil`; aceita classe/interface e iteradores genéricos; sem `implements` obrigatório. | [ADR-0082](adr/0082-iterador-de-usuario.md) |
| Variádicos | Último parâmetro `...xs: T` vira `List[T]` no corpo; chamada aceita extras e spread final `f(a, ...xs)` (só no rest, fixos explícitos); funções/métodos/lambdas, `init` fora; `fmt.format` é variádico. | [ADR-0083](adr/0083-variadicos.md) |
| Narrowing avançado | `var` mutável capturado é invalidado por chamadas de usuário (nativas puras não); `if`/`else`, `while`, `for-in` e `try` fazem merge estruturado; atribuição atualiza o refino; sem CFG/aliasing completo. | [ADR-0086](adr/0086-narrowing-captura-e-merge.md) |
| Type alias | `type Nome = Tipo` transparente e não-genérico; top-level, forward references e ciclos, imports de módulo; expandido no checker/tree-walk/backend; não vale em `implements`/superclasse. | [ADR-0039](adr/0039-decisoes-tipos-pendentes.md), [ADR-0084](adr/0084-type-alias.md) |
| `print` função | `print(valor: Any) -> Nil` builtin, uma newline; statement/palavra-chave removidos, REPL embrulha expressões; ABI `lox_print_*` inalterada. | [ADR-0085](adr/0085-print-como-funcao.md) |
| Listas | Um tipo `List[T]`, homogêneo e **invariante**; mutável in-place (`val` congela o binding); literal `[1, 2]`, `xs[i]`/`xs[i] = v`, `push`/`pop` e `len(xs)`; igualdade estrutural; mutar durante iteração é erro. | [ADR-0015](adr/0015-listas-tipadas.md) |
| Mapas | `Map[K, V]`, homogêneo e invariante; literal `{chave: valor}` (chaves são expressões; `{` no início do statement é bloco); `m[k]` erra se ausente e `m.get(k)` devolve `V?`; chaves `String`/`Int`/`Bool`; `get`/`has`/`remove`/`keys`/`values`; iteração de chaves em ordem de inserção; igualdade estrutural sem ordem. Sem `get(k, default)` — use `??`. | [ADR-0017](adr/0017-mapas-hash.md) |
| Narrowing | `T?` refina em `if`/`elif`/`else`, `x == nil`/`x != nil`, truthiness e early return; `is T`, `while` e `and`/`or` também estreitam; `val` e `var`, com invalidação em atribuição; **campos e índices literais** refinam (`p.nome`, `xs[0]`, `m["k"]`), mutação do caminho/raiz invalida e a saída de `while` refina pelo falso; sem aliasing/CFG. | [ADR-0018](adr/0018-narrowing.md), [ADR-0025](adr/0025-is-e-narrowing.md), [ADR-0032](adr/0032-narrowing-campos-indices.md) |
| Interpolação | `"${expr}"`, qualquer expressão, conversão por `stringify`; `\${` para literal; scanner empacota tokens da expressão. | [ADR-0019](adr/0019-interpolacao.md) |
| Defaults e campos | Defaults posicionais constantes com aridade `[mín, máx]`; campos `val`/`var` declarados no corpo, sem campo dinâmico. | [ADR-0009](adr/0009-defaults-e-campos.md) |
| Negação | `not` **substitui** `!` no nível unário (mesma precedência); `!` sozinho é diagnóstico dirigido e `!=` continua. | [ADR-0068](adr/0068-not-substitui-bang.md) |
| Destructuring aninhado | O padrão de `val`/`var (…) = t` é recursivo (`val (a, (b, c)) = t`), com erros por nível e sem `_` curinga. | [ADR-0069](adr/0069-destructuring-aninhado.md) |
| Strings multilinha e raw | `"""..."""` é a única forma multilinha (sem dedent/newline mágico); `r"..."`/`r"""..."""` desliga escapes e interpolação. | [ADR-0070](adr/0070-strings-multilinha-e-raw.md) |
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
| Exceções | `try`/`except Tipo as e`/`finally`/`raise`, classes `Exception`/`RuntimeError`, erros de runtime capturáveis como `RuntimeError`; `raise;` no except; backend L6. | [ADR-0042](adr/0042-excecoes.md), [ADR-0078](adr/0078-nome-loxia-extensao-lx.md) |
| Enums e `match` | Enums genéricos com variantes namespaced e payload posicional; `match` expressão exaustivo com `_`; `Result[T,E]` embutido com `Ok`/`Err`; igualdade estrutural. Padrões avançados e backend L6 pendentes. | [ADR-0041](adr/0041-enums-match.md) |
| Classes genéricas (T6a) | MVP: `class C[T]`, `ClassTy(name, args)`, invariante, inferência no construtor; sem métodos/herança genérica, constraints em classes ou `is/as` reificado (pendentes); backend 65 até o L6. | [ADR-0040](adr/0040-generics-classes-desenho.md) |
| Interfaces (ex-traits) | **Nominais**: a classe declara `implements`; checker verifica assinaturas; métodos default fazem parte da v1. O nome passou de "trait" para **interface** (ADR-0080); o modelo do ADR-0038 continua. V1 implementada no tree-walk/checker e no backend (B2, `itab`); dois casos no diferencial; constraints de função em [ADR-0081](adr/0081-constraints-generics.md). | [ADR-0038](adr/0038-traits-nominais.md), [ADR-0080](adr/0080-interfaces-nominais-implementacao.md) |
| Freeze da 1.0 | Erro de runtime não capturado é fatal (exit 70); `try`/`Result` são pós-freeze ([ADR-0041](adr/0041-enums-match.md), [ADR-0042](adr/0042-excecoes.md)); `clock` sai do prelúdio; strings UTF-8 com `len` em code points (indexação de string fora da 1.0) e identificadores ASCII; `print(valor)` é função `Any -> Nil` ([ADR-0085](adr/0085-print-como-funcao.md)); escopo congelado (single-file, sem módulos/`if`-expr/`match`/interfaces/`Any` no backend); generics é a exceção do ADR-0027. | [ADR-0026](adr/0026-freeze-1.0.md) |
| Generics T3b | Funções genéricas `fn id[T] (...)`, corpo checado uma vez; sem bounds só operações universais; `T: Ord + Num + Interface` na chamada ([ADR-0081](adr/0081-constraints-generics.md)); inferência na chamada (sem `id[Int]`); monomorfização no backend; recursão polimórfica recusada; função genérica não é valor. | [ADR-0027](adr/0027-generics-t3b.md) |
| Strings (texto) | Acesso a caractere por `chars(s) -> List[String]` (sem `s[i]`); `< <= > >=` por code point e `==`/`!=` por conteúdo; `len` em code points; sem normalização (`"é" != "e\\u{301}"`); identificadores ASCII; parse estrito sem `String.to_int`; builtins de string fora por ora. | [ADR-0035](adr/0035-strings-texto.md) |
| Generalização de lambda | `val f = fn(x) => x` infere parâmetros/retorno e generaliza o esquema (T4); `var` não generaliza; função genérica não é valor (inclusive `print`). Parâmetro de `fn` **continua exigindo anotação**: o T3c (parâmetro implícito) foi implementado e revertido. | [ADR-0033](adr/0033-inferencia-t3c-t4.md), [ADR-0034](adr/0034-t3c-revertido.md) |
| Overflow no debug | `--debug` checa `+ - * ** -`, `INT_MIN // -1` e `% -1`; overflow é erro fatal (exit 70); release continua wrapping; shifts não checam. | [ADR-0028](adr/0028-overflow-debug.md) |
| Conversões e `math` | `as` explícito (`Int`/`Float`/`Any`/classe/lista/mapa); `Float as Int` trunca e falha em NaN/Inf/range; `Int.parse`/`Float.parse` devolvem `T?`; `math.*` determinístico com abs/min/max/clamp/floor/ceil/round/trunc/sqrt; transcendentais fora do I3. | [ADR-0029](adr/0029-conversoes-math.md) |
| Tuplas | `(a, b)`/`(A, B)`, `t[i]` (literal com bounds no `--check`; dinâmico vira união), `val`/`var (a, b) = t` com anotação opcional, 2+ elementos, imutáveis e **covariantes**; igualdade/`len`/formatação; `for-in`/`is`/`as` e backend (L6) pendentes; não hasháveis. | [ADR-0030](adr/0030-tuplas.md), [ADR-0036](adr/0036-tuplas-implementacao.md) |
| Async | **Direção decidida; só as palavras-chave reservadas (sem sintaxe):** `async`/`await` *colored*, stackless, single-thread e determinístico; `Task[T]` embutido e covariante; top-level `await` (sem `async main`); `Task.all` com ordem preservada; sem `.then`/thenables/`race`; falha de tarefa é fatal; sem paralelismo. Entra depois do M7 e só com I/O, antes do M8. | [ADR-0037](adr/0037-async-direcao.md), [IDEIAS I-7](../IDEIAS.md) |
| `fn`/`elif`/`;` | `fn` substitui `fun`; `elif` é açúcar para `else if`; `;` opcional no fim da linha, EOF ou antes de `}`; operador só continua na mesma linha; `return` sozinho devolve `nil`. | [ADR-0011](adr/0011-fn-elif-ponto-e-virgula.md) |
| Comentários, `//`, `**` e bits | `#` e `/* */` aninhado; `//` truncado só `Int`; `**` com precedência matemática e `Int ** Int -> Int`; `& \| ^ ~ << >> >>>` em i64; shift inválido é erro. | [ADR-0012](adr/0012-comentarios-divisao-potencia-bits.md) |
| Ternário, `??`, `?.` e escapes | `a if c else b` (Python-style); `??` só nil; `?.` com optional call e assignment proibido; escapes `\n \t \r \" \\ \0 \u{...}`. Sem `?:`, interpolação, `"""` ou raw ainda. | [ADR-0013](adr/0013-ternario-nil-aware-escapes.md) |
| Desambiguação sintática | `//` onde se espera expressão ganha diagnóstico dirigido; operador pode iniciar linha dentro de `() [] {}` de expressão (fora, continua no fim da linha); `fn` é opcional em método; união no lado direito de `is` exige parênteses; mapa no início do statement ganha diagnóstico dirigido. | [ADR-0067](adr/0067-desambiguacao-sintatica.md) |
| API da stdlib | Modelo **híbrido**: builtins globais para operações genéricas/protocolos (`len`, `str`, `repr`), métodos para ações específicas (`xs.push/pop`), namespaces nativos para conversão (`Int.parse`/`Float.parse`, `math.*`) e funções livres para composição. Builtins globais são reservados (shadowing só local); sem métodos em primitivos; extensões/UFCS em P3 pós-LLVM. | [ADR-0016](adr/0016-api-stdlib-hibrida.md), [ADR-0029](adr/0029-conversoes-math.md) |
| Stdlib e batteries | Três camadas — kernel nativo, std em Lox e módulos; módulo só de declaração em `std/<nome>.lx`, privacidade por `_`; tiers T0–T3; cada módulo entra com programa real, golden e determinismo declarado; falha esperada é `T?`/`Result`, sem exceção na v1; fora: regex, cripto, rede, async, timezone, i18n. | [ADR-0072](adr/0072-stdlib-batteries.md) |

## Backend nativo (LLVM)

| Decisão | Resumo | Fonte |
| --- | --- | --- |
| Ferramenta | `llvmlite` como **extra opcional** (`uv sync --extra llvm`); object file emitido pelo LLVM embutido e link com `cc`; `.ll` é artefato de inspeção, não etapa de build; lib isolada em `loxia_core/backend/llvm_ir.py`. | [ADR-0031](adr/0031-backend-nativo.md) |
| Modelo de valor | Desboxado por tipo concreto (`Int`=i64, `Float`=f64, `Bool`=i1); `Any`/`List` cru/`Map` heterogêneo são erro de compilação até o L6; `loxia build` sempre roda checker. | [ADR-0031](adr/0031-backend-nativo.md) |
| `T?` | Ponteiro nulo para referência (`String?`, instância); `{i1, T}` para escalar (`Int?`, `Float?`, `Bool?`); narrowing devolve o `T` cru. | [ADR-0031](adr/0031-backend-nativo.md) |
| Erro de runtime | `lox_panic(linha, msg)`: flush do stdout, mensagem idêntica ao interpretador no stderr e exit 70; `main` devolve 0 no sucesso; traps de hardware proibidos. | [ADR-0031](adr/0031-backend-nativo.md) |
| Erro estático | Diagnóstico que o interpretador levantaria em runtime é **rebaixado a panic site** (ordem de avaliação preservada); o que só existe em compile-time (anotação) continua exit 65. | [ADR-0031](adr/0031-backend-nativo.md) |
| `Float` impresso | Menor representação testando `%.{p}e` + `strtod` (p = 1..17) e aplicando as convenções do `repr` do Python; fuzz contra `repr()`; `printf("%g")` proibido (locale) e `lox_init` fixa `LC_NUMERIC=C`. | [ADR-0031](adr/0031-backend-nativo.md) |
| `String` | Bytes UTF-8 com `byte_len`, `cp_len` e ponteiro; `len` O(1); ASCII detectado por `byte_len == cp_len`; semântica de `s[i]` em code points. | [ADR-0031](adr/0031-backend-nativo.md) |
| Memória | GC Boehm (`libgc`), coletor conservador; `lox_alloc`/`lox_alloc_*` continuam a fronteira; hard cap default de 512 MiB (build `--max-heap`) e I1 até 64 MiB de memória viva; sem RC. | [ADR-0074](adr/0074-gc-boehm-e-contrato-de-memoria.md), [ADR-0087](adr/0087-heap-cap-e-self-hosting.md) |
| Pilha de chamadas | 10.000 chamadas Lox ativas nos dois motores; a 10.001 é `R1015`/`Stack overflow.`, exit 70 e capturável; chamadas nativas e ctor de exceção não contam; `try`/`finally` restauram a profundidade; reserva de 128 MiB de soft limit no binário. | [ADR-0077](adr/0077-limite-de-pilha.md) |
| Verificação de IR | O driver roda o verificador do LLVM antes de emitir `.ll`/`.o`/executável; IR inválido vira `BackendError` (exit 65), nunca binário. | [ADR-0074](adr/0074-gc-boehm-e-contrato-de-memoria.md) |
| Generics | Monomorfização lazy com `type_of`/substituição publicados pelo checker, mangling por tipo e limite de instâncias (exit 65). | [ADR-0031](adr/0031-backend-nativo.md) |
| HIR | Normalização leve `AST → AST` (desugar), sem HIR completa no L0–L2; promove quando o lowering duplicar o interpretador. | [ADR-0031](adr/0031-backend-nativo.md) |
| Layout L5 | Instância `{ptr classe, campos base→derivada}`; vtable com prefixo e override no slot; `init` fora da vtable e `super.m` direto; bitmap de inicialização no MVP; classes locais suportadas. | [ADR-0043](adr/0043-layout-l5-classes.md) |
| Identidade de classe | `is`/`as`/`except` comparam o **objeto de classe** e a cadeia de superclasses; ids inteiros só para vtable/mangling/tags; classes locais homônimas são distintas; rebinding segue o binding atual. | [ADR-0044](adr/0044-identidade-classe.md) |
| Narrowing × backend | Lowering usa `storage_types` (declarado, sem narrowing); chamada/atribuição a campo/índice invalida refinos de campo/índice; `types` (fluxo) não define representação. | [ADR-0045](adr/0045-narrowing-representacao.md) |
| L6h — loop/nil/Any | Célula nova por iteração no `for-in`, variável não inicializada como `Any`, índice de `Any` com despacho de tupla. | [ADR-0058](adr/0058-l6-loop-capture-uninit.md) |
| L6g — defaults como valor | `Value`/`Binding` preservam `FunctionInfo`; chamada indireta preenche defaults no call site. | [ADR-0057](adr/0057-l6-defaults-as-value.md) |
| L6f — math/parse | `math.*` em IR/helpers, `floor` etc. com validação de Float em Int, e parse estrito de `Int`/`Float` devolvendo `T?`. | [ADR-0056](adr/0056-l6-math-parse.md) |
| L6i — enums/`match`/`Result` | Valor de enum com descritor, construtor de variante, dispatch por variante, `Result` embutido, print/igualdade e tag `ENUM`; sem HIR. | [ADR-0061](adr/0061-l6-enums-match.md) |
| L6j — exceções | ABI `LoxTryFrame`/`LoxException`, `setjmp`/`longjmp`, pilha de cleanup para `finally` e erros de runtime capturáveis; `lox_panic` vira fallback. | [ADR-0062](adr/0062-l6-excecoes-unwinding.md) |
| Orçamento de monomorfização | Chave canônica, 256 funções + 256 classes, profundidade 8 e diagnóstico determinístico; valor genérico no call site ou adiado. | [ADR-0063](adr/0063-orcamento-monomorfizacao.md) |
| Teto de `PENDING` | `PENDING` ≤ 5% do corpus, com nível/motivo e `l?` proibido; I1 só cobre `LEVELS`. | [ADR-0064](adr/0064-orcamento-do-corpus.md) |
| HIR-lite | Sem HIR completa; enums diretos, exceções com cleanup stack e HIR-lite só de controle se o gatilho de complexidade disparar. | [ADR-0065](adr/0065-hir-lite-controle.md) |
| L6e — `Any` | Unbox checado, `is`/`as` por tag/classe, igualdade dinâmica e `for-in` de tupla materializando `Any`; enums/exceções seguem. | [ADR-0055](adr/0055-l6-any-casts.md) |
| L6d — tuplas | `LoxTuple` boxeada, literal/índice/`len`/igualdade/print e destructuring; `is/as`/`Any`/`for-in` de tupla seguem. | [ADR-0054](adr/0054-l6-tuplas.md) |
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
| Diagnósticos estruturados | Um `Diagnostic` por execução (código de família, fase, span com linha/coluna/offset), renderizadores `human`/`short`/`json`, ordem/dedup/cap determinísticos e caminho relativo; runtime humano com o mesmo cabeçalho, sem caret, nos dois motores. | [ADR-0075](adr/0075-diagnosticos-estruturados.md) |
| Corpus do I1 | Corpus inteiro **anotado** (`tests/cases`, `exemplos/`, `tests/official/cases`); CI sempre com o extra `llvm`; promoção monotônica; suíte do livro entra quando anotada. | [ADR-0031](adr/0031-backend-nativo.md), [`spec/garantias.md`](spec/garantias.md) |
| Primitivas e kernel | Kernel = SO ou representação (≤ 15 funções); o resto é Lox. Tabela única (`lox`, símbolo C, tipos, corpo Python, `ambient`) alimenta checker/interpreter/backend/testes. `LoxStr` ganha cache de offsets: `charAt`/`chars`/`for-in` **O(n)**, `substr` O(1)+cópia e `join` O(total). Sem FFI genérica e sem `ctypes` no oráculo; gatilho: kernel > 15 ou divergência observada. | [ADR-0071](adr/0071-primitivas-de-runtime.md) |
| Kernel T2 | `io.readAll`, `fs.exists` e `fs.listDir` entram como primitivas `ambient` (SO); o teto vai de 15 para **17**. `listDir` ordena por byte e devolve `nil` em erro; `readAll` não normaliza quebras. | [ADR-0079](adr/0079-stdlib-t2.md) |
| Campos-container | `List`/`Map`/`Tuple`/`Range`/`Enum` em campo de instância são ponteiros em slot `i64` (como `String`); `Any` como campo continua 65. | [ADR-0079](adr/0079-stdlib-t2.md) |
| `str(Any)` | `str` e interpolação de valor boxeado usam `lox_str_from_any` com a mesma tabela do `print` dinâmico; no topo, string não é citada. | [ADR-0079](adr/0079-stdlib-t2.md) |
| Chave de `Map` no C | `lox_map_set/has/get/get_checked/remove` recebem `line`/`column` e validam tags (`R1014`), igual ao interpretador; divergência fechada com caso diferencial. | [ADR-0079](adr/0079-stdlib-t2.md) |
| Stdlib T2 | `json`, `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv`, `convert`: Lox puro sobre o kernel, sem sintaxe nova; `Set[T]` guarda `Map[Any, Bool]` (constraints de chave são pós-MVP) e `fs`/leitura de `io` são `ambient` (fora do corpus I1). | [ADR-0079](adr/0079-stdlib-t2.md) |
| Ranges inclusivos | `a..=b` inclui o fim, mesma precedência de `..`, sem passo; `Range.inclusive` entra na igualdade e na impressão; `INT_MAX..=INT_MAX` não faz wrap. | [ADR-0097](adr/0097-ranges-inclusivos.md) |
| Property-based | `std.property`: `Gen[T]` com `generate`/`shrink`, `forAll(runs=100, seed=0)`, geradores e shrinking (Int/List/String) para falhas mínimas e reproduzíveis. | [ADR-0098](adr/0098-property-based-testing.md) |
| Testes | Duas camadas: `std.test` (Lox, `Suite` explícita, `it` imediato, hooks `beforeEach`/`afterEach`, TAP, `TestFailure`/`Skip`, matchers híbridos) e `loxia test` (descoberta `tests/**/*_test.lx`, `--isolate=file|test` com N processos, `--filter/--only/--jobs/--timeout/--json/--native`). Sem reflection/registry (`R3`); fakes no usuário, `Recorder` na lib; `report()` puro + `done()` com exit; trace/localização depois. | [ADR-0096](adr/0096-testes-biblioteca-e-runner.md) |
| Processos e `poll` | `process.*` no kernel (handles `Int` 1-based) + `std.proc` (`Stream`/`Process`/`Output`, `spawn`, `run`): sem shell, pipes, `poll` mistura streams e processos, leitura em fronteira UTF-8, `SIGPIPE` ignorado e `wait` idempotente. POSIX/ambiente; kernel 19 → 29. | [ADR-0095](adr/0095-processos-streams-poll.md) |
| Stdio por bytes | `io.write`/`io.writeErr` flusham por chamada e `io.flush()` força stdout/stderr; `io.readUtf8(n)` lê exatamente `n` bytes UTF-8 estrito (`nil` só no EOF imediato, erro com posição nos demais casos). Kernel vai de 17 para **19**; `site` na tabela dá `(line, column)` ao símbolo C das primitivas falíveis. | [ADR-0094](adr/0094-kernel-io-flush-e-read-utf8.md) |

## Processo e escopo

| Decisão | Resumo | Fonte |
| --- | --- | --- |
| Pipeline `\|>`/`:>` | **Rejeitado por enquanto** em 2026-11-11; alternativas e gatilhos de reabertura ficam registrados. | histórico no git |
| Identidade e invariantes | A linguagem se define por **I1** equivalência executável, **I2** nada implícito e **I3** determinismo observável; features passam pelo portão de admissão. | [ADR-0014](adr/0014-identidade-e-invariantes.md), [`spec/garantias.md`](spec/garantias.md) |
| `--check` limpo compila (I4) | Programa com check limpo compila; a única recusa aceitável no lowering é `not supported by the backend yet`. O checker é a fonte única dos tipos. | [ADR-0059](adr/0059-i4-check-limpo-compila.md) |
| Sem promoção em armazenamento | `Int → Float` só vale em aritmética; `val x: Float = 2`, `x = 2`, `f(2)` e `return 2` exigem `2.0`/`as Float` (Kotlin-like). | [ADR-0059](adr/0059-i4-check-limpo-compila.md), [ADR-0006](adr/0006-int-float-separados.md) |
| Orçamento de memória | GC Boehm com hard cap default de 512 MiB e `--max-heap` de build; I1 cobre até 64 MiB de memória viva; acima disso, fora do corpus. `Out of memory.` é `exit 70`, mas o ponto exato da falha não é determinístico (coletor conservador). Ownership estilo Rust rejeitado. | [ADR-0074](adr/0074-gc-boehm-e-contrato-de-memoria.md), [ADR-0087](adr/0087-heap-cap-e-self-hosting.md) |
| Orçamento de pilha | 10.000 chamadas Lox; `R1015`/`Stack overflow.` catchable; orçamento de 64 MiB e reserva de 128 MiB no binário; `try`/`finally` restauram a profundidade. | [ADR-0077](adr/0077-limite-de-pilha.md) |
| Stack trace de runtime | Erro não capturado imprime frames default-on (nome exibível + call site), default 5 internos + 5 externos + elisão; `R1015` ganha a posição da declaração; o binário reproduz byte a byte (I1). | [ADR-0089](adr/0089-stack-trace-de-runtime.md) |
| Nome e extensão | A linguagem é **Loxia** e a extensão canônica é `.lx`; "Lox" fica como nome do dialeto do livro; o prelúdio embutido usa `Exception`/`RuntimeError` (sem a marca), e `Lox*`/`lox.` no código são herança declarada. | [ADR-0078](adr/0078-nome-loxia-extensao-lx.md) |
| Gate e orçamento sintático | Sintaxe nova passa por quatro perguntas (substituição, decidibilidade local, precedência, forma canônica), tetos de superfície e lista de não-objetivos; o agente pergunta antes de adicionar sintaxe. | [ADR-0066](adr/0066-orcamento-e-gate-sintatico.md) |
| LSP | Servidor Python no repo principal (`loxia lsp`), JSON-RPC stdio à mão, sem dependência; LSP-0 diagnostics/symbols, LSP-1 spans+SymbolIndex para hover/definition, LSP-2 completion/format/code actions; não em Loxia. **LSP-0, LSP-1 básico e LSP-2 parcial implementados em 2026-11-16** (hover/definition, completion/signature/formatting/semantic tokens); codeAction/fixes e rename pendentes. | [ADR-0090](adr/0090-lsp-escopo-e-hospedagem.md) |
| Documentação | `///` como doc comment (Markdown, anexada à declaração), API pública da stdlib/builtins em inglês e obrigatória; `loxia doc` gera Markdown/JSON e o site consome. **Core, docs da stdlib/builtins e `docs/stdlib/` implementados em 2026-11-16**; integração do site pendente. | [ADR-0091](adr/0091-doc-comments-e-geracao-de-docs.md) |
| Estilo e formatter | Tipos `PascalCase`, funções/vars/campos `camelCase`; enum constante `UPPER_SNAKE`, enum soma `PascalCase`; 2 espaços/100 col, `;` omitido, `fn` mantido em método; formatter Python agora e dogfood Lox após T3 com paridade. **Guia + `loxia fmt` mínimo implementados em 2026-11-16**; `fn` em método, trailing comma, reflow e Lox pendentes. | [ADR-0092](adr/0092-estilo-e-formatter.md) |
| CLI agent-friendly | Subcomandos aditivos, `capabilities`/`explain`, JSONL/watch restrito a `check`, `--stdin`, `--timeout` (124 + `C0001`), warnings `W1xxx` com `-Werror` e protocolo de reparo com `fixes[]` safe/unsafe. **Core implementado em 2026-11-16**; `fixes[]`, `W1002`, `fmt`, `doc` e `lsp` pendentes. | [ADR-0093](adr/0093-cli-agent-friendly-e-reparo.md) |

## O que ainda não está aqui

Nome/extensão da linguagem, `if`/blocos como expressão, `print` como função, `match`
estrutural para uniões (o de enums fechou no [ADR-0041](adr/0041-enums-match.md)),
**generics de classes/métodos e constraints em classes**, contratos e unificação mutável
continuam **em aberto** no
[`../TODO.md`](../TODO.md) §11. Tuplas foram implementadas no interpretador/checker ([ADR-0036](adr/0036-tuplas-implementacao.md)); no backend ficam para o L6. Async tem direção decidida, mas implementação pendente ([ADR-0037](adr/0037-async-direcao.md)).
Módulos têm forma implementada em [ADR-0073](adr/0073-imports-modulos.md): arquivo=módulo,
pasta=namespace, `_` privado verificado, `std.*` reservado e imports de arquivos do usuário.

Distribuição fechada no [ADR-0088](adr/0088-distribuicao-e-raizes-de-modulo.md):
`loxia` é o comando (`[project.scripts]`), a stdlib viaja como package data
(`loxia/std`, nome reservado, versão = versão do compilador), `loxia.toml` declara raízes
(`[modules] paths`) com ordem fixa **projeto → declaradas → std**, ambiguidade é erro,
`..` continua proibido no `import` (só como raiz declarada) e sem manifest o comportamento
atual permanece. **Empacotamento entregue** em 2026-11-15 (wheel com comando `loxia`,
`std/` e `runtime.c`; `tests/test_install.py`); faltam `loxia.toml` e subcomandos
([`../TODO.md`](../TODO.md) §14.4).

`std.lists.sort` usa comparador de três vias e é estável, retornando lista nova; `sortNatural[T: Ord]` cobre a ordenação natural ([ADR-0081](adr/0081-constraints-generics.md)); `sortBy`/`groupBy` ficam pós-MVP ([ADR-0076](adr/0076-std-lists-sort.md)).
