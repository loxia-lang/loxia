# SPDX-License-Identifier: MIT OR Apache-2.0
import argparse
import json
import os
import signal
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any, NoReturn, cast

from loxia import __version__
from loxia_core.diagnostics.codes import CODE_DESCRIPTIONS, CODE_PHASE, Code
from loxia_core.diagnostics.diagnostic import DiagnosticBatch, Severity
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.render import (
    SCHEMA_VERSION,
    diagnostic_json,
    render_batch,
    render_json,
)
from loxia_core.diagnostics.source import SourceMap, display_path
from loxia_core.execution.interpreter import Interpreter
from loxia_core.execution.limits import (
    DEFAULT_HEAP_BYTES,
    MAX_CALL_DEPTH,
    MAX_HEAP_BYTES,
    MIN_HEAP_BYTES,
    STACK_BUDGET_BYTES,
)
from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.source_index import SourceIndex
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.loader.deps import (
    DependencyError,
    fetch_dependencies,
    lock_manifest,
    resolve_dependencies,
)
from loxia_core.loader.lock import (
    LOCK_NAME,
    LockError,
    read_lock,
    render_lock,
    write_lock,
)
from loxia_core.loader.manifest import (
    MANIFEST_NAME,
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
COMMANDS = (
    "run",
    "repl",
    "new",
    "init",
    "check",
    "build",
    "ast",
    "fmt",
    "doc",
    "explain",
    "capabilities",
    "lsp",
    "test",
    "fix",
    "lock",
    "fetch",
)
_HEAP_SUFFIXES = {"k": 1024, "m": 1024**2, "g": 1024**3}
_WATCH_INTERVAL_SECONDS = 0.25


def parse_heap_size(text: str) -> int:
    """Interpreta `512M`, `2G` ou bytes puros; devolve o valor validado."""
    value = text.strip().lower()
    multiplier = 1
    if value and value[-1] in _HEAP_SUFFIXES:
        multiplier = _HEAP_SUFFIXES[value[-1]]
        value = value[:-1]
    try:
        number = int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid heap size '{text}' (use bytes, K, M or G)"
        ) from None
    size = number * multiplier
    if not MIN_HEAP_BYTES <= size <= MAX_HEAP_BYTES:
        raise argparse.ArgumentTypeError(
            f"heap size must be between {MIN_HEAP_BYTES // 1024**2}M "
            f"and {MAX_HEAP_BYTES // 1024**3}G"
        )
    return size


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
    ) -> None:
        self.reporter = ErrorReporter(max_errors=max_errors, werror=werror)
        self.debug = debug
        self.interpreter = Interpreter(self.reporter, checked_overflow=debug, argv=script_args)
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
        self.last_source_index: SourceIndex | None = None
        self.last_resolver: Resolver | None = None
        self.last_checker: Checker | None = None

    # -- pipeline --------------------------------------------------------

    def _parse(self, source: str, *, repl: bool = False) -> list[Stmt] | None:
        self.reporter.reset()
        self.reporter.file = self._file
        self._sources.add(self._file, source)
        self._watched_files = set()

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens, repl=repl, reporter=self.reporter)
        statements = parser.parse_repl() if repl else parser.parse()

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
                self._dependency_error(
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
                    self._dependency_error(
                        lock_path,
                        error.message,
                        line=error.line,
                        column=error.column,
                    )
                    return None
                except DependencyError as error:
                    self._dependency_error(manifest_path, error.message)
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
                _manifest_token(path),
                "Can't read manifest.",
                code=Code.SYNTAX_UNEXPECTED,
            )
            return None
        self._sources.add(display_path(path), text)
        try:
            return parse_manifest(path, text)
        except ManifestError as error:
            self.reporter.error(
                _manifest_token(path, error.line, error.column),
                error.message,
                code=Code.SYNTAX_UNEXPECTED,
            )
            return None

    def _dependency_error(
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
            _manifest_token(path, line, column),
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

        self._flush("run", exit_code=self._exit_code())

    def run_repl(self, source: str) -> None:
        self._file = "<repl>"
        statements = self._parse(source, repl=True)
        if statements is not None:
            self._execute(statements)

        self._flush("repl", exit_code=self._exit_code())

    def dump_ast(self, source: str) -> None:
        statements = self._parse(source)
        if statements is not None:
            print(AstPrinter().print_program(statements))

        self._flush("ast", exit_code=self._exit_code())

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
            self._flush("doc", exit_code=65, always=True)
            return False

        symbols = docgen.extract(statements)
        if json_output:
            text = docgen.render_json(self._file, symbols)
        else:
            text = docgen.render_markdown(self._file, symbols)
        sys.stdout.write(text)
        sys.stdout.flush()
        return True

    def check(self, source: str, *, emit: bool = True) -> int:
        self.last_resolver = None
        self.last_checker = None
        self._warn_unused_imports = True
        try:
            statements = self._parse(source)
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
            self._flush("check", exit_code=exit_code, always=True)
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
            self._flush("build", exit_code=65, always=True)
            return False

        resolver = Resolver(self.interpreter, self.reporter)
        resolver.resolve(statements)
        if self.reporter.had_error:
            self._flush("build", exit_code=65, always=True)
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
            self._flush("build", exit_code=65, always=True)
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
            self._flush("build", exit_code=65, always=True)
            return False

        self._flush("build", exit_code=0, always=True)
        return True

    def run_file(
        self,
        path: str,
        *,
        dump_ast: bool = False,
        check: bool = False,
        emit: str | None = None,
        output: str | None = None,
        max_heap: int | None = None,
    ) -> None:
        try:
            with open(path, encoding="utf-8") as file:
                source = file.read()
        except FileNotFoundError:
            print(
                f"Erro: Arquivo '{display_path(path)}' não encontrado.",
                file=sys.stderr,
            )
            sys.exit(66)

        self._file = display_path(path)
        self._module_root = Path(path).resolve().parent

        if dump_ast:
            self.dump_ast(source)
        elif check:
            self.check(source)
        elif emit is not None:
            destination = Path(output) if output is not None else None
            if not self.build(
                source,
                emit=emit,
                output=destination,
                stem=Path(path).stem,
                max_heap=max_heap,
            ):
                sys.exit(65)
            return
        else:
            self.run(source)

        if self.reporter.had_error:
            sys.exit(65)
        if self.reporter.had_runtime_error:
            sys.exit(70)

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

    def exit_code(self) -> int:
        return self._exit_code()

    def report_timeout(self, command: str, milliseconds: int) -> None:
        self.reporter.cli_error(f"Execution timed out after {milliseconds} ms.")
        self._flush(command, exit_code=124, always=True)

    # -- diagnóstico -----------------------------------------------------

    def _exit_code(self) -> int:
        if self.reporter.had_error:
            return 65
        if self.reporter.had_runtime_error:
            return 70
        return 0

    def _flush(
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


class _Timeout(BaseException):
    """Timeout de comando; BaseException para não ser capturado pelo interpretador."""


def _raise_timeout(signum: int, frame: FrameType | None) -> None:
    raise _Timeout


@contextmanager
def _deadline(milliseconds: int) -> Iterator[None]:
    if not hasattr(signal, "setitimer"):
        raise RuntimeError("--timeout is not supported on this platform")
    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, milliseconds / 1000)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _with_timeout(
    milliseconds: int | None,
    call: Callable[[], object],
    *,
    lox: Loxia,
    command: str,
) -> None:
    if not milliseconds:
        call()
        return
    try:
        with _deadline(milliseconds):
            call()
    except _Timeout:
        lox.report_timeout(command, milliseconds)
        sys.exit(124)


class _ErrorFormatAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        assert isinstance(values, str)
        setattr(namespace, self.dest, values)
        namespace.error_format_explicit = True


def _add_common_options(parser: argparse.ArgumentParser, *, include_debug: bool = False) -> None:
    parser.add_argument(
        "--error-format",
        choices=("human", "short", "json"),
        default="human",
        action=_ErrorFormatAction,
        help="formato dos diagnósticos (human: trecho+caret; short: uma linha; json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="alias de --error-format=json",
    )
    parser.add_argument(
        "--json-lines",
        action="store_true",
        help="um objeto JSON por linha (start/diagnostic/summary)",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="cor nos diagnósticos humanos (auto: só em TTY, respeita NO_COLOR)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=20,
        metavar="N",
        help="limite de diagnósticos por execução (0 = sem limite)",
    )
    parser.add_argument(
        "--module-path",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "raiz adicional de módulos, relativa ao CWD (repetível; "
            "ordem de precedência depois do manifest)"
        ),
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="desliga progresso (aceito por compatibilidade; hoje é no-op)",
    )
    parser.add_argument(
        "-Werror",
        dest="werror",
        action="store_true",
        help="trata warnings como erros (só check/build)",
    )
    if include_debug:
        parser.add_argument(
            "--debug",
            action="store_true",
            help="checa overflow de Int em runtime (release faz wrapping)",
        )
    parser.set_defaults(error_format_explicit=False)


