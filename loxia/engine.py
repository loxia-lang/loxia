# SPDX-License-Identifier: MIT OR Apache-2.0
"""Engine de uma execução do CLI: parse + módulos, resolver, checker e interpretador.

Uma instância `Loxia` é uma **sessão** (um `ErrorReporter`, um `SourceMap`, um
`Interpreter`). O argparse mora em `loxia.cli_args`, os runners em `loxia.cli_commands` e o
dispatch em `loxia.cli`; o LSP, o fixer, o rename e os benchmarks reutilizam esta engine
diretamente (por isso a API pública `use_file`/`check`/`build`).
"""

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loxia import __version__
from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.diagnostic import DiagnosticBatch
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.render import (
    SCHEMA_VERSION,
    diagnostic_json,
    render_batch,
    render_json,
)
from loxia_core.diagnostics.source import SourceMap, display_path
from loxia_core.execution.interpreter import Interpreter
from loxia_core.frontend.ast_json import dumps as ast_dumps
from loxia_core.frontend.ast_json import program_payload
from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.source_index import SourceIndex
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.trivia import Trivia
from loxia_core.frontend.ty import Ty, display
from loxia_core.loader.deps import DependencyError, resolve_dependencies
from loxia_core.loader.lock import LOCK_NAME, LockError, read_lock
from loxia_core.loader.manifest import (
    Manifest,
    ManifestError,
    discover_manifest,
    parse_manifest,
)
from loxia_core.native_build import TOOLCHAIN_MESSAGE, cargo_binary
from loxia_core.semantics.checker import Checker
from loxia_core.semantics.decl_table import DeclTable
from loxia_core.semantics.layers import REGEX_PRIMITIVES, named_uses, native_only_uses
from loxia_core.semantics.resolver import Resolver

if TYPE_CHECKING:
    from loxia_core.backend.driver import Emit

# Comandos de inspeção: o JSON vai para stdout (não há saída de programa). `build` e
# `run` podem escrever IR/programa em stdout, então o JSON deles vai para stderr.
JSON_ON_STDOUT = frozenset({"check"})


def manifest_token(path: Path, line: int = 1, column: int = 1) -> Token:
    """Token sintético para ancorar erro de `loxia.toml` (arquivo/linha reais)."""
    return Token(
        TokenType.IDENTIFIER,
        path.name,
        None,
        line,
        column,
        0,
        file=display_path(path),
    )


# No REPL o check é por snippet: nomes e anotações de linhas anteriores não existem.
_REPL_QUIET = frozenset({Code.UNDEFINED_NAME, Code.MISSING_ANNOTATION})


def _declared_globals(statements: list[Stmt]) -> set[str]:
    """Nomes declarados no snippet: o seed antigo deles não deve disparar redeclaração."""
    names: set[str] = set()
    for statement in statements:
        lexeme = getattr(getattr(statement, "name", None), "lexeme", None)
        if isinstance(lexeme, str):
            names.add(lexeme)
    return names


