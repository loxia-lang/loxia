import argparse
import sys

from lox import __version__
from src.ast_printer import AstPrinter
from src.error_reporter import ErrorReporter
from src.interpreter import Interpreter
from src.parser import Parser
from src.resolver import Resolver
from src.scanner import Scanner
from src.stmt import Stmt


class Lox:
    def __init__(self) -> None:
        self.reporter = ErrorReporter()
        self.interpreter = Interpreter(self.reporter)

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

    def run_file(self, path: str, *, dump_ast: bool = False) -> None:
        try:
            with open(path, encoding="utf-8") as file:
                source = file.read()
        except FileNotFoundError:
            print(f"Erro: Arquivo '{path}' não encontrado.", file=sys.stderr)
            sys.exit(66)

        if dump_ast:
            self.dump_ast(source)
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
    parser.add_argument(
        "--dump-ast",
        action="store_true",
        help="imprime a AST do script (S-expression) e não executa",
    )
    parser.add_argument("script", nargs="?", help="Caminho para o script Lox")

    parsed_args = parser.parse_args()

    if parsed_args.dump_ast and not parsed_args.script:
        parser.error("--dump-ast requires a script")

    lox = Lox()

    if parsed_args.script:
        lox.run_file(parsed_args.script, dump_ast=parsed_args.dump_ast)
    else:
        lox.run_prompt()


if __name__ == "__main__":
    main()