def _add_scaffold_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--name",
        metavar="NOME",
        help="nome do pacote (default: nome do diretório, normalizado para identificador)",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="não inicializa um repositório git no projeto",
    )


def _add_dependency_options(
    parser: argparse.ArgumentParser,
    *,
    frozen: bool = True,
    cache: bool = True,
) -> None:
    if frozen:
        parser.add_argument(
            "--frozen",
            action="store_true",
            help="resolve só pelo loxia.lock; falha se manifest ou conteúdo divergirem",
        )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="nunca acessa a rede (dependências git só do cache)",
    )
    if cache:
        parser.add_argument(
            "--cache-dir",
            metavar="DIR",
            help="cache de dependências (default: .loxia/cache na raiz do projeto)",
        )


def _add_stdin_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="lê o programa de stdin em vez de um arquivo",
    )
    parser.add_argument(
        "--file-name",
        metavar="NOME",
        help="nome de exibição/raiz de módulos quando --stdin (default: <stdin>)",
    )


def _add_timeout(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=int,
        metavar="MS",
        help="tempo limite em milissegundos para run/check (0 = sem limite)",
    )


def _add_watch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--watch",
        action="store_true",
        help="recheca o arquivo e os módulos a cada mudança (só check)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Parser legado, isolado para testes de cobertura (flags x README)."""
    parser = argparse.ArgumentParser(
        prog="loxia",
        description="Loxia: interpretador tree-walk com backend LLVM opcional",
        usage="%(prog)s [opções] [script]",
        epilog=(
            "subcomandos: run, repl, new, init, check, build, ast, fmt, doc, explain, "
            "capabilities, lsp, test, fix, lock, fetch (use 'loxia <comando> --help')"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dump-ast",
        action="store_true",
        help="imprime a AST do script (S-expression) e não executa",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="checa os tipos do script e não executa",
    )
    mode.add_argument(
        "--emit",
        choices=("ll", "obj", "exe"),
        help="compila para código nativo (ll: IR textual, obj: .o, exe: binário)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="caminho de saída do build (padrão: nome do script)",
    )
    parser.add_argument(
        "--max-heap",
        type=parse_heap_size,
        metavar="SIZE",
        help=(
            "teto de heap do binário nativo (default: "
            f"{DEFAULT_HEAP_BYTES // 1024**2}M; ex.: 512M, 2G); só com --emit=exe"
        ),
    )
    _add_common_options(parser, include_debug=True)
    _add_stdin_options(parser)
    _add_timeout(parser)
    _add_watch(parser)
    parser.add_argument("script", nargs="?", help="Caminho para o script Loxia")
    parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="argumentos repassados para o programa (args())",
    )
    return parser


