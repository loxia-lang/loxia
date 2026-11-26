# ADRs — Architecture Decision Records

Record of the decisions that shape the language and the compiler. An ADR explains **why**
the choice was made, what it costs and what was discarded — things the diff does not tell.

## When to create an ADR

Create one when the decision:

- changes syntax, semantics or observable behavior;
- is hard to reverse (value representation, type model, backend, error format);
- has relevant trade-offs (immutability by default, `Int` vs `Float`, `|>` vs UFCS);
- establishes process/architecture that everyone must follow.

Do **not** create one for a bug fix, an internal refactor with no external consequence or a
TODO item.

## Flow

1. Discuss in [Discussions › Ideas](https://github.com/loxia-lang/loxia/discussions/categories/ideas)
   or in an issue labeled `decision`; pending type questions stay in
   [`../../TIPOS.md`](../../TIPOS.md).
2. Decide, with a test case that demonstrates the behavior.
3. Create `NNNN-slug.md` from the [template](template.md), with status `accepted`.
4. Update [`../spec/`](../spec/) to reflect what the code does.
5. Add it to the index below.

## Rules

- **An accepted ADR is immutable.** Changed your mind? Create a new ADR and mark the old one
  as `superseded by ADR-XXXX`.
- Sequential 4-digit numbering; never reuse a number.
- Language: existing ADRs are written in Portuguese (they are not being translated now);
  code identifiers stay in English.
- Every ADR lists **negative** consequences or costs. A decision with no cost is suspect.
- Open discussion is **not** an ADR — it lives in Discussions › Ideas or in a `decision`
  issue. A deferred language/runtime decision is recorded in
  [ADR-0107](0107-adiados-e-nao-objetivos.md); a deferred process/release decision gets its
  own ADR and is cross-referenced there.

## Status

| Status | Meaning |
| --- | --- |
| `proposed` | under discussion; may still change |
| `accepted` | decided and (where applicable) implemented |
| `rejected` | discarded; the reason why is recorded |
| `superseded by ADR-XXXX` | replaced by another ADR |
| `deprecated` | still valid, but should not be used in new code |

## Index

| # | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-registrar-decisoes-em-adrs.md) | Recording decisions in ADRs | accepted | 2026-11-11 |
| [0002](0002-tree-walk-como-oraculo.md) | The tree-walk is the executable specification | accepted | 2026-11-11 |
| [0003](0003-diagnosticos-por-execucao.md) | Per-run diagnostics, with no global state | accepted | 2026-11-11 |
| [0004](0004-identidade-dos-nos-de-ast.md) | AST nodes have identity | accepted | 2026-11-11 |
| [0005](0005-val-var-imutabilidade.md) | `val`/`var` and binding immutability | accepted | 2026-11-11 |
| [0006](0006-int-float-separados.md) | `Int` (i64) and `Float` (f64) separate | accepted | 2026-11-11 |
| [0007](0007-ranges-e-iteracao.md) | Ranges and iteration with a built-in protocol | accepted | 2026-11-11 |
| [0008](0008-heranca-class-parens.md) | Inheritance with `class Dog(Animal)` and an `init` constructor | accepted | 2026-11-11 |
| [0009](0009-defaults-e-campos.md) | Default parameters and declared fields | accepted | 2026-11-11 |
| [0010](0010-tipagem-estatica.md) | Gradual static typing with `--check` | accepted | 2026-11-11 |
| [0011](0011-fn-elif-ponto-e-virgula.md) | `fn`, `elif` and optional `;` | accepted | 2026-11-11 |
| [0012](0012-comentarios-divisao-potencia-bits.md) | Comments, `//`, `**` and bits | accepted | 2026-11-11 |
| [0013](0013-ternario-nil-aware-escapes.md) | Ternary, `??`, `?.` and escapes | accepted | 2026-11-11 |
| [0014](0014-identidade-e-invariantes.md) | Identity: three invariants and an admission gate | accepted | 2026-11-11 |
| [0015](0015-listas-tipadas.md) | Typed `List[T]` lists, mutable and invariant | accepted | 2026-11-11 |
| [0016](0016-api-stdlib-hibrida.md) | Stdlib API: hybrid model, minimal prelude and reserved builtins | accepted | 2026-11-11 |
| [0017](0017-mapas-hash.md) | `Map[K, V]` maps, `{ k: v }` literal and explicit missing key | accepted | 2026-11-11 |
| [0018](0018-narrowing.md) | Flow narrowing for `T?` | accepted | 2026-11-11 |
| [0019](0019-interpolacao.md) | `"${expr}"` interpolation | accepted | 2026-11-11 |
| [0020](0020-assinaturas-explicitas.md) | Explicit signatures and functions declared later | accepted | 2026-11-12 |
| [0021](0021-tipos-de-funcao.md) | Function types in annotations | accepted | 2026-11-12 |
| [0022](0022-lambdas.md) | Lambdas with `fn(x) => ...` and contextual typing | accepted | 2026-11-12 |
| [0023](0023-soundness-do-checker.md) | Checker soundness: return, fields and override | accepted | 2026-11-12 |
| [0024](0024-mutacao-monomorfica.md) | Monomorphic mutation and `var x = nil` | accepted | 2026-11-12 |
| [0025](0025-is-e-narrowing.md) | `is T` and union narrowing | accepted | 2026-11-12 |
| [0026](0026-freeze-1.0.md) | 1.0 freeze: errors, determinism, UTF-8 and scope | accepted | 2026-11-12 |
| [0027](0027-generics-t3b.md) | Generics T3b: functions, monomorphization and inference | accepted | 2026-11-12 |
| [0028](0028-overflow-debug.md) | Checked overflow in `--debug` mode | accepted | 2026-11-12 |
| [0029](0029-conversoes-math.md) | Conversions (`as`, parse) and deterministic `math.*` | accepted | 2026-11-12 |
| [0030](0030-tuplas.md) | Tuples: chosen syntax, post-1.0 implementation | accepted (post-1.0) | 2026-11-12 |
| [0031](0031-backend-nativo.md) | Native backend: value contract, runtime and corpus | accepted (L0–L4; L5–L7 pending) | 2026-11-12 |
| [0032](0032-narrowing-campos-indices.md) | Narrowing of fields and literal indices | accepted | 2026-11-12 |
| [0033](0033-inferencia-t3c-t4.md) | T3c/T4 inference | accepted (T4; T3c reverted in ADR-0034) | 2026-11-12 |
| [0034](0034-t3c-revertido.md) | T3c reverted: the implicit parameter is out | accepted | 2026-11-12 |
| [0035](0035-strings-texto.md) | Strings as text: code points and order | accepted | 2026-11-12 |
| [0036](0036-tuplas-implementacao.md) | Tuples: implementation in the interpreter and checker | accepted | 2026-11-12 |
| [0037](0037-async-direcao.md) | Async: colored, deterministic and post-M7 | accepted (direction; keywords reserved) | 2026-11-12 |
| [0038](0038-traits-nominais.md) | Interfaces (formerly traits), nominal, with default methods | superseded by ADR-0080 (naming) and ADR-0081 (constraints) | 2026-11-12 |
| [0039](0039-decisoes-tipos-pendentes.md) | Pending type decisions | accepted | 2026-11-12 |
| [0040](0040-generics-classes-desenho.md) | Generic classes (T6a): design | accepted (MVP; follow-ups deferred) | 2026-11-12 |
| [0041](0041-enums-match.md) | Generic enums, exhaustive `match` and `Result` | accepted (MVP; backend L6) | 2026-11-13 |
| [0042](0042-excecoes.md) | Exceptions: `try`/`except`/`finally`/`raise` | accepted (tree-walk; backend L6) | 2026-11-13 |
| [0043](0043-layout-l5-classes.md) | L5 layout: classes, fields, vtable and `init` | accepted (design; backend L5 pending) | 2026-11-13 |
| [0044](0044-identidade-classe.md) | Class identity at runtime (`is`/`as`/`except`) | accepted (tree-walk; backend L5 pending) | 2026-11-13 |
| [0045](0045-narrowing-representacao.md) | Narrowing and representation types | accepted (checker/tree-walk; backend L5 pending) | 2026-11-13 |
| [0046](0046-closures-celulas-l4.md) | L4: closures, cells and function values | accepted (backend L4 implemented) | 2026-11-13 |
| [0047](0047-optionais-escalares-l2-5.md) | L2.5: scalar optionals, contextual `nil` and safe unwrap | accepted (backend L2.5 implemented) | 2026-11-13 |
| [0048](0048-abi-classes-l5.md) | L5: method ABI, class descriptor and instance | accepted (L5a/L5b/L5c implemented) | 2026-11-13 |
| [0049](0049-any-boxeado-spike-l6.md) | L6: boxed `Any` as a union spike | accepted (spike; not full `Any`) | 2026-11-13 |
| [0050](0050-monomorfizacao-t7.md) | T7: monomorphization of generic functions and classes | accepted (T7a/b/c; containers in L6) | 2026-11-13 |
| [0051](0051-l6-range-for-in-escalares.md) | L6a: Range, `for-in` and scalar operations | accepted (containers/tuples/Any/enums/exceptions pending) | 2026-11-13 |
| [0052](0052-l6-listas.md) | L6b: boxed lists in the runtime | accepted (Map/tuples/Any/enums/exceptions pending) | 2026-11-13 |
| [0053](0053-l6-mapas.md) | L6c: boxed maps in the runtime | accepted (tuples/Any/enums/exceptions pending) | 2026-11-13 |
| [0054](0054-l6-tuplas.md) | L6d: boxed tuples | accepted (Any/is/as/tuple for-in pending) | 2026-11-13 |
| [0055](0055-l6-any-casts.md) | L6e: `Any` with unbox, `is`/`as`, equality and tuple `for-in` | accepted (first slice) | 2026-11-13 |
| [0056](0056-l6-math-parse.md) | L6f: `math.*` and `Int.parse`/`Float.parse` | accepted | 2026-11-13 |
| [0057](0057-l6-defaults-as-value.md) | L6g: function with defaults as a value | accepted | 2026-11-13 |
| [0058](0058-l6-loop-capture-uninit.md) | L6h: per-iteration capture, nil variable and `Any` tuple index | accepted | 2026-11-13 |
| [0059](0059-i4-check-limpo-compila.md) | I4: a clean check compiles; promotion only in arithmetic | accepted | 2026-11-13 |
| [0060](0060-orcamento-de-memoria.md) | Memory budget (64 MiB arena) in the contract | superseded by [0074](0074-gc-boehm-e-contrato-de-memoria.md) | 2026-11-13 |
| [0061](0061-l6-enums-match.md) | L6i: enums, `Result` and `match` | accepted | 2026-11-13 |
| [0062](0062-l6-excecoes-unwinding.md) | L6j: exceptions, unwinding ABI and cleanup | accepted | 2026-11-13 |
| [0063](0063-orcamento-monomorfizacao.md) | Monomorphization budget and generic value | accepted (implemented) | 2026-11-13 |
| [0064](0064-orcamento-do-corpus.md) | Corpus ceiling: 5% for `PENDING` and the I1 promise | accepted | 2026-11-13 |
| [0065](0065-hir-lite-controle.md) | HIR-lite: scope, trigger and not doing full HIR | accepted | 2026-11-13 |
| [0066](0066-orcamento-e-gate-sintatico.md) | Syntax budget and gate: ceilings, non-goals and human approval | accepted | 2026-11-13 |
| [0067](0067-desambiguacao-sintatica.md) | Disambiguation: `//`, brackets, `fn` in methods, union in `is`, map | accepted | 2026-11-13 |
| [0068](0068-not-substitui-bang.md) | `not` replaces `!` as negation (one spelling, same precedence) | accepted | 2026-11-13 |
| [0069](0069-destructuring-aninhado.md) | Recursive nested destructuring in `val`/`var` | accepted | 2026-11-13 |
| [0070](0070-strings-multilinha-e-raw.md) | Canonical `"""` for multiline and raw `r"..."`/`r"""..."""` | accepted | 2026-11-13 |
| [0071](0071-primitivas-de-runtime.md) | Runtime primitives: native boundary, single table and linear complexity | accepted (plan; implementation pending) | 2026-11-14 |
| [0072](0072-stdlib-batteries.md) | Stdlib: native kernel, library in Lox and batteries policy | accepted (plan; implementation pending) | 2026-11-14 |
| [0073](0073-imports-modulos.md) | Imports, file modules, private `_` and desugaring | accepted (implemented) | 2026-11-14 |
| [0074](0074-gc-boehm-e-contrato-de-memoria.md) | Boehm GC and memory contract (hard cap updated to 512 MiB by ADR-0087) | accepted (implemented) | 2026-11-14 |
| [0075](0075-diagnosticos-estruturados.md) | Structured diagnostics: model, stable codes, `human`/`short`/`json` and determinism | accepted (implemented) | 2026-11-14 |
| [0076](0076-std-lists-sort.md) | `std.lists.sort`: three-way comparator, stable, new list | accepted (implemented) | 2026-11-14 |
| [0077](0077-limite-de-pilha.md) | Call depth limit (10,000) and `Stack overflow.` | accepted (implemented) | 2026-11-15 |
| [0078](0078-nome-loxia-extensao-lx.md) | Name **Loxia**, `.lx` extension and prelude without the brand (`RuntimeError`) | accepted (implemented) | 2026-11-15 |
| [0079](0079-stdlib-t2.md) | Stdlib T2: kernel 17, container fields, `str(Any)` and `Map` key validation in C | accepted (implemented) | 2026-11-15 |
| [0080](0080-interfaces-nominais-implementacao.md) | Nominal interfaces: syntax, checking, defaults, types and ABI | accepted (implemented) | 2026-11-15 |
| [0081](0081-constraints-generics.md) | Constraints on generic functions: `T: Ord + Num + Interface` | accepted (implemented) | 2026-11-15 |
| [0082](0082-iterador-de-usuario.md) | User iterator in `for-in`: `iter()` + `next() -> T?` | accepted (implemented) | 2026-11-15 |
| [0083](0083-variadicos.md) | Variadics `...args` and final spread `f(...xs)` | accepted (implemented) | 2026-11-15 |
| [0084](0084-type-alias.md) | Transparent, non-generic `type` alias | accepted (implemented) | 2026-11-15 |
| [0085](0085-print-como-funcao.md) | `print` as a builtin function (`Any -> Nil`); statement removed | accepted (implemented) | 2026-11-15 |
| [0086](0086-narrowing-captura-e-merge.md) | Narrowing: invalidation of captured `var` and flow merge | accepted (implemented) | 2026-11-15 |
| [0087](0087-heap-cap-e-self-hosting.md) | Heap: 512 MiB default and build-time `--max-heap` | accepted (implemented) | 2026-11-15 |
| [0088](0088-distribuicao-e-raizes-de-modulo.md) | Distribution: `loxia` command, embedded stdlib and declared module roots | accepted (implemented) | 2026-11-15 |
| [0089](0089-stack-trace-de-runtime.md) | Runtime stack trace: frames, call site and R1015 position | accepted (implemented) | 2026-11-15 |
| [0090](0090-lsp-escopo-e-hospedagem.md) | LSP: Python in the repo, JSON-RPC, diagnostics and phases | accepted (partial implementation) | 2026-11-16 |
| [0091](0091-doc-comments-e-geracao-de-docs.md) | Documentation: `///` doc comments, Markdown and generation | accepted (partial implementation) | 2026-11-16 |
| [0092](0092-estilo-e-formatter.md) | Style and formatter: names, profile and dogfooding in Lox | accepted (partial implementation) | 2026-11-16 |
| [0093](0093-cli-agent-friendly-e-reparo.md) | Agent-friendly CLI: subcommands, JSONL/watch, timeout, warnings and repair | accepted (partial implementation) | 2026-11-16 |
| [0094](0094-kernel-io-flush-e-read-utf8.md) | Kernel: `io.flush`, `io.readUtf8` and flush per write on stdio | accepted (implemented) | 2026-11-16 |
| [0095](0095-processos-streams-poll.md) | Processes, streams and `poll` in the kernel (`std.proc`) | accepted (implemented) | 2026-11-16 |
| [0096](0096-testes-biblioteca-e-runner.md) | Tests: `std.test` (library) and `loxia test` (runner) | accepted (implemented) | 2026-11-16 |
| [0097](0097-ranges-inclusivos.md) | Inclusive ranges (`..=`) | accepted (implemented) | 2026-11-16 |
| [0098](0098-property-based-testing.md) | Property-based testing (`std.property`) | accepted (implemented) | 2026-11-16 |
| [0099](0099-notas-de-proveniencia.md) | Provenance notes in type errors | accepted (implemented) | 2026-11-16 |
| [0100](0100-dependencias-path.md) | `path` dependencies and resolution by package name | accepted (implemented) | 2026-11-16 |
| [0101](0101-licenca-dual-e-politica-de-contribuicao.md) | Dual MIT/Apache-2.0 license and contribution policy (DCO) | accepted (partial implementation) | 2026-11-17 |
| [0102](0102-ingles-na-vitrine-e-docs-pt-br.md) | English in the public showcase; internal docs in pt-BR until the translation | accepted (first stage) | 2026-11-17 |
| [0103](0103-site-de-documentacao-e-versionamento.md) | Documentation site: Starlight, staging and reference version | accepted (implemented; deploy on the flip) | 2026-11-17 |
| [0104](0104-lock-e-frozen.md) | Package lock: tree hash, `--frozen`, local cache and `C0002` | accepted (implemented) | 2026-11-17 |
| [0105](0105-dependencias-git.md) | Git dependencies: pinned `rev`, bare mirror, clean checkout and offline fetch | accepted (implemented) | 2026-11-17 |
| [0106](0106-scaffolding-new-init.md) | Scaffolding: `loxia new`/`init`, minimal template, git and name rules | accepted (implemented) | 2026-11-17 |
| [0107](0107-adiados-e-nao-objetivos.md) | Deferred and non-goals: consolidated reopen triggers | accepted (consolidation) | 2026-11-18 |
| [0108](0108-contratos-como-biblioteca.md) | Contracts as a library: `std.contracts`, no syntax yet | accepted (library implemented; adoption pending) | 2026-11-18 |
| [0109](0109-editor-repo-e-assets.md) | Editor client in its own repo; generated grammar as a release asset | accepted (implemented; publishing pending accounts) | 2026-11-18 |
| [0110](0110-help-do-cli-e-modulos.md) | CLI help per command; CLI split into args/commands/engine | accepted (implemented) | 2026-11-19 |
| [0111](0111-indice-de-documentacao.md) | Deterministic documentation index for agents, site and MCP | accepted (implemented) | 2026-11-19 |
| [0112](0112-mcp-servidor-stdio.md) | MCP server over the CLI: modern-only stdio, sandbox profile, zero-dep | accepted (implemented) | 2026-11-19 |
| [0113](0113-protocolo-stdio-jsonrpc-framing-documents.md) | Stdio protocol as three modules: JSON-RPC envelopes, `Content-Length` framing and document store | accepted (implemented) | 2026-11-19 |
| [0114](0114-ast-recuperada-para-tooling.md) | Recovered AST for tooling: strict CLI, parser prefix for the LSP | accepted (implemented) | 2026-11-19 |
| [0115](0115-corpus-de-conformidade-adiado.md) | Conformance corpus artifact: deferred until a published `lox-core` spec exists | accepted (deferred) | 2026-11-19 |
| [0116](0116-benchmarks-publicos-adiados.md) | Public benchmarks: deferred until a reproducible protocol and a performance-led release exist | accepted (deferred) | 2026-11-19 |
| [0117](0117-ast-manual-e-cobertura-de-visitantes.md) | AST stays manual: visitor coverage enforced by protocols and a hierarchy guard | accepted (implemented) | 2026-11-19 |
| [0118](0118-toml-na-toolchain-e-edicao-de-manifest.md) | TOML: data model in the language (spike first), comment-preserving editing in the tool | accepted (implemented) | 2026-11-19 |
| [0119](0119-fs-open-handles-e-erro-de-host.md) | File handles plus one `Result` pattern for host failures across the stdlib | accepted (implementation partial) | 2026-11-19 |
| [0120](0120-localizacao-de-falha-em-excecoes.md) | Caught exceptions expose `e.site` (`file:line:column`) for test failure location | accepted (implemented) | 2026-11-19 |
| [0121](0121-matriz-de-cobertura-de-features.md) | Curated feature → golden/differential matrix, snapshot and generated coverage page | accepted (implemented) | 2026-11-19 |
| [0122](0122-contrato-de-data-e-instante.md) | Time is milliseconds; civil date is an `(Int, Int, Int)` tuple; `timex` v2 validates, formats offsets and does calendar arithmetic | proposed | 2026-11-20 |
| [0123](0123-orcamento-do-kernel-por-grupo.md) | Kernel budget per group with an executable test; `fs` mutation and vendored SHA-256 approved, table stays in Python | proposed | 2026-11-20 |
| [0124](0124-fmt-self-host-e-pacotes-por-repo.md) | Lox front-end and formatter as the first self-hosted consumer; tooling packages are born as org repos, `glob` is the pilot | proposed | 2026-11-20 |
| [0125](0125-bytes-tipo-binario.md) | `Bytes`: immutable binary value type, no new syntax, native-module buffer ABI | proposed | 2026-11-21 |
| [0126](0126-modulo-nativo-embutido-sqlite.md) | Bundled native modules, SQLite first: separate budget, conditional link, vendored amalgamation | proposed | 2026-11-21 |
| [0127](0127-pacotes-com-codigo-nativo.md) | Third-party native packages: contract recorded, implementation deferred with four triggers | proposed | 2026-11-21 |
| [0128](0128-contrato-de-motores.md) | Three engine layers (core/ambient/native-only) with an explicit interpreter refusal instead of silent divergence | proposed | 2026-11-21 |
| [0129](0129-oraculo-do-front-end.md) | Front-end oracle: per-file AST, versioned JSON with spans, and a frozen AST/formatter/diagnostics snapshot | accepted (implemented) | 2026-11-21 |
| [0130](0130-regex-pcre2-embutido.md) | Regex: vendored PCRE2, one engine behind `run` (ctypes) and `--emit=exe`, `bundled/regex` | superseded by ADR-0131 | 2026-11-22 |
| [0131](0131-regex-motor-rust-dois-modos.md) | Regex: Rust engine (`regex` linear by default, `fancy-regex` opt-in), own C ABI, two-stage distribution | accepted (implemented in #119) | 2026-11-22 |
| [0132](0132-nos-de-erro-na-arvore-recuperada.md) | Recovered AST: inert `ErrorStmt`/`ErrorExpr`, line-aware recovery, `--allow-errors` opt-in | accepted (implemented) | 2026-11-22 |
| [0134](0134-trivia-side-table.md) | Trivia as a scanner side table: exact comments/whitespace, normalized round-trip, deterministic attachment | accepted (implemented) | 2026-11-22 |
| [0133](0133-suite-rapida-in-process-e-xdist.md) | Fast suite: CLI in-process for case tests, xdist in the local loop, real processes where they matter | accepted (implemented) | 2026-11-22 |
| [0135](0135-politica-de-erro.md) | Error policy: defect (`RuntimeError`), expected failure (`Result`), user flow (`raise`); one channel per signature, `OrRaise` shell, stdlib allowlist, `Err` at top = exit 70 | accepted (migration tracked) | 2026-11-23 |
| [0136](0136-formatter-2-doc-ir.md) | Formatter 2.0: Doc IR + item layer, width-aware wrapping, comment preservation, blank-line policy and the `format_source` contract | accepted (implemented) | 2026-11-23 |
| [0137](0137-mcp-format.md) | MCP `loxia_format`: formatted text + `TextEdit[]`, source/path read-only, range by expanded hunks, check/diff | accepted (implemented) | 2026-11-23 |
| [0138](0138-remocao-for-c-style.md) | Remove C-style `for (;;)`; keep `for-in`/`while`, targeted migration diagnostic | accepted (breaking; target 2.0) | 2026-11-23 |
| [0139](0139-break-continue.md) | `break`/`continue` without labels: innermost loop, `finally` cleanup, function boundary; keyword budget 27→29 | accepted (implemented) | 2026-11-23 |
| [0140](0140-match-literais.md) | Literal `match` patterns: Int/String/Bool/nil, `_` required outside enums; no Float, guards or structural match | accepted (implemented) | 2026-11-23 |
| [0141](0141-soundness-de-fluxo-do-checker.md) | Checker flow soundness: `break`/`continue` terminate post-loop refinement, `match` forks/joins per arm, jump-aware merges and a flow-policy gate; precision stays with alias/effects/CFG deferred | accepted (implemented; split `TypeOps`/`DeclTable` included) | 2026-11-24 |
| [0142](0142-check-por-fases.md) | `--check` in phases: gradual mode plus checking in `loxia test`/CI, blocking `run` later; type errors stop being optional | accepted (phases 1–3 implemented; no escape) | 2026-11-24 |
| [0143](0143-lsp-didchange-coalescing-e-reuso.md) | LSP `didChange`: coalesce changes with a lazy flush, reuse unchanged module parses by content and build the `SymbolIndex` lazily; diagnostics stay full-file and only the latest version is published | accepted (implemented, #191) | 2026-11-25 |
| [0144](0144-any-dinamico-exige-estreitamento.md) | Dynamic access on `Any` (member get/set, call, index) requires narrowing (`is`/`as`, `E3025`); the backend honors the checker's flow type by unboxing at the use; value operations stay dynamic | accepted (implemented) | 2026-11-25 |
| [0145](0145-campo-any-slot-largo.md) | `Any` fields take two inline words (`{tag, payload}`) with an absolute `slot` next to the bitmap `index`; instance size comes from `word_count()` and the GC-scanned slab keeps the payload rooted | accepted (implemented) | 2026-11-25 |
| [0146](0146-is-as-interface.md) | `is I`/`as I`: runtime check against the descriptor's interface table (own + inherited, kind `J<id>`); a cast from a concrete class that does not implement the interface is a static error; no new tag or ABI; functions and class objects remain in issue #213 | accepted (implemented) | 2026-11-25 |
| [0147](0147-valores-de-funcao-assinatura-runtime.md) | Function values carry a static signature (`min/max` arity, variadic, param/return type trees); `is`/`as fn` compare the actual signature with the target by the checker's subtyping **plus ABI-compatible representations**; no new tag, nested function types supported, natives/class objects out | accepted (implemented) | 2026-11-25 |
| [0148](0148-ponto-de-entrada-main-result.md) | Opt-in entry point: the entry file's top-level `fn main` returning `Result[T, String]` (no params/generics) runs after top-level statements; `Ok` exits 0, `Err(msg)` prints `error[R1016]: msg` and exits 70; modules/REPL never have one, `main -> Nil` stays an ordinary function, near-miss signatures are `E3026` | accepted (implemented) | 2026-11-26 |
| [0149](0149-motores-primarios-thir-e-congelamento.md) | Primary engines: `run` compiles with a content-addressed cache (AOT) and the tree-walk becomes REPL/`--interpret`/oracle; THIR (typed, desugared tree) is the seam between the Python checker and the Loxia engines; a backend-internal control IR (blocks/phi/cleanup) honours ADR-0065; Python is frozen per module at parity+soak gates, the oracle migrates to spec+corpus+golden, and self-host has three levels (self-executing, self-hosted, reproducible) | accepted | 2026-11-26 |


## Next decisions that call for an ADR

Open decisions have an issue labeled `decision`; the ADR is written when the issue closes.

- contracts/DbC — decided as a library in [ADR-0108](0108-contratos-como-biblioteca.md);
  the syntax remains deferred with triggers (issue #14 closes with this ADR);
- `fs.open` streaming — [#16](https://github.com/loxia-lang/loxia/issues/16).

Language decisions still open: `if`/blocks as an expression (recoverable exceptions were decided in
[ADR-0042](0042-excecoes.md) and their policy in [ADR-0135](0135-politica-de-erro.md)),
generic methods/inheritance/reification, constraints in classes and mutable unification.
Deferred items are consolidated in [ADR-0107](0107-adiados-e-nao-objetivos.md); async has a
decided direction, but the implementation is pending ([ADR-0037](0037-async-direcao.md)).

The summary of decisions **already closed** lives in [`../decisoes.md`](../decisoes.md); this
index remains the complete history.

Identity and the feature admission criterion are **no longer** in that queue: they were
decided in [ADR-0014](0014-identidade-e-invariantes.md) (see also
[`../spec/garantias.md`](../spec/garantias.md)).
