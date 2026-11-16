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
from typing import TYPE_CHECKING, Any, cast

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
from loxia_core.frontend.stmt import Stmt
from loxia_core.semantics.checker import Checker
from loxia_core.semantics.resolver import Resolver

if TYPE_CHECKING:
    from loxia_core.backend.driver import Emit

# Comandos de inspeção: o JSON vai para stdout (não há saída de programa). `build` e
# `run` podem escrever IR/programa em stdout, então o JSON deles vai para stderr.
JSON_ON_STDOUT = frozenset({"check"})
COMMANDS = ("run", "check", "build", "ast", "explain", "capabilities")
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
    ) -> None:
        self.reporter = ErrorReporter(max_errors=max_errors, werror=werror)
        self.interpreter = Interpreter(
            self.reporter, checked_overflow=debug, argv=script_args
        )
        self.error_format = error_format
        self.color = color
        self.json_lines = json_lines
        self._sources = SourceMap()
        self._file = "<stdin>"
        self._module_root: Path | None = None
        self._watched_files: set[Path] = set()
        self._jsonl_started = False
        self._revision = 0

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
            return None

        if self._module_root is not None:
            from loxia_core.loader.loader import ModuleLoader

            loader = ModuleLoader(self.reporter, self._sources, self._module_root)
            loaded = loader.load(statements, self._file)
            if loaded is None:
                return None
            self._watched_files = {
                module.path for module in loader.modules.values()
            }
            statements = loaded

        return statements

    def _execute(self, statements: list[Stmt]) -> None:
        # Em run não há warnings: o binário não os emite e o I1 compara stderr.
        Resolver(
            self.interpreter, self.reporter, warn_unused=False
        ).resolve(statements)

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

    def check(self, source: str, *, emit: bool = True) -> int:
        statements = self._parse(source)
        if statements is not None:
            resolver = Resolver(self.interpreter, self.reporter)
            resolver.resolve(statements)
            if not self.reporter.had_error:
                Checker(
                    self.reporter,
                    captured_mutables=resolver.captured_mutables,
                    captured_globals=resolver.captured_global_names,
                ).check(statements)

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
            )
        except BackendError as error:
            self.reporter.backend_error(
                error.line, error.message, code=error.code
            )
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
            print(f"Erro: Arquivo '{path}' não encontrado.", file=sys.stderr)
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
        print("Loxia REPL (Ctrl+C ou Ctrl+D para sair)")
        while True:
            try:
                line = input("> ")
                if not line.strip():
                    continue
                self.run_repl(line)
            except (KeyboardInterrupt, EOFError):
                print("\nSaindo...")
                break

    @property
    def watched_files(self) -> set[Path]:
        return set(self._watched_files)

    def exit_code(self) -> int:
        return self._exit_code()

    def report_timeout(self, command: str, milliseconds: int) -> None:
        self.reporter.cli_error(
            f"Execution timed out after {milliseconds} ms."
        )
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
            text = render_json(
                batch, command=command, success=success, exit_code=exit_code
            )
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


def _add_common_options(
    parser: argparse.ArgumentParser, *, include_debug: bool = False
) -> None:
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
            "subcomandos: run, check, build, ast, explain, capabilities "
            "(use 'loxia <comando> --help')"
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
        parser.add_argument("script", nargs="?", help="script Loxia")
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
        parser.add_argument("script", help="script Loxia")
    elif command == "ast":
        _add_common_options(parser)
        _add_stdin_options(parser)
        parser.add_argument("script", nargs="?", help="script Loxia")
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


def _validate_legacy(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
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


def _make_loxia(args: argparse.Namespace) -> Loxia:
    error_format = (
        "json" if args.json or args.json_lines else args.error_format
    )
    return Loxia(
        debug=getattr(args, "debug", False),
        error_format=error_format,
        color=args.color,
        max_errors=args.max_errors,
        script_args=getattr(args, "script_args", None),
        json_lines=args.json_lines,
        werror=getattr(args, "werror", False),
    )


def _read_source(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(f"Erro: Arquivo '{path}' não encontrado.", file=sys.stderr)
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
                lox._flush(
                    "check", exit_code=code, always=True, revision=revision
                )
                last = _snapshot([entry, *lox.watched_files])
                revision += 1
            time.sleep(_WATCH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        sys.exit(130)


def _capabilities_payload() -> dict[str, object]:
    commands: list[dict[str, object]] = [
        {
            "name": "run",
            "features": ["json", "json-lines", "stdin", "timeout"],
        },
        {
            "name": "check",
            "features": [
                "json",
                "json-lines",
                "stdin",
                "timeout",
                "watch",
            ],
        },
        {"name": "build", "features": ["json", "json-lines"]},
        {"name": "ast", "features": ["json", "json-lines", "stdin"]},
        {"name": "explain", "features": ["json"]},
        {"name": "capabilities", "features": ["json"]},
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
            "implemented": False,
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
