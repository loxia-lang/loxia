# Architecture

How the interpreter is put together internally. For observable behavior, see
[`../spec/`](../spec/); the contribution rules are in
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Pipeline

```
source .lx
   │
   ▼
Scanner ───────────────► list[Token]
   │                       │
   │                       ▼
   │                    Parser ──────────► list[Stmt] (AST)
   │                       │
   │                       ▼
   │                    Resolver ────────► Interpreter.locals: {Expr: depth}
   │                       │                (binding scope errors)
   │                       ▼
   │                    Checker ─────────► type errors (`--check`; `run` checa gradual)
   │                       │
   ▼                       ▼
   └──────────────────► Interpreter ──────► effects (print, variables, objects)

   (path `--emit`)        Checker ─────────► Lowerer ──► llvmlite.ir ──► .o ──► cc
                                                                    └─► `--emit=ll`
```

Each phase depends only on the previous one. The **resolver** is mandatory: without it, the
interpreter does not know the distance of local variables. The **checker** is strict under
`--check` and runs on the normal path in gradual mode (`run` blocks a real type error,
missing annotations are silent); types are erased before execution.

On the backend path (`--emit`, [ADR-0031](../adr/0031-backend-nativo.md)) the checker is
**mandatory**: lowering consumes concrete types. What has no representation yet
(`Float`, `String`, variables, functions, classes, `Any`) fails with an explicit compilation
error — the backend never generates "roughly right" code.

## Modules

Packages by phase (dependency only downward):

| Package | Phase |
| --- | --- |
| [`loxia_core/frontend/`](../../loxia_core/frontend) | lexing → tokens → AST → parser; annotation types (`ty.py`), `ast_printer` (debug) and `ast_json` (oracle, ADR-0129) |
| [`loxia_core/semantics/`](../../loxia_core/semantics) | `resolver` (scopes/`depth`), `flow` (refinamentos, merge e política de fluxo), `type_ops`/`decl_table` (split do ADR-0141) and gradual `checker` |
| [`loxia_core/execution/`](../../loxia_core/execution) | values, environment, objects, natives and `interpreter` |
| [`loxia_core/diagnostics/`](../../loxia_core/diagnostics) | `errors` and `error_reporter` |
| [`loxia_core/loader/`](../../loxia_core/loader) | module loader, manifest, lock and dependency resolution (ADR-0073/0104) |
| [`loxia_core/backend/`](../../loxia_core/backend) | lowering and LLVM emission (opt-in via `--emit`) |