def _build_subcommand_parser(command: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"loxia {command}",
        description=f"loxia {command}",
    )
    if command == "run":
        _add_common_options(parser, include_debug=True)
        _add_stdin_options(parser)
        _add_timeout(parser)
        _add_dependency_options(parser)
        parser.add_argument("script", nargs="?", help="script Loxia")
        parser.add_argument(
            "script_args",
            nargs="*",
            help="argumentos repassados para o programa (use -- antes)",
        )
    elif command == "check":
        _add_common_options(parser)
        _add_stdin_options(parser)
        _add_timeout(parser)
        _add_watch(parser)
        _add_dependency_options(parser)
        parser.add_argument("script", nargs="?", help="script Loxia")
    elif command == "repl":
        # Sessão interativa (ou stream em pipe): não há arquivo de entrada.
        _add_common_options(parser, include_debug=True)
    elif command == "new":
        _add_common_options(parser)
        _add_scaffold_options(parser)
        parser.add_argument("path", help="diretório do projeto (não pode existir)")
    elif command == "init":
        _add_common_options(parser)
        _add_scaffold_options(parser)
        parser.add_argument(
            "path",
            nargs="?",
            default=".",
            help="diretório existente para inicializar (default: .)",
        )
    elif command == "build":
        _add_common_options(parser)
        parser.add_argument(
            "--emit",
            choices=("ll", "obj", "exe"),
            default="exe",
            help="tipo de saída (default: exe)",
        )
        parser.add_argument("-o", "--output", help="caminho de saída")
        parser.add_argument(
            "--max-heap",
            type=parse_heap_size,
            metavar="SIZE",
            help="teto de heap do binário nativo (só --emit=exe)",
        )
        _add_dependency_options(parser)
        parser.add_argument("script", help="script Loxia")
    elif command == "ast":
        _add_common_options(parser)
        _add_stdin_options(parser)
        _add_dependency_options(parser)
        parser.add_argument("script", nargs="?", help="script Loxia")
    elif command == "fmt":
        _add_common_options(parser)
        _add_stdin_options(parser)
        parser.add_argument("--check", action="store_true", help="não escreve; exit 1 se mudaria")
        parser.add_argument("script", nargs="?", help="arquivo Loxia")
    elif command == "doc":
        parser.add_argument("script", nargs="?", help="arquivo Loxia")
        parser.add_argument("--stdin", action="store_true", help="lê de stdin")
        parser.add_argument("--file-name", metavar="NOME", help="nome de exibição")
        parser.add_argument("--json", action="store_true", help="referência em JSON")
        parser.add_argument(
            "--error-format",
            choices=("human", "short", "json"),
            default="human",
            action=_ErrorFormatAction,
            help="formato dos diagnósticos",
        )
        parser.add_argument(
            "--color",
            choices=("auto", "always", "never"),
            default="auto",
            help="cor nos diagnósticos",
        )
        parser.add_argument(
            "--max-errors",
            type=int,
            default=20,
            metavar="N",
            help="limite de diagnósticos",
        )
        parser.set_defaults(error_format_explicit=False)
    elif command == "lsp":
        parser.add_argument(
            "--stdio",
            action="store_true",
            help="usa stdio (padrão; aceito para compatibilidade)",
        )
    elif command == "fix":
        parser.add_argument("script", help="arquivo Loxia")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="grava as mudanças (padrão: dry-run)",
        )
        parser.add_argument(
            "--max-iterations",
            type=int,
            default=10,
            metavar="N",
            help="rodadas de fix (default: 10)",
        )
        parser.add_argument("--json", action="store_true", help="resumo em JSON")
    elif command == "test":
        parser.add_argument(
            "paths",
            nargs="*",
            help="arquivos ou diretórios (default: tests/ se existir, senão .)",
        )
        parser.add_argument("--filter", metavar="SUB", help="só nomes com SUB")
        parser.add_argument("--only", metavar="NAME", help="só o teste com esse nome exato")
        parser.add_argument(
            "--jobs",
            type=int,
            default=1,
            metavar="N",
            help="arquivos em paralelo (default: 1)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            metavar="MS",
            help="timeout por arquivo em milissegundos",
        )
        parser.add_argument("--json", action="store_true", help="relatório em JSON")
        parser.add_argument(
            "--isolate",
            choices=("file", "test"),
            default="file",
            help="processo por arquivo (default) ou por teste",
        )
        parser.add_argument(
            "--fail-fast", action="store_true", help="para no primeiro arquivo com falha"
        )
        parser.add_argument(
            "--native",
            action="store_true",
            help="compila cada arquivo e roda o binário",
        )
        _add_dependency_options(parser)
    elif command == "lock":
        _add_common_options(parser)
        parser.add_argument(
            "--check",
            action="store_true",
            help="não escreve; exit 1 se o lock estiver desatualizado",
        )
        _add_dependency_options(parser, frozen=False)
    elif command == "fetch":
        _add_common_options(parser)
        _add_dependency_options(parser, frozen=False)
    elif command == "explain":
        parser.add_argument("code", help="código de diagnóstico (ex.: E2001)")
        parser.add_argument("--json", action="store_true", help="saída JSON")
    elif command == "capabilities":
        parser.add_argument("--json", action="store_true", help="saída JSON")
    else:  # pragma: no cover - guarda de programação
        raise AssertionError(f"unknown command {command}")
    return parser