class Loxia:
    def __init__(
        self,
        *,
        debug: bool = False,
        error_format: str = "human",
        color: str = "auto",
        max_errors: int = 20,
        script_args: list[str] | None = None,
        json_lines: bool = False,
        werror: bool = False,
        module_paths: list[str] | None = None,
        frozen: bool = False,
        offline: bool = False,
        cache_dir: str | None = None,
        sandbox: bool = False,
        gradual: bool = False,
        check_on_run: bool = True,
    ) -> None:
        self.reporter = ErrorReporter(max_errors=max_errors, werror=werror)
        self.debug = debug
        self.interpreter = Interpreter(
            self.reporter,
            checked_overflow=debug,
            argv=script_args,
            sandbox=sandbox,
        )
        self.error_format = error_format
        self.color = color
        self.json_lines = json_lines
        self.frozen = frozen
        self.offline = offline
        self.cache_dir = Path(cache_dir).resolve() if cache_dir is not None else None
        self.gradual = gradual
        self._check_on_run = check_on_run
        # Estado consultivo da sessão REPL: o check de cada snippet enxerga o anterior.
        self._repl_decls = DeclTable()
        self._repl_globals: dict[str, Ty] = {}
        self._repl_alias_targets: dict[str, Ty] = {}
        self._repl_alias_resolved: dict[str, Ty] = {}
        self._sources = SourceMap()
        self._file = "<stdin>"
        self._module_root: Path | None = None
        self._module_paths: tuple[Path, ...] = tuple(
            Path(path).resolve() for path in (module_paths or ())
        )
        self._watched_files: set[Path] = set()
        self._module_files: dict[str, Path] = {}
        self._warn_unused_imports = False
        self._jsonl_started = False
        self._revision = 0
        # Estado da última análise, consumido pelo LSP (hover/definition).
        self.last_statements: list[Stmt] | None = None
        # Tokens do último parse (entrada, não módulos). Só o oráculo da AST
        # (`--file-only --format=json`) consome (ADR-0129).
        self.last_tokens: list[Token] | None = None
        # Comentários/espaços do último parse; o formatter/LSP consome (ADR-0134).
        self.last_trivia: list[Trivia] = []
        # Statements recuperados pelo parser quando há erro de sintaxe: só tooling
        # (LSP) consome; `run`/`check` continuam estritos (ADR-0113).
        self.last_recovered_statements: list[Stmt] | None = None
        self.last_source_index: SourceIndex | None = None
        self.last_resolver: Resolver | None = None
        self.last_checker: Checker | None = None

    # -- pipeline --------------------------------------------------------

    def use_file(self, file: str, *, module_root: Path | None = None) -> None:
        """Aponta a sessão para um arquivo (nome de exibição e raiz de módulos).

        API pública para quem reutiliza a engine sem argparse (fixer, rename, LSP):
        evita escrever em `_file`/`_module_root` de fora do módulo.
        """
        self._file = file
        if module_root is not None:
            self._module_root = module_root

    def _parse(
        self,
        source: str,
        *,
        repl: bool = False,
        module_overrides: dict[Path, str] | None = None,
        file_only: bool = False,
    ) -> list[Stmt] | None:
        self.reporter.reset()
        self.reporter.file = self._file
        self._sources.add(self._file, source)
        self._watched_files = set()
        self._module_files = {}

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        self.last_tokens = tokens
        self.last_trivia = scanner.trivia
        parser = Parser(tokens, repl=repl, reporter=self.reporter)
        statements = parser.parse_repl() if repl else parser.parse()
        self.last_recovered_statements = statements

        if self.reporter.had_error or statements is None:
            self.last_statements = None
            return None

        if not file_only and self._module_root is not None:
            from loxia_core.loader.loader import ModuleLoader

            manifest = None
            dependencies: dict[str, Path] = {}
            lock_path: Path | None = None
            manifest_path = discover_manifest(self._module_root)
            project_root = self._module_root
            if manifest_path is None and self.frozen:
                self.dependency_error(
                    Path(self._file),
                    "--frozen requires a loxia.toml.",
                )
                return None
            if manifest_path is not None:
                manifest = self._load_manifest(manifest_path)
                if manifest is None:
                    return None
                project_root = manifest.path.parent
                lock_path = manifest.path.parent / LOCK_NAME
                try:
                    lock = read_lock(lock_path)
                    dependencies = resolve_dependencies(
                        manifest,
                        lock=lock,
                        frozen=self.frozen,
                        offline=self.offline,
                        cache_dir=self.cache_dir,
                    )
                except LockError as error:
                    self.dependency_error(
                        lock_path,
                        error.message,
                        line=error.line,
                        column=error.column,
                    )
                    return None
                except DependencyError as error:
                    self.dependency_error(manifest_path, error.message)
                    return None
                if lock is not None:
                    self._watched_files.add(lock_path)
            loader = ModuleLoader(
                self.reporter,
                self._sources,
                project_root,
                manifest=manifest,
                module_paths=self._module_paths,
                dependencies=dependencies,
                overrides=module_overrides,
            )
            loaded = loader.load(
                statements,
                self._file,
                warn_unused=self._warn_unused_imports,
            )
            if loaded is None:
                return None
            self._watched_files = {module.path for module in loader.modules.values()}
            self._module_files = {
                ModuleLoader.display_path(name): module.path
                for name, module in loader.modules.items()
            }
            if manifest_path is not None:
                self._watched_files.add(manifest_path)
            statements = loaded

        self.last_statements = statements
        self.last_source_index = SourceIndex(statements, source, sources=self._sources)
        return statements

    def _load_manifest(self, path: Path) -> Manifest | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            self.reporter.error(
                manifest_token(path),
                "Can't read manifest.",
                code=Code.SYNTAX_UNEXPECTED,
            )
            return None
        self._sources.add(display_path(path), text)
        try:
            return parse_manifest(path, text)
        except ManifestError as error:
            self.reporter.error(
                manifest_token(path, error.line, error.column),
                error.message,
                code=Code.SYNTAX_UNEXPECTED,
            )
            return None

    def dependency_error(
        self,
        path: Path,
        message: str,
        *,
        line: int = 1,
        column: int = 1,
    ) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            pass
        else:
            self._sources.add(display_path(path), text)
        self.reporter.error(
            manifest_token(path, line, column),
            message,
            code=Code.DEPENDENCY_STATE,
        )

    def _execute(self, statements: list[Stmt], *, repl: bool = False) -> None:
        # Em run não há warnings: o binário não os emite e o I1 compara stderr.
        resolver = Resolver(self.interpreter, self.reporter, warn_unused=False)
        resolver.resolve(statements)

        if self.reporter.had_error:
            return

        if self._check_on_run and repl:
            self._repl_check(statements, resolver)

        # ADR-0128: o interpretador recusa capacidade native-only antes de executar.
        for use in native_only_uses(statements, self.interpreter.locals):
            self.reporter.error(
                use.token,
                f"`{use.name}` is not supported by the interpreter; build with `--emit=exe`.",
                code=Code.INTERPRETER_UNSUPPORTED,
            )

        if self.reporter.had_error:
            return

        # ADR-0131: regex exige o toolchain Rust; a recusa é antes de executar.
        if cargo_binary() is None:
            for use in named_uses(statements, self.interpreter.locals, REGEX_PRIMITIVES):
                self.reporter.error(use.token, TOOLCHAIN_MESSAGE, code=Code.TOOLCHAIN_MISSING)
                break

        if self.reporter.had_error:
            return

        if self._check_on_run and not repl:
            self._run_check(statements, resolver)
            if self.reporter.had_fatal_error:
                return

        self.interpreter.interpret(statements)

    def _run_check(self, statements: list[Stmt], resolver: Resolver) -> None:
        """Checa antes de executar (ADR-0142, fase 2).

        Gradual e silencioso para anotação ausente. Erro que o interpretador também
        levantaria (`lowerable`) é adiado e vira `Rxxxx` no runtime, preservando a
        mensagem e o exit 70; só o erro que o runtime não pega bloqueia (exit 65).
        """
        self.reporter.defer_lowerable = True
        try:
            checker = Checker(
                self.reporter,
                captured_mutables=resolver.captured_mutables,
                captured_globals=resolver.captured_global_names,
                source_index=self.last_source_index,
                gradual=True,
                warn_missing=False,
            )
            checker.check(statements)
        finally:
            self.reporter.defer_lowerable = False
        self.last_checker = checker
        if not self.reporter.had_fatal_error:
            self.reporter.release_deferred()

    def _repl_check(self, statements: list[Stmt], resolver: Resolver) -> None:
        """No REPL o check só avisa: nunca bloqueia um snippet (ADR-0142).

        A sessão lembra declarações, globais e aliases dos snippets anteriores; sem isso
        `p.m()`/`x + 1`/`val b: A` viravam aviso falso porque o checker era recriado do zero.
        """
        declared = _declared_globals(statements)
        seed = {name: ty for name, ty in self._repl_globals.items() if name not in declared}
        # O REPL só avisa (ADR-0142): `-Werror` não bloqueia um snippet interativo.
        advisory = ErrorReporter(max_errors=self.reporter.max_errors)
        advisory.file = self._file
        checker = Checker(
            advisory,
            captured_mutables=resolver.captured_mutables,
            captured_globals=resolver.captured_global_names,
            source_index=self.last_source_index,
            gradual=True,
            warn_only=True,
            decls=self._repl_decls,
            seed_globals=seed,
            alias_targets=self._repl_alias_targets,
            alias_resolved=self._repl_alias_resolved,
        )
        checker.check(statements)
        self._repl_globals = checker.global_scope
        self._repl_alias_targets = checker.alias_targets
        self._repl_alias_resolved = checker.alias_resolved
        diagnostics = tuple(
            item for item in advisory.batch().diagnostics if item.code not in _REPL_QUIET
        )
        if diagnostics:
            self.reporter.adopt(diagnostics)

    # -- comandos --------------------------------------------------------

    def run(self, source: str) -> None:
        statements = self._parse(source)
        if statements is not None:
            self._execute(statements)

        self.flush("run", exit_code=self._exit_code())

    def run_repl(self, source: str) -> None:
        self._file = "<repl>"
        statements = self._parse(source, repl=True)
        if statements is not None:
            self._execute(statements, repl=True)

        self.flush("repl", exit_code=self._exit_code())

    def parse_file(
        self,
        source: str,
        *,
        allow_errors: bool = False,
    ) -> tuple[list[Token], list[Stmt]] | None:
        """Parse de **um arquivo**, sem loader e sem mangling (ADR-0129).

        Devolve tokens e statements na ordem do fonte; `None` quando há erro e
        `allow_errors` é falso. Com `allow_errors`, devolve a árvore recuperada (com
        `ErrorStmt`/`ErrorExpr`), mas o reporter continua com erro e o CLI sai 65.
        """
        statements = self._parse(source, file_only=True)
        tokens = self.last_tokens
        if tokens is None:
            return None
        if statements is not None:
            return tokens, statements
        if allow_errors and self.last_recovered_statements is not None:
            return tokens, self.last_recovered_statements
        return None

    def dump_ast(
        self,
        source: str,
        *,
        file_only: bool = False,
        output_format: str = "sexp",
        allow_errors: bool = False,
        typed: bool = False,
    ) -> None:
        if output_format not in {"sexp", "json"}:
            raise ValueError(f"unknown AST format: {output_format}")
        if output_format == "json" and not file_only:
            raise ValueError("AST JSON requires file_only parsing")
        if typed and output_format != "json":
            raise ValueError("typed AST requires JSON output")

        if typed:
            # `--typed` continua sendo o contrato por arquivo: nunca passa pelo loader.
            statements = self._parse(source, file_only=True)
            tokens = self.last_tokens or []
            trivia = self.last_trivia
            if statements is None:
                self.flush("ast", exit_code=self._exit_code())
                return
            self._check_parsed(statements)
            exit_code = self._exit_code()
            if exit_code == 0:
                payload = program_payload(
                    statements,
                    tokens,
                    display_path(self._file),
                    trivia=trivia,
                    typed=self._typed_expressions(source),
                )
                sys.stdout.write(ast_dumps(payload))
                sys.stdout.flush()
            self.flush("ast", exit_code=exit_code)
            return

        statements = self._parse(source, file_only=file_only)
        if statements is None and allow_errors:
            statements = self.last_recovered_statements
        if statements is not None:
            if output_format == "json":
                tokens = self.last_tokens or []
                payload = program_payload(
                    statements,
                    tokens,
                    display_path(self._file),
                    trivia=self.last_trivia,
                )
                sys.stdout.write(ast_dumps(payload))
                sys.stdout.flush()
            else:
                print(AstPrinter().print_program(statements))

        self.flush("ast", exit_code=self._exit_code())

    def _check_parsed(self, statements: list[Stmt]) -> None:
        """Resolve/check uma árvore já parseada, sem loader (ADR-0129)."""
        self.last_resolver = None
        self.last_checker = None
        resolver = Resolver(self.interpreter, self.reporter)
        resolver.resolve(statements)
        self.last_resolver = resolver
        if not self.reporter.had_error:
            checker = Checker(
                self.reporter,
                captured_mutables=resolver.captured_mutables,
                captured_globals=resolver.captured_global_names,
                source_index=self.last_source_index,
            )
            checker.check(statements)
            self.last_checker = checker

    def _typed_expressions(self, source: str) -> list[dict[str, object]]:
        checker = self.last_checker
        index = self.last_source_index
        if checker is None or index is None:
            return []
        entries: list[tuple[int, int, str]] = []
        for expression, ty in checker.types.items():
            span = index.span_of(expression)
            if span is None:
                continue
            entries.append((span.start, span.end, display(ty)))
        entries.sort()
        data = source.encode("utf-8")
        result: list[dict[str, object]] = []
        for start, end, type_text in entries:
            start_text = data[:start].decode("utf-8")
            end_text = data[:end].decode("utf-8")
            start_line = start_text.count("\n") + 1
            end_line = end_text.count("\n") + 1
            start_column = len(start_text.rsplit("\n", 1)[-1]) + 1
            end_column = len(end_text.rsplit("\n", 1)[-1]) + 1
            result.append(
                {
                    "span": {
                        "start": {"line": start_line, "column": start_column, "offset": start},
                        "end": {"line": end_line, "column": end_column, "offset": end},
                    },
                    "type": type_text,
                }
            )
        return result

    def document(self, source: str, *, json_output: bool = False) -> bool:
        """Gera a referência de um arquivo a partir de `///` (não executa)."""
        from loxia import docgen

        self.reporter.reset()
        self.reporter.file = self._file
        self._sources.add(self._file, source)

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens, reporter=self.reporter)
        statements = parser.parse()
        if self.reporter.had_error or statements is None:
            self.flush("doc", exit_code=65, always=True)
            return False

        symbols = docgen.extract(statements)
        if json_output:
            text = docgen.render_json(self._file, symbols)
        else:
            text = docgen.render_markdown(self._file, symbols)
        sys.stdout.write(text)
        sys.stdout.flush()
        return True

    def check(
        self,
        source: str,
        *,
        emit: bool = True,
        module_overrides: dict[Path, str] | None = None,
        defer_lowerable: bool = False,
    ) -> int:
        self.last_resolver = None
        self.last_checker = None
        self._warn_unused_imports = True
        try:
            statements = self._parse(source, module_overrides=module_overrides)
        finally:
            self._warn_unused_imports = False
        if statements is not None:
            resolver = Resolver(self.interpreter, self.reporter)
            resolver.resolve(statements)
            self.last_resolver = resolver
            self.last_checker = None
            if not self.reporter.had_error:
                self.reporter.defer_lowerable = defer_lowerable
                try:
                    checker = Checker(
                        self.reporter,
                        captured_mutables=resolver.captured_mutables,
                        captured_globals=resolver.captured_global_names,
                        source_index=self.last_source_index,
                        gradual=self.gradual,
                    )
                    checker.check(statements)
                    self.last_checker = checker
                finally:
                    self.reporter.defer_lowerable = False
                if defer_lowerable and not self.reporter.had_fatal_error:
                    self.reporter.release_deferred()

        exit_code = self._exit_code()
        if emit:
            self.flush("check", exit_code=exit_code, always=True)
        return exit_code

    def build(
        self,
        source: str,
        *,
        emit: str,
        output: Path | None,
        stem: str,
        max_heap: int | None = None,
    ) -> bool:
        statements = self._parse(source)
        if statements is None:
            self.flush("build", exit_code=65, always=True)
            return False

        resolver = Resolver(self.interpreter, self.reporter)
        resolver.resolve(statements)
        if self.reporter.had_error:
            self.flush("build", exit_code=65, always=True)
            return False

        # Erro que o interpretador só levantaria em runtime é rebaixável: não bloqueia
        # o build e não é impresso agora — vira `lox_panic` no ponto (ADR-0031).
        self.reporter.defer_lowerable = True
        checker = Checker(
            self.reporter,
            captured_mutables=resolver.captured_mutables,
            captured_globals=resolver.captured_global_names,
            source_index=self.last_source_index,
        )
        checker.check(statements)
        if self.reporter.had_fatal_error:
            self.flush("build", exit_code=65, always=True)
            return False

        # ADR-0131: sem cargo não há `staticlib` para linkar; falha antes do lowering.
        # A decisão olha só os usos de regex: `had_error` também fica verdadeiro para
        # o erro rebaixável que virou panic site (deferred), e isso não é falta de
        # toolchain — sem este recorte, um `print(1 + true)` sem cargo não compila.
        if cargo_binary() is None:
            regex_uses = tuple(named_uses(statements, self.interpreter.locals, REGEX_PRIMITIVES))
            for use in regex_uses:
                self.reporter.error(use.token, TOOLCHAIN_MESSAGE, code=Code.TOOLCHAIN_MISSING)
            if regex_uses:
                self.flush("build", exit_code=65, always=True)
                return False

        # Import tardio: `llvmlite` só é exigido quando o backend é usado.
        from loxia_core.backend.driver import build as build_native
        from loxia_core.backend.lower import BackendError

        try:
            build_native(
                statements,
                emit=cast("Emit", emit),
                output=output,
                stem=stem,
                types=checker.storage_types,
                depths=self.interpreter.locals,
                generic_instances=checker.generic_fn_instances,
                generic_classes=checker.concrete_class_types(),
                generic_class_sites=checker.generic_class_sites,
                type_aliases=checker.type_aliases(),
                source_path=self._file,
                max_heap=max_heap,
                debug=self.debug,
            )
        except BackendError as error:
            self.reporter.backend_error(error.line, error.message, code=error.code)
            self.flush("build", exit_code=65, always=True)
            return False

        self.flush("build", exit_code=0, always=True)
        return True

    def run_prompt(self) -> None:
        # Sem TTY (pipe, CI, agente) a sessão é um stream: nada de banner nem de
        # prompt no stdout, senão a saída deixa de ser só a do programa.
        interactive = sys.stdin.isatty()
        if interactive:
            print("Loxia REPL (Ctrl+C ou Ctrl+D para sair)")
        prompt = "> " if interactive else ""
        while True:
            try:
                line = input(prompt)
                if not line.strip():
                    continue
                self.run_repl(line)
            except (KeyboardInterrupt, EOFError):
                if interactive:
                    print("\nSaindo...")
                break

    @property
    def watched_files(self) -> set[Path]:
        return set(self._watched_files)

    @property
    def module_files(self) -> dict[str, Path]:
        """Caminho lógico (`std/io.lx`) -> caminho absoluto dos módulos da última análise."""
        return dict(self._module_files)

    @property
    def sources(self) -> SourceMap:
        """Fontes registradas na sessão (o LSP publica source maps para o cliente)."""
        return self._sources

    def exit_code(self) -> int:
        return self._exit_code()

    def report_timeout(self, command: str, milliseconds: int) -> None:
        self.reporter.cli_error(f"Execution timed out after {milliseconds} ms.")
        self.flush(command, exit_code=124, always=True)

    # -- diagnóstico -----------------------------------------------------

    def _exit_code(self) -> int:
        if self.reporter.had_error:
            return 65
        if self.reporter.had_runtime_error:
            return 70
        return 0

    def flush(
        self,
        command: str,
        *,
        exit_code: int,
        always: bool = False,
        revision: int | None = None,
    ) -> None:
        self.flush_batch(
            self.reporter.batch(),
            command,
            exit_code=exit_code,
            always=always,
            revision=revision,
        )

    def flush_batch(
        self,
        batch: DiagnosticBatch,
        command: str,
        *,
        exit_code: int,
        always: bool = False,
        revision: int | None = None,
    ) -> None:
        """Renderiza um batch já coletado (usado por comandos com vários alvos)."""
        success = exit_code == 0

        if self.json_lines:
            self._flush_json_lines(
                command,
                exit_code=exit_code,
                success=success,
                batch=batch,
                revision=self._revision if revision is None else revision,
            )
            return

        if self.error_format == "json":
            if not batch and not always:
                return
            text = render_json(batch, command=command, success=success, exit_code=exit_code)
            stream = sys.stdout if command in JSON_ON_STDOUT else sys.stderr
            stream.write(text)
            stream.flush()
            return

        if not batch:
            return
        text = render_batch(
            batch,
            self._sources,
            error_format=self.error_format,
            color=self._use_color(),
        )
        sys.stderr.write(text)
        sys.stderr.flush()

    def _flush_json_lines(
        self,
        command: str,
        *,
        exit_code: int,
        success: bool,
        batch: DiagnosticBatch,
        revision: int,
    ) -> None:
        lines: list[str] = []
        if not self._jsonl_started:
            lines.append(
                self._jsonl(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "event": "start",
                        "command": command,
                        "version": __version__,
                    }
                )
            )
            self._jsonl_started = True

        for diagnostic in batch.diagnostics:
            payload: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "event": "diagnostic",
            }
            payload.update(diagnostic_json(diagnostic))
            lines.append(self._jsonl(payload))

        lines.append(
            self._jsonl(
                {
                    "schema_version": SCHEMA_VERSION,
                    "event": "summary",
                    "command": command,
                    "success": success,
                    "exit_code": exit_code,
                    "errors": batch.errors,
                    "warnings": batch.warnings,
                    "suppressed": batch.suppressed,
                    "revision": revision,
                }
            )
        )
        stream = sys.stdout if command in JSON_ON_STDOUT else sys.stderr
        stream.write("\n".join(lines) + "\n")
        stream.flush()

    @staticmethod
    def _jsonl(payload: dict[str, object]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _use_color(self) -> bool:
        if self.color == "always":
            return True
        if self.color == "never":
            return False
        return not os.environ.get("NO_COLOR") and sys.stderr.isatty()
