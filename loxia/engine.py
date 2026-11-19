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
from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.source_index import SourceIndex
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.loader.deps import DependencyError, resolve_dependencies
from loxia_core.loader.lock import LOCK_NAME, LockError, read_lock
from loxia_core.loader.manifest import (
    Manifest,
    ManifestError,
    discover_manifest,
    parse_manifest,
)
from loxia_core.semantics.checker import Checker
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
        self._sources = SourceMap()
        self._file = "<stdin>"
        self._module_root: Path | None = None
        self._module_paths: tuple[Path, ...] = tuple(
            Path(path).resolve() for path in (module_paths or ())
        )
        self._watched_files: set[Path] = set()
        self._warn_unused_imports = False
        self._jsonl_started = False
        self._revision = 0
        # Estado da última análise, consumido pelo LSP (hover/definition).
        self.last_statements: list[Stmt] | None = None
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
    ) -> list[Stmt] | None:
        self.reporter.reset()
        self.reporter.file = self._file
        self._sources.add(self._file, source)
        self._watched_files = set()

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens, repl=repl, reporter=self.reporter)
        statements = parser.parse_repl() if repl else parser.parse()
        self.last_recovered_statements = statements

        if self.reporter.had_error or statements is None:
            self.last_statements = None
            return None

        if self._module_root is not None:
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

    def _execute(self, statements: list[Stmt]) -> None:
        # Em run não há warnings: o binário não os emite e o I1 compara stderr.
        Resolver(self.interpreter, self.reporter, warn_unused=False).resolve(statements)

        if self.reporter.had_error:
            return

        self.interpreter.interpret(statements)

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
            self._execute(statements)

        self.flush("repl", exit_code=self._exit_code())

    def dump_ast(self, source: str) -> None:
        statements = self._parse(source)
        if statements is not None:
            print(AstPrinter().print_program(statements))

        self.flush("ast", exit_code=self._exit_code())

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
                checker = Checker(
                    self.reporter,
                    captured_mutables=resolver.captured_mutables,
                    captured_globals=resolver.captured_global_names,
                    source_index=self.last_source_index,
                )
                checker.check(statements)
                self.last_checker = checker

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
        batch = self.reporter.batch()
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