def _validate(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    command: str,
) -> None:
    args.stdin = getattr(args, "stdin", False)
    args.file_name = getattr(args, "file_name", None)
    args.timeout = getattr(args, "timeout", None)
    args.watch = getattr(args, "watch", False)
    args.frozen = getattr(args, "frozen", False)
    args.offline = getattr(args, "offline", False)
    args.cache_dir = getattr(args, "cache_dir", None)
    if args.json_lines and args.error_format_explicit:
        parser.error("--json-lines cannot be combined with --error-format")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    if args.timeout is not None and args.timeout < 0:
        parser.error("--timeout must be non-negative")
    if args.timeout and not hasattr(signal, "setitimer"):
        parser.error("--timeout is not supported on this platform")
    if args.timeout and command not in {"run", "check"}:
        parser.error("--timeout is only supported by run/check")
    if args.timeout and getattr(args, "watch", False):
        parser.error("--timeout cannot be combined with --watch")
    if getattr(args, "watch", False) and command != "check":
        parser.error("--watch is only supported by check")
    if getattr(args, "watch", False) and args.stdin:
        parser.error("--watch cannot be combined with --stdin")
    if args.stdin and getattr(args, "script", None):
        parser.error("--stdin cannot be combined with a script")
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    if command in {"run", "check", "ast"} and not args.stdin and not args.script:
        parser.error(f"{command} requires a script (or --stdin)")
    if command == "build":
        if args.stdin:
            parser.error("build does not support --stdin yet")
        if args.max_heap is not None and args.emit != "exe":
            parser.error("--max-heap requires --emit=exe")