| Module | Responsibility |
| --- | --- |
| [`main.py`](../../main.py) | compatibility shim (`python main.py`) |
| [`loxia_core/bundle.py`](../../loxia_core/bundle.py) | resources shipped with the package: resolves `std/`, `bundled/`, `runtime/` and `native/` in the clone and in the wheel (ADR-0088) |
| [`loxia_core/native_build.py`](../../loxia_core/native_build.py) | builds the Rust regex crate on demand (ADR-0131): finds `cargo`, caches the `cdylib` under `$XDG_CACHE_HOME/loxia`, always `--locked --offline` |
| [`loxia/cli.py`](../../loxia/cli.py) | CLI entry point: picks a subcommand or compatibility mode and dispatches to `HANDLERS` |
| [`loxia/cli_args.py`](../../loxia/cli_args.py) | CLI surface: `COMMANDS`, `build_parser`/`_build_subcommand_parser`, option groups, per-command help and `_validate*` |
| [`loxia/cli_commands.py`](../../loxia/cli_commands.py) | subcommand runners (`run`, `check`, `build`, `fmt`, `doc`, `lock`, `fetch`, `capabilities`, ...), timeout/watch and the `HANDLERS` table |
| [`loxia/engine.py`](../../loxia/engine.py) | `Loxia` engine: parse + modules, resolver, checker, execution, `build` and diagnostic flushing |
| [`loxia/scaffold.py`](../../loxia/scaffold.py) | `loxia new`/`init` (ADR-0106): minimal deterministic template, name normalization, `git init` and empty lock |
| [`loxia/fixer.py`](../../loxia/fixer.py) | `loxia fix`: applies only `safe` fixes, with reparse/check per round (ADR-0093) |
| [`loxia/manifest_edit.py`](../../loxia/manifest_edit.py) | scoped `loxia.toml` editing for `loxia add`/`remove` (ADR-0118) |
| [`loxia/test_selection.py`](../../loxia/test_selection.py) | test selection by change (`--changed`) and by shard (`--shard`) |
| [`loxia/test_runner.py`](../../loxia/test_runner.py) | `loxia test` runner (ADR-0096): discovers `*_test.lx`, one subprocess per file, aggregates TAP and `--json` |
| [`loxia/docgen.py`](../../loxia/docgen.py) | generates Markdown/JSON from the AST based on `///` (ADR-0091), without executing |
| [`loxia/formatter/`](../../loxia/formatter/) | formatter: `doc.py`, `comments.py`, `printer.py` and `engine.py` are the Doc IR pipeline (ADR-0136); `edits.py` turns the result into deterministic `TextEdit[]` for `--diff`/`--edits=json`/LSP; `targets.py` resolves multiple paths/directories and `--exclude` for `loxia fmt` |
| [`loxia/lsp.py`](../../loxia/lsp.py) | LSP (ADR-0090/ADR-0114): JSON-RPC stdio, diagnostics (tags), documentSymbol, hover/definition/references/highlight, typeDefinition/implementation, type hierarchy, completion/signature/inlay hints/formatting/semantic tokens, codeAction/fix-all, rename, file rename imports, workspace/symbol, unsaved module overlays and settings |
| [`loxia/docs_index.py`](../../loxia/docs_index.py) | generated documentation index loader/search (ADR-0111); `loxia/_spec/index.json` is produced by `tools/docs_index.py` |
| [`loxia/mcp.py`](../../loxia/mcp.py) | MCP stdio modern-only (2026-07-28) over the CLI, sandboxed `run`, tools and CLI parity (ADR-0112) |
| [`tools/docs_index.py`](../../tools/docs_index.py) | generates the index and `site/public/llms.txt`; `tools/docs_common.py` shares slugs/URLs with the Starlight generator |
| [`loxia/source_symbols.py`](../../loxia/source_symbols.py) | original-AST symbol resolution for the LSP: imports, members with superclass/interfaces, callable signatures and source type display |
| [`loxia/rename.py`](../../loxia/rename.py) | semantic cross-file rename from the loader-resolved AST: mangled tokens, imports/aliases and type annotations |
| [`loxia/completion.py`](../../loxia/completion.py) | LSP completion over the original AST: scope, imports, modules, `this`/`super`, inherited members, enums and native members |
| [`loxia/symbols.py`](../../loxia/symbols.py) | LSP-1 `SymbolIndex`: declarations, references, checker types and inferred declaration metadata |
| [`loxia/builtins_docs.py`](../../loxia/builtins_docs.py) | English docs for builtins/primitives for `docs/stdlib/builtins.md` |
| [`loxia/__main__.py`](../../loxia/__main__.py) | `python -m loxia` entrypoint |
| [`loxia_core/frontend/scanner.py`](../../loxia_core/frontend/scanner.py) | hand-written lexer; nested `#` and `/* */` comments |
| [`loxia_core/frontend/tokens.py`](../../loxia_core/frontend/tokens.py) | frozen `Token(type, lexeme, literal, line)` |
| [`loxia_core/frontend/token_type.py`](../../loxia_core/frontend/token_type.py) | `TokenType` enum |
| [`loxia_core/frontend/keywords.py`](../../loxia_core/frontend/keywords.py) | lexeme → token map |
| [`loxia_core/frontend/expr.py`](../../loxia_core/frontend/expr.py) | expression nodes + `Visitor` Protocol + `accept` |
| [`loxia_core/frontend/stmt.py`](../../loxia_core/frontend/stmt.py) | statement nodes + `Visitor` Protocol + `accept` |
| [`loxia_core/frontend/parser.py`](../../loxia_core/frontend/parser.py) | recursive descent + recovery; optional `;` at end of line; `elif`, `fn` and `[T]` |
| [`loxia_core/frontend/destructuring.py`](../../loxia_core/frontend/destructuring.py) | destructuring patterns (`val (a, (b, c)) = t`), recursive (ADR-0069) |
| [`loxia_core/frontend/source_index.py`](../../loxia_core/frontend/source_index.py) | index of node/type spans (expressions, declarations, annotations, exact type/declaration names; offset → smallest node; text/line per file) for the LSP, checker and provenance `notes` |
| [`loxia_core/frontend/trivia.py`](../../loxia_core/frontend/trivia.py) | scanner side table for comments/whitespace, normalized round-trip and deterministic attachment (ADR-0134) |
| [`loxia_core/loader/loader.py`](../../loxia_core/loader/loader.py) | module loader (ADR-0073/0100): file = module, folder = namespace, inlining, import cycles and isolation |
| [`loxia_core/loader/manifest.py`](../../loxia_core/loader/manifest.py) | `loxia.toml`: discovery, `[package]` (name/version), `[dependencies]` specs and `[modules].paths` |
| [`loxia_core/loader/lock.py`](../../loxia_core/loader/lock.py) | `loxia.lock` (ADR-0104): strict parse and canonical rendering (sorted, relative posix paths, no timestamp) |
| [`loxia_core/loader/deps.py`](../../loxia_core/loader/deps.py) | dependency resolution: `.lx` tree hash, lock generation, `--frozen` verification, `fetch`, git mirror/checkout cache and `C0002` |
| [`loxia_core/loader/gitenv.py`](../../loxia_core/loader/gitenv.py) | clean environment for the `git` calls Loxia spawns (product and tests) |
| [`loxia_core/backend/llvm_ir.py`](../../loxia_core/backend/llvm_ir.py) | single boundary with `llvmlite` (module, target machine, object file) |
| [`loxia_core/backend/lower.py`](../../loxia_core/backend/lower.py) | lowering coordination: program, statements, expressions, arithmetic and control flow |
| [`loxia_core/backend/lower_model.py`](../../loxia_core/backend/lower_model.py) | types, values, bindings and field/class layouts (ABI from ADR-0048) |
| [`loxia_core/backend/lower_base.py`](../../loxia_core/backend/lower_base.py) | context shared by the lowering mixins |
| [`loxia_core/backend/lower_functions.py`](../../loxia_core/backend/lower_functions.py) | functions, lambdas, capture and closure ABI |
| [`loxia_core/backend/lower_variables.py`](../../loxia_core/backend/lower_variables.py) | slots, cells, assignment and scope |
| [`loxia_core/backend/lower_optionals.py`](../../loxia_core/backend/lower_optionals.py) | `T?`, coercions, unwrap and optional equality |
| [`loxia_core/backend/lower_strings.py`](../../loxia_core/backend/lower_strings.py) | strings, interpolation, `str`/`repr`/`len` and display |
| [`loxia_core/backend/lower_class_layout.py`](../../loxia_core/backend/lower_class_layout.py) | layout planning, fields and constant initializers |
| [`loxia_core/backend/lower_class_codegen.py`](../../loxia_core/backend/lower_class_codegen.py) | descriptor, vtable, constructor (top-level and local), bound methods, `super`, `is`/`as` |
| [`loxia_core/backend/lower_instances.py`](../../loxia_core/backend/lower_instances.py) | field reads/writes, bitmap and `get`/`set` |
| [`loxia_core/backend/lower_calls.py`](../../loxia_core/backend/lower_calls.py) | calls, callable classes, methods and short-circuiting `?.` |
| [`loxia_core/backend/lower_bytes.py`](../../loxia_core/backend/lower_bytes.py) | `Bytes`: method calls, static namespace and `for-in` (ADR-0125) |
| [`loxia_core/backend/lower_containers.py`](../../loxia_core/backend/lower_containers.py) | lists (L6): boxed runtime, literals, index, methods, `len` and equality |
| [`loxia_core/backend/lower_enums.py`](../../loxia_core/backend/lower_enums.py) | enums, `Result` and `match` (L6i, ADR-0061) |
| [`loxia_core/backend/lower_exceptions.py`](../../loxia_core/backend/lower_exceptions.py) | L6j exceptions: try/raise/finally with the setjmp/longjmp ABI (ADR-0062) |
| [`loxia_core/backend/lower_generics.py`](../../loxia_core/backend/lower_generics.py) | monomorphization of generic functions (T7) |
| [`loxia_core/backend/lower_math.py`](../../loxia_core/backend/lower_math.py) | `math.*`, `Int.parse` and `Float.parse` (L6) |
| [`loxia_core/backend/lower_range.py`](../../loxia_core/backend/lower_range.py) | `Range` and `for-in` (L6): runtime pointer, direct iteration lowering |
| [`loxia_core/backend/lower_tuples.py`](../../loxia_core/backend/lower_tuples.py) | tuples (L6): boxed runtime, index, equality, destructuring and `len` |
| [`loxia_core/backend/driver.py`](../../loxia_core/backend/driver.py) | `--emit=ll|obj|exe` and linking with the system `cc` |
| [`runtime/lox_runtime.h`](../../runtime/lox_runtime.h) | types, limits and internal prototypes of the C runtime (one header common to the units) |
| [`runtime/core.c`](../../runtime/core.c) | initialization, Boehm GC, stack, panic and exceptions |
| [`runtime/objects.c`](../../runtime/objects.c) | class/type descriptors, interfaces and the `is`/`as` matcher |
| [`runtime/strings.c`](../../runtime/strings.c) | `LoxStr`, UTF-8, `Float` formatting and `lox_print_*` |
| [`runtime/containers.c`](../../runtime/containers.c) | `Range`, `List`, `Map`, tuple, enum and equality |
| [`runtime/numeric.c`](../../runtime/numeric.c) | guards for `//`/`%`/division, `**`, shifts, `math.*` and parse |
| [`runtime/kernel.c`](../../runtime/kernel.c) | kernel 13.2 (ADR-0071): `args`, `io.*`, `fs.*`, `os.*`, `time.*` |
| [`runtime/proc.c`](../../runtime/proc.c) | processes/streams (ADR-0095): `posix_spawnp`, pipes, `poll(2)` and handles |
| [`runtime/regex.c`](../../runtime/regex.c) | `regex_engine.*` adapters over the Rust ABI (ADR-0131); compiled and linked only when the program uses the primitive |
| [`native/regex/`](../../native/regex) | Rust engine (ADR-0131): `regex` + `fancy-regex`, C ABI in `include/lox_regex.h`, vendored crates and offline builds |
| [`bundled/regex.lx`](../../bundled/regex.lx) | public Lox API over the native module: imported by the short name (`import regex`), reserved and never shadowed by the project (ADR-0126) |
| [`runtime/kernel_gen.h`](../../runtime/kernel_gen.h) | primitive ABI, **generated** from `primitives.py` by `runtime/gen_kernel.py` |
| [`loxia_core/semantics/resolver.py`](../../loxia_core/semantics/resolver.py) | lexical scopes, static validations, `depth` |
| [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py) | execution; `globals`, `environment`, `locals` |
| [`loxia_core/execution/environment.py`](../../loxia_core/execution/environment.py) | chained scopes (`values` + `enclosing`) |
| [`loxia_core/execution/values.py`](../../loxia_core/execution/values.py) | single `stringify` |
| [`loxia_core/execution/numeric.py`](../../loxia_core/execution/numeric.py) | `Int`/`Float`, promotion, wrapping, `//`, `**` and bits |
| [`loxia_core/numeric_bounds.py`](../../loxia_core/numeric_bounds.py) | i64 bounds (`INT_MIN`/`INT_MAX`) shared by the scanner and the numeric model; leaf module (no `loxia_core` imports) |
| [`loxia_core/frontend/ty.py`](../../loxia_core/frontend/ty.py) | types (`Ty`), `TyVar`, `GenericFnTy`, unions, `T?`, `FnTy` and helpers |
| [`loxia_core/semantics/flow.py`](../../loxia_core/semantics/flow.py) | refinement key, state merge, `LoopContext` and the per-node flow policy (ADR-0141) |
| [`loxia_core/semantics/type_ops.py`](../../loxia_core/semantics/type_ops.py) | type algebra: assignment, unification, substitution (ADR-0141) |
| [`loxia_core/semantics/decl_table.py`](../../loxia_core/semantics/decl_table.py) | classes/enums/interfaces registry and hierarchy lookups (ADR-0141) |
| [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py) | gradual static checker (`--check`; flow lives in `flow`, types in `type_ops`) |
| [`loxia_core/execution/type_test.py`](../../loxia_core/execution/type_test.py) | dynamic type test for `x is T` |
| [`loxia_core/execution/lox_range.py`](../../loxia_core/execution/lox_range.py) | lazy `Range` (start, end, step) |
| [`loxia_core/execution/lox_tuple.py`](../../loxia_core/execution/lox_tuple.py) | immutable `LoxTuple` (tuples) |
| [`loxia_core/execution/lox_exception.py`](../../loxia_core/execution/lox_exception.py) | `Exception`/`RuntimeError` and exception values |
| [`loxia_core/execution/lox_list.py`](../../loxia_core/execution/lox_list.py) | mutable `List`: elements, `version`, `push`/`pop`, index |
| [`loxia_core/execution/lox_map.py`](../../loxia_core/execution/lox_map.py) | mutable `Map`: entries, `version`, `get`/`has`/`remove`/`keys`/`values` |
| [`loxia_core/execution/bytes_api.py`](../../loxia_core/execution/bytes_api.py) | `Bytes` signatures and methods (ADR-0125) |
| [`loxia_core/execution/lox_bytes.py`](../../loxia_core/execution/lox_bytes.py) | `Bytes` value and surface in the interpreter (ADR-0125) |
| [`loxia_core/execution/lox_enum.py`](../../loxia_core/execution/lox_enum.py) | enum and variant values (ADR-0041) |
| [`loxia_core/execution/fs_runtime.py`](../../loxia_core/execution/fs_runtime.py) | `fs.open` handles for files (1-based; 0 is never valid) |
| [`loxia_core/execution/proc_runtime.py`](../../loxia_core/execution/proc_runtime.py) | `proc.*` handles: processes and streams (1-based; 0 = failure) |
| [`loxia_core/diagnostics/error_reporter.py`](../../loxia_core/diagnostics/error_reporter.py) | collection/printing of diagnostics |
| [`loxia_core/diagnostics/errors.py`](../../loxia_core/diagnostics/errors.py) | `ParseError`, `LoxRuntimeError`, `NativeError`, `ReturnSignal` |
| [`loxia_core/execution/lox_callable.py`](../../loxia_core/execution/lox_callable.py) | `min_arity`/`max_arity`/`call` Protocol |
| [`loxia_core/execution/prelude.py`](../../loxia_core/execution/prelude.py) | names of reserved global builtins |
| [`loxia_core/execution/lox_function.py`](../../loxia_core/execution/lox_function.py) | user function + closure + `bind` |
| [`loxia_core/execution/lox_class.py`](../../loxia_core/execution/lox_class.py) | class (methods, inheritance, `init`, interfaces) |
| [`loxia_core/execution/lox_interface.py`](../../loxia_core/execution/lox_interface.py) | nominal interface (defaults bound to the environment) |
| [`loxia_core/execution/lox_instance.py`](../../loxia_core/execution/lox_instance.py) | instance (fields + bound methods) |
| [`loxia_core/execution/natives/len.py`](../../loxia_core/execution/natives/len.py) | `len(xs)` / `len(m)` / `len(s)` |
| [`loxia_core/execution/natives/chars.py`](../../loxia_core/execution/natives/chars.py) | `chars`: splits a string into one-code-point strings |
| [`loxia_core/execution/natives/repr.py`](../../loxia_core/execution/natives/repr.py) | `repr(x)` |
| [`loxia_core/execution/natives/range.py`](../../loxia_core/execution/natives/range.py) | `range(a, b, step)` |
| [`loxia_core/execution/natives/str.py`](../../loxia_core/execution/natives/str.py) | `str(x)` |
| [`loxia_core/execution/native_module.py`](../../loxia_core/execution/native_module.py) | read-only native namespace (`Int`, `Float`, `math`) |
| [`loxia_core/execution/natives/parse.py`](../../loxia_core/execution/natives/parse.py) | `Int.parse`/`Float.parse` (`T?`, without crashing) |
| [`loxia_core/execution/natives/math.py`](../../loxia_core/execution/natives/math.py) | deterministic `math.*` (abs/min/max/clamp/floor/ceil/round/trunc/sqrt) |
| [`loxia_core/execution/natives/modules.py`](../../loxia_core/execution/natives/modules.py) | assembly of native namespaces |
| [`loxia_core/frontend/ast_printer.py`](../../loxia_core/frontend/ast_printer.py) | S-expression dump (debug/tests) |
| [`loxia_core/frontend/ast_json.py`](../../loxia_core/frontend/ast_json.py) | versioned AST JSON (tokens + spans + node fields) for the per-file oracle (ADR-0129) |
| [`tools/oracle_snapshot.py`](../../tools/oracle_snapshot.py) | freezes AST/formatter/diagnostics over `std/`, `tests/cases/` and `examples/` (ADR-0129) |

