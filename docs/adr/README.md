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
  issue. A deferred decision is recorded in [ADR-0107](0107-adiados-e-nao-objetivos.md).

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
| [0088](0088-distribuicao-e-raizes-de-modulo.md) | Distribution: `loxia` command, embedded stdlib and declared module roots | accepted (implementation pending) | 2026-11-15 |
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


## Next decisions that call for an ADR

Open decisions have an issue labeled `decision`; the ADR is written when the issue closes.

- contracts/DbC — decided as a library in [ADR-0108](0108-contratos-como-biblioteca.md);
  the syntax remains deferred with triggers (issue #14 closes with this ADR);
- `fs.open` streaming — [#16](https://github.com/loxia-lang/loxia/issues/16);
- AST generator — [#15](https://github.com/loxia-lang/loxia/issues/15).

Language decisions still open: `if`/blocks as an expression, recoverable exceptions,
generic methods/inheritance/reification, constraints in classes and mutable unification.
Deferred items are consolidated in [ADR-0107](0107-adiados-e-nao-objetivos.md); async has a
decided direction, but the implementation is pending ([ADR-0037](0037-async-direcao.md)).

The summary of decisions **already closed** lives in [`../decisoes.md`](../decisoes.md); this
index remains the complete history.

Identity and the feature admission criterion are **no longer** in that queue: they were
decided in [ADR-0014](0014-identidade-e-invariantes.md) (see also
[`../spec/garantias.md`](../spec/garantias.md)).