def _validate_legacy(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.json_lines and args.error_format_explicit:
        parser.error("--json-lines cannot be combined with --error-format")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    if args.timeout is not None and args.timeout < 0:
        parser.error("--timeout must be non-negative")
    if args.timeout and not hasattr(signal, "setitimer"):
        parser.error("--timeout is not supported on this platform")
    if args.timeout and (args.dump_ast or args.emit):
        parser.error("--timeout is only supported by run/check")
    if args.watch and not args.check:
        parser.error("--watch requires --check")
    if args.watch and args.stdin:
        parser.error("--watch cannot be combined with --stdin")
    if args.watch and not args.script:
        parser.error("--watch requires a script")
    if args.watch and args.timeout:
        parser.error("--timeout cannot be combined with --watch")
    if args.stdin and args.script:
        parser.error("--stdin cannot be combined with a script")
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    if (args.dump_ast or args.check or args.emit) and not (args.script or args.stdin):
        parser.error("--dump-ast/--check/--emit requires a script")
    if args.emit and args.stdin:
        parser.error("--stdin cannot be used with --emit")
    if args.output and not args.emit:
        parser.error("-o/--output requires --emit")
    if args.max_heap is not None and args.emit != "exe":
        parser.error("--max-heap requires --emit=exe")
    if not args.script and not args.stdin:
        if args.json_lines:
            parser.error("--json-lines requires a script or --stdin")
        if args.timeout:
            parser.error("--timeout requires a script or --stdin")


def _manifest_token(path: Path, line: int = 1, column: int = 1) -> Token:
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


def _make_loxia(args: argparse.Namespace) -> Loxia:
    error_format = "json" if args.json or args.json_lines else args.error_format
    return Loxia(
        debug=getattr(args, "debug", False),
        error_format=error_format,
        color=args.color,
        max_errors=args.max_errors,
        script_args=getattr(args, "script_args", None),
        json_lines=args.json_lines,
        werror=getattr(args, "werror", False),
        module_paths=getattr(args, "module_path", None),
        frozen=getattr(args, "frozen", False),
        offline=getattr(args, "offline", False),
        cache_dir=getattr(args, "cache_dir", None),
    )


def _read_source(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(
            f"Erro: Arquivo '{display_path(path)}' não encontrado.",
            file=sys.stderr,
        )
        sys.exit(66)


def _set_source(
    lox: Loxia,
    *,
    path: str | None,
    stdin: bool,
    file_name: str | None,
) -> str:
    if stdin:
        lox._file = file_name or "<stdin>"
        lox._module_root = Path.cwd()
        return sys.stdin.read()
    assert path is not None
    source = _read_source(path)
    lox._file = display_path(path)
    lox._module_root = Path(path).resolve().parent
    return source


def _run_source(
    lox: Loxia,
    args: argparse.Namespace,
    *,
    command: str,
) -> None:
    source = _set_source(
        lox,
        path=args.script,
        stdin=args.stdin,
        file_name=args.file_name,
    )
    if command == "ast":
        lox.dump_ast(source)
        sys.exit(lox.exit_code())
    if command == "check":
        _with_timeout(
            args.timeout,
            lambda: lox.check(source),
            lox=lox,
            command="check",
        )
        sys.exit(lox.exit_code())
    _with_timeout(
        args.timeout,
        lambda: lox.run(source),
        lox=lox,
        command="run",
    )
    sys.exit(lox.exit_code())


def _run_fmt(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from loxia.formatter import format_source

    if args.stdin and args.script:
        parser.error("--stdin cannot be combined with a script")
    if not args.stdin and not args.script:
        parser.error("fmt requires a script (or --stdin)")
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    if args.timeout if hasattr(args, "timeout") else False:
        parser.error("--timeout is not supported by fmt")

    lox = Loxia(
        error_format=("json" if args.json or args.json_lines else args.error_format),
        color=args.color,
        max_errors=args.max_errors,
        json_lines=args.json_lines,
    )
    source = _set_source(
        lox,
        path=args.script,
        stdin=args.stdin,
        file_name=args.file_name,
    )
    result = format_source(source, reporter=lox.reporter)
    if result is None:
        lox._flush("fmt", exit_code=65, always=True)
        sys.exit(65)

    if args.check:
        sys.exit(1 if result.changed else 0)

    if args.stdin:
        sys.stdout.write(result.text)
        sys.stdout.flush()
        return

    assert args.script is not None
    if result.changed:
        Path(args.script).write_text(result.text, encoding="utf-8")
    sys.exit(0)


def _run_doc(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.script and args.stdin:
        parser.error("--stdin cannot be combined with a script")
    if not args.script and not args.stdin:
        parser.error("doc requires a script (or --stdin)")
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    lox = Loxia(
        error_format=args.error_format,
        color=args.color,
        max_errors=args.max_errors,
    )
    source = _set_source(
        lox,
        path=args.script,
        stdin=args.stdin,
        file_name=args.file_name,
    )
    if not lox.document(source, json_output=args.json):
        sys.exit(65)


def _run_scaffold(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    command: str,
) -> None:
    from loxia.scaffold import ScaffoldError, create, validate_name

    _validate(args, parser, command=command)
    lox = _make_loxia(args)
    if args.name is not None:
        try:
            validate_name(args.name)
        except ScaffoldError as error:
            parser.error(error.message)
    target = Path(args.path)
    try:
        project = create(
            target,
            name=args.name,
            git=not args.no_git,
            require_new=command == "new",
        )
    except ScaffoldError as error:
        lox.reporter.error(
            _manifest_token(target / "loxia.toml"),
            error.message,
            code=Code.SCAFFOLD_STATE,
        )
        lox._flush(command, exit_code=65, always=True)
        sys.exit(65)
    shown = display_path(project.path, cwd=Path.cwd())
    if args.json:
        print(
            json.dumps(
                {
                    "path": shown,
                    "name": project.name,
                    "files": list(project.files),
                    "git": project.git_initialized,
                },
                ensure_ascii=False,
            )
        )
        return
    verb = "Created" if command == "new" else "Initialized"
    print(f"{verb} project '{project.name}' at '{shown}'.")


def _dependency_failure(
    lox: Loxia,
    command: str,
    path: Path,
    message: str,
    *,
    line: int = 1,
    column: int = 1,
) -> NoReturn:
    lox._dependency_error(path, message, line=line, column=column)
    lox._flush(command, exit_code=65, always=True)
    sys.exit(65)


def _project_manifest(lox: Loxia, command: str) -> Manifest:
    manifest_path = discover_manifest(Path.cwd())
    if manifest_path is None:
        _dependency_failure(lox, command, Path.cwd() / MANIFEST_NAME, "No loxia.toml found.")
    manifest = lox._load_manifest(manifest_path)
    if manifest is None:
        lox._flush(command, exit_code=65, always=True)
        sys.exit(65)
    return manifest


def _run_lock(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="lock")
    lox = _make_loxia(args)
    manifest = _project_manifest(lox, "lock")
    lock_path = manifest.path.parent / LOCK_NAME
    try:
        lock = lock_manifest(manifest, offline=args.offline, cache_dir=lox.cache_dir)
        if args.check:
            current = read_lock(lock_path)
            if current is None or render_lock(current) != render_lock(lock):
                print("loxia.lock is out of date; run 'loxia lock'.", file=sys.stderr)
                sys.exit(1)
            return
        write_lock(lock_path, lock)
    except LockError as error:
        _dependency_failure(
            lox,
            "lock",
            lock_path,
            error.message,
            line=error.line,
            column=error.column,
        )
    except DependencyError as error:
        _dependency_failure(lox, "lock", manifest.path, error.message)


def _run_fetch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="fetch")
    lox = _make_loxia(args)
    manifest = _project_manifest(lox, "fetch")
    lock_path = manifest.path.parent / LOCK_NAME
    try:
        lock = read_lock(lock_path)
        fetch_dependencies(
            manifest,
            lock=lock,
            offline=args.offline,
            cache_dir=lox.cache_dir,
        )
    except LockError as error:
        _dependency_failure(
            lox,
            "fetch",
            lock_path,
            error.message,
            line=error.line,
            column=error.column,
        )
    except DependencyError as error:
        _dependency_failure(lox, "fetch", manifest.path, error.message)


def _run_build(lox: Loxia, args: argparse.Namespace) -> None:
    source = _set_source(
        lox,
        path=args.script,
        stdin=False,
        file_name=None,
    )
    destination = Path(args.output) if args.output is not None else None
    ok = lox.build(
        source,
        emit=args.emit,
        output=destination,
        stem=Path(args.script).stem,
        max_heap=args.max_heap,
    )
    sys.exit(0 if ok else 65)


def _snapshot(paths: list[Path]) -> tuple[tuple[str, int | None, int | None], ...]:
    snapshot: list[tuple[str, int | None, int | None]] = []
    for path in sorted(set(paths)):
        try:
            stat = os.stat(path)
        except OSError:
            snapshot.append((str(path), None, None))
        else:
            snapshot.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(snapshot)


def _watch_check(lox: Loxia, args: argparse.Namespace) -> None:
    assert args.script is not None
    entry = Path(args.script).resolve()
    last: tuple[tuple[str, int | None, int | None], ...] | None = None
    revision = 0
    try:
        while True:
            paths = [entry, *lox.watched_files]
            current = _snapshot(paths)
            if current != last:
                source = _read_source(args.script)
                lox._file = display_path(args.script)
                lox._module_root = entry.parent
                code = lox.check(source, emit=False)
                lox._revision = revision
                lox._flush("check", exit_code=code, always=True, revision=revision)
                last = _snapshot([entry, *lox.watched_files])
                revision += 1
            time.sleep(_WATCH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        sys.exit(130)


def _capabilities_payload() -> dict[str, object]:
    commands: list[dict[str, object]] = [
        {
            "name": "run",
            "features": [
                "json",
                "json-lines",
                "stdin",
                "timeout",
                "frozen",
                "offline",
                "cache-dir",
            ],
        },
        {
            "name": "repl",
            "features": ["json", "json-lines", "debug", "module-path"],
        },
        {"name": "new", "features": ["name", "no-git", "json"]},
        {"name": "init", "features": ["name", "no-git", "json"]},
        {
            "name": "check",
            "features": [
                "json",
                "json-lines",
                "stdin",
                "timeout",
                "watch",
                "frozen",
                "offline",
                "cache-dir",
            ],
        },
        {
            "name": "build",
            "features": ["json", "json-lines", "frozen", "offline", "cache-dir"],
        },
        {
            "name": "ast",
            "features": ["json", "json-lines", "stdin", "frozen", "offline", "cache-dir"],
        },
        {"name": "fmt", "features": ["check", "stdin"]},
        {"name": "fix", "features": ["apply", "json"]},
        {
            "name": "test",
            "features": [
                "json",
                "filter",
                "only",
                "jobs",
                "isolate",
                "fail-fast",
                "native",
                "timeout",
                "frozen",
                "offline",
                "cache-dir",
            ],
        },
        {"name": "lock", "features": ["check", "offline", "cache-dir"]},
        {"name": "fetch", "features": ["offline", "cache-dir"]},
        {"name": "doc", "features": ["json", "stdin"]},
        {"name": "explain", "features": ["json"]},
        {"name": "capabilities", "features": ["json"]},
        {
            "name": "lsp",
            "features": [
                "stdio",
                "hover",
                "definition",
                "documentSymbol",
                "completion",
                "signatureHelp",
                "inlayHint",
                "formatting",
                "codeAction",
                "rename",
                "workspaceSymbol",
                "semanticTokens",
            ],
        },
    ]
    codes = [
        {
            "code": code.value,
            "phase": CODE_PHASE[code].value,
            "description": CODE_DESCRIPTIONS[code],
        }
        for code in sorted(Code, key=lambda item: item.value)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "version": __version__,
        "program": "loxia",
        "commands": commands,
        "error_formats": ["human", "short", "json"],
        "jsonl_events": ["start", "diagnostic", "summary"],
        "codes": codes,
        "limits": {
            "max_call_depth": MAX_CALL_DEPTH,
            "stack_budget_bytes": STACK_BUDGET_BYTES,
            "default_heap_bytes": DEFAULT_HEAP_BYTES,
        },
        "warnings": {"codes": ["W1001"], "werror": True},
        "fixes": {
            "applicability": ["safe", "unsafe"],
            "implemented": True,
        },
    }


def _print_capabilities(as_json: bool) -> None:
    payload = _capabilities_payload()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    commands = cast(list[dict[str, object]], payload["commands"])
    print(f"loxia {payload['version']}")
    print("commands: " + ", ".join(str(command["name"]) for command in commands))
    print("error formats: " + ", ".join(cast(list[str], payload["error_formats"])))
    print("jsonl events: " + ", ".join(cast(list[str], payload["jsonl_events"])))
    print(f"max call depth: {MAX_CALL_DEPTH}")
    print(f"default heap: {DEFAULT_HEAP_BYTES // 1024**2}M")


def _explain(code_text: str, as_json: bool) -> None:
    try:
        code = Code(code_text.upper())
    except ValueError:
        print(f"Erro: código de diagnóstico desconhecido: {code_text}", file=sys.stderr)
        sys.exit(2)

    phase = CODE_PHASE[code]
    description = CODE_DESCRIPTIONS[code]
    if as_json:
        print(
            json.dumps(
                {
                    "code": code.value,
                    "phase": phase.value,
                    "severity": (
                        Severity.WARNING.value
                        if code.value.startswith("W")
                        else Severity.ERROR.value
                    ),
                    "description": description,
                    "doc": "docs/spec/erros.md",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(f"{code.value} ({phase.value}): {description}")
    print("See docs/spec/erros.md.")


def _main_subcommand(command: str, argv: list[str]) -> None:
    parser = _build_subcommand_parser(command)
    args = parser.parse_args(argv)

    if command in {"explain", "capabilities"}:
        if command == "explain":
            _explain(args.code, args.json)
        else:
            _print_capabilities(args.json)
        return

    if command == "lsp":
        from loxia.lsp import main as lsp_main

        raise SystemExit(lsp_main())

    if command == "test":
        from loxia.test_runner import run_tests

        raise SystemExit(run_tests(args))

    if command == "fix":
        from loxia.fixer import run_fix_command

        raise SystemExit(run_fix_command(args))

    if command == "fmt":
        _run_fmt(args, parser)
        return

    if command == "doc":
        _run_doc(args, parser)
        return

    if command in {"new", "init"}:
        _run_scaffold(args, parser, command=command)
        return

    if command == "lock":
        _run_lock(args, parser)
        return

    if command == "fetch":
        _run_fetch(args, parser)
        return

    if command == "repl":
        _validate(args, parser, command=command)
        _make_loxia(args).run_prompt()
        return

    _validate(args, parser, command=command)
    lox = _make_loxia(args)

    if command == "build":
        _run_build(lox, args)
    elif command == "check" and args.watch:
        _watch_check(lox, args)
    else:
        _run_source(lox, args, command=command)


def _main_legacy(argv: list[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_legacy(args, parser)
    lox = _make_loxia(args)

    if args.watch:
        _watch_check(lox, args)
    elif args.stdin:
        _run_source(lox, args, command="ast" if args.dump_ast else "check" if args.check else "run")
    elif args.script:
        if args.dump_ast or args.check or args.emit:
            if args.emit is not None:
                _run_build(lox, args)
            else:
                _run_source(
                    lox,
                    args,
                    command="ast" if args.dump_ast else "check",
                )
        else:
            _run_source(lox, args, command="run")
    else:
        lox.run_prompt()


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] in COMMANDS:
        _main_subcommand(argv[0], argv[1:])
    else:
        _main_legacy(argv)


if __name__ == "__main__":
    main()