`loxia_core` is a normal package (`__init__.py`). Imports are always absolute and point to
the phase package (`from loxia_core.frontend.expr import Binary`, `from loxia_core.execution.numeric
import wrap_int`). The program runs from the repository root.

### Front-end baseline (2026-11-23)

`make frontend-bench` roda [`tools/frontend_bench.py`](../../tools/frontend_bench.py) sem
subprocesso e sem CI: no corpus de 2026-11-23 (349 arquivos, 320 parseáveis, 62 500 tokens,
2 663 statements), parse ~528 ms e `format_source` ~973 ms (mediana de 5), com pico de
~3,1 MiB no `tracemalloc` para parse+format. O formatter v2 (ADR-0136) constrói Doc IR e
deriva offsets de início com uma caminhada memoizada de primeiro token, sem construir o
`SourceIndex` completo (antes: ~1 267 ms e ~3,7 MiB); é ferramenta offline, não caminho
quente. O port em Lox/nativo tem orçamento próprio (512 MiB/10k chamadas) e será medido na
fase D.

### `SourceIndex` budget (2026-11-24)

`uv run python bench/source_index.py` mede a construção do índice sem subprocesso e sem
CI (issue #130). No corpus de 2026-11-24 (369 arquivos, 338 parseáveis, 31 casos de erro de
sintaxe pulados): **36 827 spans** — 2 928 nomes de tipo, 3 295 nomes de declaração —,
**~625 ms no total**, mediana **0,589 ms/arquivo**, p95 **7,939 ms/arquivo** e
`SourceIndex.at()` a **~13,9 µs/consulta** para os spans de navegação (`name`/`type`).
O custo dos nomes extras é ~41% sobre a caminhada do AST (os nomes de tipo sozinhos são
~0%); o parse fica fora da medição.
O baseline local é [`bench/source_index_baseline.json`](../../bench/source_index_baseline.json)
e a regra é **≤ 2×** o total/mediana ao comparar antes/depois. `at()` continua O(n); o
interval index só entra se o benchmark mostrar regressão — o guard determinístico é
[`tests/test_source_index_budget.py`](../../tests/test_source_index_budget.py), sem timing.

