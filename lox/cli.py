import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from lox import __version__
from src.diagnostics.error_reporter import ErrorReporter
from src.execution.interpreter import Interpreter
from src.frontend.ast_printer import AstPrinter
from src.frontend.parser import Parser
from src.frontend.scanner import Scanner
from src.frontend.stmt import Stmt
from src.semantics.checker import Checker
from src.semantics.resolver import Resolver

if TYPE_CHECKING:
    from src.backend.driver import Emit


class Lox:
    def __init__(self, *, debug: bool = False) -> None:
        self.reporter = ErrorReporter()
        self.interpreter = Interpreter(
            self.reporter, checked_overflow=debug
        )

    def _parse(self, source: str, *, repl: bool = False) -> list[Stmt] | None:
        self.reporter.reset()

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens, repl=repl, reporter=self.reporter)
        statements = parser.parse_repl() if repl else parser.parse()

        if self.reporter.had_error or statements is None:
            return None

        return statements

    def _execute(self, statements: list[Stmt]) -> None:
        Resolver(self.interpreter, self.reporter).resolve(statements)

        if self.reporter.had_error:
            return

        self.interpreter.interpret(statements)

    def run(self, source: str) -> None:
        statements = self._parse(source)
        if statements is not None:
            self._execute(statements)

    def run_repl(self, source: str) -> None:
        statements = self._parse(source, repl=True)
        if statements is not None:
            self._execute(statements)

    def dump_ast(self, source: str) -> None:
        statements = self._parse(source)
        if statements is not None:
            print(AstPrinter().print_program(statements))

    def check(self, source: str) -> None:
        statements = self._parse(source)
        if statements is None:
            return

        Resolver(self.interpreter, self.reporter).resolve(statements)
        if self.reporter.had_error:
            return

        Checker(self.reporter).check(statements)

    def build(
        self, source: str, *, emit: str, output: Path | None, stem: str
    ) -> bool:
        statements = self._parse(source)
        if statements is None:
            return False

        Resolver(self.interpreter, self.reporter).resolve(statements)
        if self.reporter.had_error:
            return False

        # Erro que o interpretador só levantaria em runtime é rebaixável: não bloqueia
        # o build e não é impresso agora — vira `lox_panic` no ponto (ADR-0031).
        self.reporter.defer_lowerable = True
        checker = Checker(self.reporter)
        checker.check(statements)
        if self.reporter.had_fatal_error:
            return False

        # Import tardio: `llvmlite` só é exigido quando o backend é usado.
        from src.backend.driver import build as build_native
        from src.backend.lower import BackendError

        try:
            build_native(
                statements,
                emit=cast("Emit", emit),
                output=output,
                stem=stem,
                types=checker.storage_types,
                depths=self.interpreter.locals,
            )
        except BackendError as error:
            self.reporter.backend_error(error.line, error.message)
            return False

        return True

    def run_file(
        self,
        path: str,
        *,
        dump_ast: bool = False,
        check: bool = False,
        emit: str | None = None,
        output: str | None = None,
    ) -> None:
        try:
            with open(path, encoding="utf-8") as file:
                source = file.read()
        except FileNotFoundError:
            print(f"Erro: Arquivo '{path}' não encontrado.", file=sys.stderr)
            sys.exit(66)

        if dump_ast:
            self.dump_ast(source)
        elif check:
            self.check(source)
        elif emit is not None:
            destination = Path(output) if output is not None else None
            if not self.build(
                source, emit=emit, output=destination, stem=Path(path).stem
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
        print("PyLox REPL (Ctrl+C ou Ctrl+D para sair)")
        while True:
            try:
                line = input("> ")
                if not line.strip():
                    continue
                self.run_repl(line)
            except (KeyboardInterrupt, EOFError):
                print("\nSaindo...")
                break


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pylox",
        description="Interpretador Lox em Python",
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
        "--debug",
        action="store_true",
        help="checa overflow de Int em runtime (release faz wrapping)",
    )
    parser.add_argument("script", nargs="?", help="Caminho para o script Lox")

    parsed_args = parser.parse_args()

    if (parsed_args.dump_ast or parsed_args.check or parsed_args.emit) and not (
        parsed_args.script
    ):
        parser.error("--dump-ast/--check/--emit requires a script")
    if parsed_args.output and not parsed_args.emit:
        parser.error("-o/--output requires --emit")

    lox = Lox(debug=parsed_args.debug)

    if parsed_args.script:
        lox.run_file(
            parsed_args.script,
            dump_ast=parsed_args.dump_ast,
            check=parsed_args.check,
            emit=parsed_args.emit,
            output=parsed_args.output,
        )
    else:
        lox.run_prompt()


if __name__ == "__main__":
    main()
