import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loxia import __version__
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.render import render_batch, render_json
from loxia_core.diagnostics.source import SourceMap, display_path
from loxia_core.execution.interpreter import Interpreter
from loxia_core.execution.limits import (
    DEFAULT_HEAP_BYTES,
    MAX_HEAP_BYTES,
    MIN_HEAP_BYTES,
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
_HEAP_SUFFIXES = {"k": 1024, "m": 1024**2, "g": 1024**3}


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
    ) -> None:
        self.reporter = ErrorReporter(max_errors=max_errors)
        self.interpreter = Interpreter(
            self.reporter, checked_overflow=debug, argv=script_args
        )
        self.error_format = error_format
        self.color = color
        self._sources = SourceMap()
        self._file = "<stdin>"
        self._module_root: Path | None = None

    # -- pipeline --------------------------------------------------------

    def _parse(self, source: str, *, repl: bool = False) -> list[Stmt] | None:
        self.reporter.reset()
        self.reporter.file = self._file
        self._sources.add(self._file, source)

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens, repl=repl, reporter=self.reporter)
        statements = parser.parse_repl() if repl else parser.parse()

        if self.reporter.had_error or statements is None:
            return None

        if self._module_root is not None:
            from loxia_core.loader.loader import ModuleLoader

            loaded = ModuleLoader(
                self.reporter, self._sources, self._module_root
            ).load(statements, self._file)
            if loaded is None:
                return None
            statements = loaded

        return statements

    def _execute(self, statements: list[Stmt]) -> None:
        Resolver(self.interpreter, self.reporter).resolve(statements)

        if self.reporter.had_error:
            return

        self.interpreter.interpret(statements)

    # -- comandos --------------------------------------------------------

    def run(self, source: str) -> None:
        statements = self._parse(source)
        if statements is not None:
            self._execute(statements)

        exit_code = self._exit_code()
        self._flush("run", exit_code=exit_code)

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

    def check(self, source: str) -> None:
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

        self._flush("check", exit_code=self._exit_code(), always=True)

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

    # -- diagnóstico -----------------------------------------------------

    def _exit_code(self) -> int:
        if self.reporter.had_error:
            return 65
        if self.reporter.had_runtime_error:
            return 70
        return 0

    def _flush(self, command: str, *, exit_code: int, always: bool = False) -> None:
        batch = self.reporter.batch()
        success = exit_code == 0

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

    def _use_color(self) -> bool:
        if self.color == "always":
            return True
        if self.color == "never":
            return False
        return not os.environ.get("NO_COLOR") and sys.stderr.isatty()


def build_parser() -> argparse.ArgumentParser:
    """Parser do CLI, isolado para testes de cobertura (flags x README)."""
    parser = argparse.ArgumentParser(
        prog="loxia",
        description="Loxia: interpretador tree-walk com backend LLVM opcional",
        usage="%(prog)s [opções] [script]",
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="checa overflow de Int em runtime (release faz wrapping)",
    )
    parser.add_argument(
        "--error-format",
        choices=("human", "short", "json"),
        default="human",
        help="formato dos diagnósticos (human: trecho+caret; short: uma linha; json)",
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
    parser.add_argument("script", nargs="?", help="Caminho para o script Loxia")
    parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="argumentos repassados para o programa (args())",
    )
    return parser


def main() -> None:
    parser = build_parser()
    parsed_args = parser.parse_args()

    if (parsed_args.dump_ast or parsed_args.check or parsed_args.emit) and not (
        parsed_args.script
    ):
        parser.error("--dump-ast/--check/--emit requires a script")
    if parsed_args.output and not parsed_args.emit:
        parser.error("-o/--output requires --emit")
    if parsed_args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    if parsed_args.max_heap is not None and parsed_args.emit != "exe":
        parser.error("--max-heap requires --emit=exe")

    lox = Loxia(
        debug=parsed_args.debug,
        error_format=parsed_args.error_format,
        color=parsed_args.color,
        max_errors=parsed_args.max_errors,
        script_args=parsed_args.script_args,
    )

    if parsed_args.script:
        lox.run_file(
            parsed_args.script,
            dump_ast=parsed_args.dump_ast,
            check=parsed_args.check,
            emit=parsed_args.emit,
            output=parsed_args.output,
            max_heap=parsed_args.max_heap,
        )
    else:
        lox.run_prompt()


if __name__ == "__main__":
    main()