O caminho end-to-end do servidor é medido por
[`bench/lsp.py`](../../bench/lsp.py) (`make bench-lsp`), que sobe `main.py lsp` e mede
startup, didOpen, hover, definition, references (frio/quente), highlight, rename, completion,
documentSymbol, didChange, didChange num arquivo de ~650 linhas e uma rajada de 5 didChange,
com baseline [`bench/lsp_baseline.json`](../../bench/lsp_baseline.json) e tolerância de
**1,5×**. Mediana de 2026-11-25, pós-[ADR-0143](../adr/0143-lsp-didchange-coalescing-e-reuso.md)
(workspace de ~50 arquivos): startup ~92 ms, didOpen ~34 ms, references cross-file ~92 ms
na primeira consulta e ~86 ms após uma edição (o cache do workspace é descartado), ~1,7 ms
no cache quente, didChange ~10 ms, didChange em ~650 linhas ~48 ms e rajada de 5 didChange
~10 ms; as requisições locais ficam abaixo de 2 ms. O orçamento é **≤12 ms** no workspace
do bench e **~0,06 ms/linha** (163 linhas ~20 ms, 323 ~30 ms); acima de ~1000 linhas fica
**fora** até o parse incremental (#113).

O `didChange` coalesce a rajada: uma thread leitora só enfileira mensagens e a thread
principal analisa uma vez quando a fila esvazia ou antes de servir um request, publicando só
a última versão (versões intermediárias podem ser puladas). O parse de módulo é reusado por
conteúdo (`ModuleCache`, LRU de 256 entradas/8 MiB de fonte) e o `SymbolIndex` nasce só na
primeira navegação, como o `SourceIndex`. O piso do arquivo grande é o parse da entrada
(~27 ms) mais a reescrita de imports, que só o parse incremental (#113) muda.

A descoberta usa `os.walk` com poda de diretórios ocultos e `node_modules`, e cache de
leitura por `mtime`/`ctime`/inode/tamanho; o fingerprint do `WorkspaceCache` usa hash (não
guarda uma segunda cópia de todos os textos). Módulos de dependência resolvidos fora do
`root` ainda não entram nesse fingerprint (limitação declarada na #195). O `SourceIndex` é
construído na primeira consulta (`lazy`), então diagnóstico **limpo** e didChange não pagam
a caminhada do AST; um diagnóstico com nota de proveniência constrói o índice. O warm de
~1,7 ms vale para o workspace de ~50 arquivos do bench.

Os nomes de tipo são uma **side table** do parser (`Parser.type_spans` → `Loxia.last_type_spans`
→ `SourceIndex(extra_spans=...)`), como a trivia do ADR-0134: o AST e o JSON v2 não mudam.
`NodeSpan.kind` distingue `node`, `name` e `type`; o LSP só troca o range do token pelo
span exato quando o texto do span é o lexema, então `Foo` em `List[Foo]` nunca vira a
anotação inteira.

## Visitor

`Expr` and `Stmt` are Protocols with an `accept` method. Each node is a
`@dataclass(frozen=True, eq=False)` that calls `visitor.visit_<no>_<expr|stmt>`.

Adding a node requires **five** points:

1. dataclass in `expr.py`/`stmt.py` + method in the `Visitor`;
2. `accept` on the node;
3. parsing;
4. `Interpreter` (semantics) and `Resolver` (scope);
5. `AstPrinter` (debug) + golden case.

Strict `mypy` enforces the Protocol methods; forgetting a step breaks the type check.

## AST identity

Nodes use `eq=False`: equality and hash are **by identity**. The resolver uses the node itself
as the key in `Interpreter.locals`, like the book's identity `HashMap`. With structural
equality, two `a` on the same line (same token) would collide. See
[ADR-0004](../adr/0004-identidade-dos-nos-de-ast.md).

## Environments and resolution

- `Environment` is a linked list (`values: dict[str, object]`, `_mutable: dict[str, bool]`,
  `enclosing`).
- `define(name, value, mutable)` writes to the current scope; `get`/`assign` walk up the chain
  until they find it (globals live in the root environment). `assign`/`assign_at` reject
  immutable bindings.
- The resolver keeps a stack of `dict[str, _VariableInfo]` scopes (`defined`, `mutable`)
  and writes `Interpreter.locals[expr] = distance`. This is where a local/parameter `val`
  becomes a compilation error; globals are left to the `Environment`.
- At runtime, a local variable uses `environment.get_at(distance, name)`; a global uses
  `globals.get`. Assignment likewise with `assign_at`.
- `distance` is counted from the current environment: 0 = current scope.

Consequence: **lexical scope**. A closure reads the variable from the declaration point, not
from the call site.

## Calls and objects

- `LoxCallable` is a `runtime_checkable` `Protocol` with `min_arity()`, `max_arity()` and
  `call(interpreter, args)`. The range covers parameters with defaults.
  `isinstance(x, LoxCallable)` checks that the methods are present.
- `Stmt.Function.params` is a list of `Param(name, mutable, default, type_annotation)`, and
  `Stmt.Var` carries `mutable` and `type_annotation`. Parameters are immutable by default
  (`var` in the parser sets `mutable`).
- `LoxFunction` holds the declaration (`Stmt.Function`) and the `closure`; `call` creates a
  new environment, defines the parameters (filling in constant defaults) and executes the
  body. `bind(instance)` creates an environment with `this` (used by methods and by `super`).
- `LoxClass` holds `superclass`, `methods` and `fields: dict[str, FieldInfo]` (inherited
  fields already merged); `find_method`/`find_field` walk up recursively. `call` creates the
  instance, runs field initializers and `init`, and validates the initialized fields.
- `LoxInstance` has `fields: dict[str, object]` and `_initialized`; `get` looks for a field,
  then a method (and returns the bound method); `set` rejects an undeclared field and a `val`
  that is already initialized.
- `return` uses `ReturnSignal`, an internal exception caught by `LoxFunction.call`.
  It is not a runtime error and must not leak to the user.

## Lists

- `LoxList` wraps `list[object]` and an incremental `version`; `push`/`pop`/`set` change the
  version. `get_method(name)` returns a bound `LoxCallable` (`ListPushMethod`/
  `ListPopMethod`), and the interpreter's `Get` accepts `LoxInstance` or `LoxList`.
- `ListLiteral`, `Index` and `IndexSet` are expression nodes; `Index`/`IndexSet` carry the
  `[` token for diagnostics. `IndexSet` is the target of `xs[i] = v` (the parser turns
  `Index` into `IndexSet` when it sees `=`).
- `for-in` uses `_iterate_list`: it checks `version` before each element and at the end;
  mutation in the middle of the loop becomes a `RuntimeError`.
- `stringify` is recursive with an identity stack (cycle → `[...]`); structural equality
  uses a set of `(id(a), id(b))` pairs.
- Types are erased: `LoxList` does not know about `T`; the `Checker` is what applies `ListTy`,
  invariance and the `push`/`pop`/`len` signatures.

## Maps

- `LoxMap` wraps a `dict[_MapKey, object]` (insertion order) and an incremental `version`.
  `_MapKey` is `(tag, value)` to separate `Bool` from `Int` and restrict keys to
  `String`/`Int`/`Bool`; any other key becomes a `RuntimeError`.
- `MapLiteral(entries, brace)` holds `(key, value)` pairs as expressions; the parser only
  creates this node in expression position (at the start of a statement, `{` is a block). The
  interpreter evaluates key→value, from left to right, and checks `has` before inserting, to
  reject a duplicate key in the literal.
- `Index`/`IndexSet` were already generic: the interpreter dispatches to `LoxList` or
  `LoxMap`. `m.get(k)`/`m.has(k)`/`m.remove(k)`/`m.keys()`/`m.values()` come from
  `get_method` (bound native methods), and `Get` accepts `LoxInstance`, `LoxList` and
  `LoxMap`.
- `for-in` uses `_iterate_map`: snapshot of the keys + `version` check before each key and
  at the end; mutation in the loop becomes a `RuntimeError`.
- Map `stringify` is recursive with the same identity stack as `List` (cycle → `{...}`);
  structural equality is order-independent and uses `b.find(key)` with the same set of
  `(id(a), id(b))` pairs.
- Types are erased at runtime: `LoxMap` does not know about `K`/`V`; the `Checker` applies
  `MapTy`, invariance, the key restriction and the method signatures.

## Signatures and order

- `Checker.check` pre-declares the classes and computes the signatures of **top-level
  functions** before checking the bodies. A function body can call another one declared
  later, including mutual recursion, because the signature is already in the
  `_predeclared_by_name` table.
- The table is only consulted when `_function_depth > 0` (inside a body). Top-level
  statements remain in order: calling a function before its declaration is still an error.
- The signature is computed once and stored per AST node (`_signatures`); `visit_function_stmt`
  reuses the same `FnTy` instead of recomputing it.
- Class methods and fields are not anticipated; they follow the class visit order.
  See [ADR-0020](../adr/0020-assinaturas-explicitas.md).
- Function annotations (`fn(Int) -> Int`) become `FnTy` in the parser and are resolved in
  `_resolve_type`. `_assignable_fn` applies contravariance to parameters and covariance to
  the return; a `ClassObjectTy` is also assignable to the signature of its `init`, so a
  class can be passed as a factory. See [ADR-0021](../adr/0021-tipos-de-funcao.md).
- `_body_always_returns` applies to functions, methods and lambdas: a non-nil return without
  a return path is an error. `visit_return_stmt` rejects `return;` in a non-nil return.
- `_check_field_initialization` runs a simple dataflow (`_init_flow`/`_init_stmt`) over
  `init`: intersection at `if`/`else`, early `return` and conservative loops; every field
  without an initializer must be assigned on all paths.
- `_check_overrides` runs after all classes and compares each method with the superclass
  one via `_assignable` (contravariant in parameters, covariant in the return).
  See [ADR-0023](../adr/0023-soundness-do-checker.md).

## Lambdas

- `Lambda(Expr)` holds `keyword`, `params`, `body` and `return_type`. The parser turns
  `=> expr` into `body = [Return(arrow, expr)]`; a block uses the normal body. The runtime
  does not need to know the difference.
- `LoxFunction` accepts `Function | Lambda`; a lambda is a closure over the environment
  where it was evaluated (`visit_lambda_expr`), and `__str__` returns `<lambda>`.
- The resolver reuses `_resolve_function` for a lambda: it changes `_current_function` to
  `FUNCTION`, but **does not** change `_current_class`; `this`/`super` are still resolved
  in the scope of the method that encloses the lambda.
- The checker uses `_lambda_type`. The expected type (`FnTy`) fills in parameters without an
  annotation; the return is collected by `_check_function_body(..., collect_returns=True)`
  and inferred; the `preserve_class` flag keeps `this`/`super` visible. A parameter without
  context is an error; a mix of non-nil returns requires an annotation.
- `AstPrinter.visit_lambda_expr` prints `(lambda (params) [-> Type] body)`.
  See [ADR-0022](../adr/0022-lambdas.md).

## Generics

- `Function.type_params` holds the `[T, U]` tokens; the parser accepts the block only in
  function declarations, never in a lambda. The dump prints `(fn id[T] ...)`.
- The checker has `FunctionSignature(type_params, type_param_names, fn)`. `_signature`
  creates fresh `TyVar`s (unique `id`), pushes `_type_param_scopes` and resolves
  parameters/return with `_resolve_type`; `T` becomes a `TyVar` instead of a `ClassTy`. The
  body is checked **once** with `_check_function_body(..., type_params=...)`; the type scope
  stays active for annotations and nested lambdas.
- `_lookup` of a generic function returns `GenericFnTy` (parameters + signature), not
  `FnTy`. It is only valid as a callee; `val f = id` and passing `id` as a callback are
  errors.
- `visit_call_expr` delegates to `_infer_call`. If the callee is a `GenericFnTy`,
  `_instantiate_generic` renames the `TyVar`s and `_infer_generic_call`:
  - unifies the return with the expected type (when there is one);
  - checks arguments in order, using `_check_generic_argument` (context for a lambda/
    list/map, unification for the rest);
  - applies the substitutions, requires every `T` to have been inferred and returns the
    concrete type.
- `_unify` covers `TyVar`, `List`, `Map`, `Fn`, unions and concrete cases via
  `_assignable`; `_occurs` rejects `T = List[T]`; `_substitute` applies the map. Without
  constraints, `a + b` on `T` remains an error (`_numeric` does not accept `TyVar`).
- `_check_polymorphic_recursion` rejects `f[T]` calling `f([x])` (it changes the type
  arguments); `f(x)` with the same `T`s is allowed.
- The runtime does not change: `T` is erased; monomorphization is the backend's
  responsibility (ADR-0027). No boxed `LoxValue` in the tree-walk.

## Narrowing

- The checker keeps `_scopes` (declarations) and `_narrowings` (refinements), a parallel
  stack. Each `_narrowings` entry holds `(declaration_scope_index, Ty)`, so an old
  refinement does not leak to a variable redefined in an inner scope.
- `_find_decl` finds the closest declaration; `_lookup` searches for a refinement from the
  innermost level up to the declaration (with a matching index) and falls back to the
  declared type.
- `_refinements(cond, truth)` recognizes `x == nil`, `x != nil`, `if (x)`, `x is T`, `not`,
  and combines `and` (true branch) / `or` (false branch); `_check_branch` pushes a temporary
  level and `_always_returns` decides whether the opposite branch persists after an early
  return. `while` applies the true refinement to the body.
- `x is T` uses `_intersect_types`/`_narrow_to` in the true branch and `_narrow_away` in the
  false one (removes union members fully covered by `T`); `_merge_refinements` combines
  `and`/`or` by intersection.
- `Is` is an expression node (`left`, `test_type`, `operator`); the interpreter calls
  `matches_type`, which lives in `loxia_core/execution/type_test.py` and covers primitives, classes/subclasses,
  `List[T]`/`Map[K, V]` (recursive) and unions. The runtime does not gain a general type
  system; `matches_type` exists only for `is`.
- `_invalidate` removes the name from all active levels when there is an assignment. It is
  conservative: losing a refinement is safe; keeping an invalid refinement would not be.
- The runtime does not participate; `T?` remains erased.

## Interpolation

- `Scanner._string` recognizes `${` and delegates the expression to
  `_scan_expression_tokens`, which scans into its own token buffer, counts inner braces
  (map/block) and ignores strings/comments. The `INTERPOLATED_STRING` token holds
  `list[str | list[Token]]`.
- `Parser._interpolated_string` creates a sub-`Parser` per buffer and calls
  `parse_expression`; the result is `InterpolatedString(parts, token)`, with text chunks and
  expression nodes.
- `Interpreter.visit_interpolated_expr` evaluates each expression from left to right and
  concatenates with `stringify`; `Checker` infers each part and returns `String`; `Resolver`
  resolves the subexpressions.
- `\$` and `\${` are text escapes; `$` without `{` is literal. The AST printer shows
  `(interp "texto" expr ...)`.

## Builtins and shadowing

- `Interpreter.__init__` defines `len`, `range`, `repr`, `str`, `Int`, `Float` and `math`
  with `mutable=False`; `_reject_immutable_redeclaration` rejects redefinition in the
  global scope. `clock` was removed from 1.0 ([ADR-0026](../adr/0026-freeze-1.0.md)); it can
  be an ordinary name.
- `Int`/`Float`/`math` are `NativeModule`s (read-only namespaces), not instantiable
  classes. The checker associates each name with `NativeModuleTy(name)` and resolves members
  in `_native_modules`; the interpreter resolves `visit_get_expr` to the member.
- `as` is an `As(left, target_type, operator)` node in the parser (between `factor` and
  `unary`); the checker validates targets/`Any` and the interpreter converts/checks at
  runtime ([ADR-0029](../adr/0029-conversoes-math.md)).
- The checker has the same list in `loxia_core/execution/prelude.py::BUILTIN_NAMES`: `_define`
  reports `Can't redefine builtin 'x'.` when the scope is the global one; `visit_class_stmt`
  does its own check because classes are pre-declared.
- Local scopes (parameter, block, `for`) can shadow the name normally; the existing lexical
  resolution takes care of the rest.

## Diagnostics

- One `ErrorReporter` per execution, created in `Lox.run` and injected into the scanner,
  parser, resolver and interpreter (see
  [ADR-0003](../adr/0003-diagnosticos-por-execucao.md)).
- Syntax/scope: `reporter.error(token, message)`; the parser recovers and the resolver
  continues. Runtime: `raise LoxRuntimeError` and `interpret` catches it.
- Exit codes: 65 (compilation), 70 (runtime), 66 (file).
- Structured diagnostics ([ADR-0075](../adr/0075-diagnosticos-estruturados.md)):
  `Diagnostic` with code, phase, span, `labels`/`notes`/`help` and `trace`;
  `human`/`short`/`json` renderers; `--error-format`, `--color` and `--max-errors` flags.
  The token carries the source file, so a compilation error in a module points to the
  module.
- Runtime stack trace ([ADR-0089](../adr/0089-stack-trace-de-runtime.md)): the
  `Interpreter` keeps `_frames` and freezes the trace at the innermost `except`; the binary
  keeps `lox_frames` and the call site in three globals read by `lox_stack_enter`. Format,
  clipping and `R1015` are identical in both engines (I1).

## REPL

`main.Lox.run_prompt` reads one line at a time and calls `run_repl`:

1. `Parser(..., repl=True)` tries a pure expression and, if the whole line is an expression,
   wraps it in `Print` (that is why `1 + 1` shows `2`);
2. otherwise, it parses statements normally;
3. the resolver runs on every line, but the `Environment` and `Interpreter.locals` persist —
   functions/classes defined earlier remain valid;
4. the `ErrorReporter` is reset at the start of each `run`.

The `;` is optional at the end of the line/EOF in any execution (`_end_statement`); it is only
mandatory when there is another statement on the same line.

## Native backend (L0–L6 + T7)

The IR is intentionally small: `Int` is `i64`, `Float` is `double`, `Bool` is `i1`, `nil`
has no value (it only affects `print`). `+ - *` become instructions (with `sitofp` in the
`Int → Float` promotion); `if`/`while` become blocks with `br`/`cbranch`. `//`, `%`, `/` and
Float's `%` call the runtime: `INT_MIN / -1` is UB in LLVM (`idiv` traps on x86) and division
by zero is a fatal error in the interpreter. Those cases become `lox_panic`, which reproduces
stderr and exits with 70. Since ADR-0075, `lox_panic(line, column, code, message)` prints the
same compilation diagnostic header (`file:line:col: error[CODE]:`), without the caret; the
display path (relative, never absolute) is pinned in `lox_init`.

Printed `Float` uses the shortest representation that reconstructs the same bit pattern, with
Python's `repr` conventions (`1.0`, `-0.0`, `1e-05`, `1e+16`); `lox_init` pins
`LC_NUMERIC=C` so it does not depend on the locale (I3). Parity is policed by fuzzing against
`repr()` in `tests/test_backend.py`.

Variables use `alloca` (locals) and LLVM globals (top level); the resolver's `depth` decides
the scope (`depths`), and the slot type is the type of the **value** at runtime, not the
annotation's — as in the interpreter, `val f: Float = 2` stores an `Int`. Variables captured
by closures become **cells** on the collected heap (`{ value }`) and are referenced by
pointer; the others remain in `alloca`.

User functions have the ABI `(i8* env, params...)`; a closure is `{ fnptr, env, display }`
allocated on the collected heap. Top-level functions have their signature pre-declared
(mutual recursion), but the global binding is only initialized when the statement runs —
using it earlier becomes `lox_panic` with `Undefined variable`, as in the interpreter. The
[`loxia_core/backend/captures.py`](../../loxia_core/backend/captures.py) pass decides what
each function captures and what becomes a cell
([ADR-0046](../adr/0046-closures-celulas-l4.md)); local functions, lambdas with a concrete
type and indirect calls use the same closure.

Direct calls still fill defaults at the call site; a function with defaults as a **value** is
rejected with exit 65 in L4. `return` and arguments must match (no implicit coercion) and
`Nil` becomes `void`. Wrong arity becomes `lox_panic` with the message assembled at compile
time (the numbers are static), and the body runs in its own blocks with
`ret`/`unreachable`.

The L6 spike represents `Any` and scalar unions as `{i64 tag, i64 payload}`, with
`lox_print_any`; it is a 16-byte box only on the dynamic path (ADR-0049).

L5 uses a single method ABI `(i8* env, i8* this, params...)`, a vtable of closures, a class
descriptor `{super, id, name, vtable, n_fields, init, init_min, init_max}` and an instance
`{classe, bitmap, slots i64}`; bound methods are thunks. Inheritance copies the vtable,
prefixes the fields and resolves `super` through the class where the method was declared
([ADR-0048](../adr/0048-abi-classes-l5.md)). `String?`/instance `T?` use a null pointer;
class `is`/`as` and empty local classes work. `?.` with an optional receiver already works;
general local classes and `nil_aware` (union/`Any`) stay in L6.

`String` is `{byte_len, cp_len, flat, cp_offsets, hash, left, right}`; literals become
constant globals (UTF-8 bytes + header), concatenation allocates a rope node on the collected
heap (Boehm GC,
[ADR-0074](../adr/0074-gc-boehm-e-contrato-de-memoria.md)) and `len` returns `cp_len` (code
points). `lox_str_bytes` flattens a rope on first observation and caches the buffer;
equality is `memcmp` of the flat bytes and `print` is an `fwrite`. Interpolation concatenates the parts,
converting scalars with `lox_str_from_int/double/bool` and `lox_str_nil`; `repr` quotes and
escapes with `lox_str_quote`.

`List` escolhe o armazenamento no lowering: quando a anotação (ou o tipo publicado pelo
checker) declara `Int`/`Float`/`Bool`/`String`, o literal cria uma lista tipada (um i64 por elemento, buffer atômico exceto para ponteiros);
o runtime promove para `LoxValue` boxeado no primeiro push de tag diferente. `Map` mantém as
entradas em ordem de inserção e um índice open-addressing para lookup O(1).

The generated `main` returns `0` on success; success/failure is never the return value of a
user function. Before emitting `.ll`, `.o` or an executable, the driver runs the LLVM
verifier (`mod.verify`); invalid IR becomes a `BackendError` (exit 65), never a binary.
`--emit=ll` is an inspection artifact: the build emits an object file with the same LLVM that
built the module and links it with `cc`, without depending on the system LLVM version.

The runtime is split by domain into seven units (`core`, `objects`, `strings`, `containers`,
`numeric`, `kernel`, `proc`) with a common header. They are compiled once per (content of
**all** sources and headers, compiler, version, flags and `CPATH`) and the `.o` files live in
`$TMPDIR/loxia-build-<uid>/runtime-<key>/`; `LOX_BUILD_CACHE=<dir>` isolates the cache.
Subsequent builds reuse the objects and pay only for linking. The cache is only about performance:
it does not change generated bytes, does not enter the output, and error paths are sanitized
to `<build>`.

`loxia test --native` adds a second, content-addressed cache for the test executables. The
key covers the project's `.lx` files, the embedded `loxia`/`loxia_core` sources, the compiler
identity and version, the dependency flags, platform and `CPATH`/`LIBRARY_PATH`; the binary
lives in `$TMPDIR/loxia-build-<uid>/tests-<key>/`. A hit skips compilation entirely; a miss
builds to a temporary file and publishes it with `os.replace`, so concurrent runs cannot see
a partial binary. `--no-cache` keeps the old per-run build. As with the runtime objects, a
cache failure falls back to the temporary build directory and never changes the result.

The runtime navigation map — owner of each symbol, `LoxValue` tags, layouts, recipes (adding
a primitive, debugging divergence) and known pitfalls — is in
[`runtime/README.md`](../../runtime/README.md). The top comments of each `.c` repeat the
essentials for anyone who opens the file directly.

`runtime/kernel_gen.h` is generated from the `primitives.py` table (`make primitives`,
`runtime/gen_kernel.py`) and included by `kernel.c`: divergent table and C definition break
the compilation, not the test. `tests/test_primitives_gen.py` polices the freshness of the
generated file.

The table also carries the **budget**
([ADR-0123](../adr/0123-orcamento-do-kernel-por-grupo.md)): a primitive's group is its
namespace (`io.*`, `fs.*`, `process.*` → `proc`) or `core` when there is no prefix.
`GROUP_BUDGET` caps each group and `KERNEL_BUDGET` caps the total (core 5, io 8, fs 11,
os 2, proc 10, time 2, digest 2; total 40). `tests/test_primitives.py` fails when a group
or the total overflows, and `loxia capabilities --json` publishes the table with the group
and the budget. Native modules keep their own `NATIVE_MODULE_BUDGET`, outside the 40
([ADR-0126](../adr/0126-modulo-nativo-embutido-sqlite.md)).

Each primitive also carries its **layer** ([ADR-0128](../adr/0128-contrato-de-motores.md)),
derived from two independent axes: `ambient` (determinism) and `native_only` (engine). The
label is a projection (`native-only` > `ambient` > `core`). A native-only capability is
refused by the interpreter **before execution**: `loxia/engine.py` runs
`loxia_core/semantics/layers.py` after the resolver and reports `E3021` at the call site
(exit 65). `PrimitiveCallable.call` keeps a runtime backstop with the same message for the
case an alias or shadowing hides the call from the static pass. `loxia check` stays
engine-agnostic; `build` only refuses the backend gap (`E4001`, I4).

The differential test (`tests/test_backend.py`) compiles, runs and compares stdout, stderr
and exit code with the interpreter — the oracle is always the tree-walk.

## Known limitations

- No stack trace on a **caught** exception (the value does not carry frames) and no suspended
  async frames; position, code, JSON and trace of the uncaught error exist
  ([ADR-0075](../adr/0075-diagnosticos-estruturados.md),
  [ADR-0089](../adr/0089-stack-trace-de-runtime.md)).
- `Int` (i64) and `Float` (f64) separate; `/` always `Float`, `%` truncated, `Int` with
  wrapping — see [ADR-0006](../adr/0006-int-float-separados.md).
- Recursion limited to 10,000 Lox calls (R1015, catchable) in both engines; no tail call.
  R1015 has a position and the trace shows the active frames
  ([ADR-0077](../adr/0077-limite-de-pilha.md),
  [ADR-0089](../adr/0089-stack-trace-de-runtime.md)).
- In the tree-walk, no GC of its own: objects are collected by Python. In the backend,
  conservative Boehm GC, default hard cap of 512 MiB (`--max-heap` at build) and I1 up to
  64 MiB of live memory ([ADR-0074](../adr/0074-gc-boehm-e-contrato-de-memoria.md),
  [ADR-0087](../adr/0087-heap-cap-e-self-hosting.md)).
- No bytecode/VM: the target is LLVM, and the tree-walk is the oracle (ADR-0002).
- Optional `;` is decided in the parser, not by insertion in the scanner; an operator at the
  start of the line does not continue the expression (ADR-0011).

## Tests and benchmark

- `tests/` — pytest + `.lx` golden cases; see the
  [`lox-testing`](../../.dsh/skills/lox-testing/SKILL.md) skill.
- `tests/official/` — official Crafting Interpreters suite (chapters 10–13), adapted by
  `tests/test_official_suite.py`; 112 pass, 8 are documented `xfail`s.
- `bench/` — performance harness with a baseline; see AGENTS §6.
