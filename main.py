import argparse
import sys

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

    def run(self, source: str) -> None:
        self.reporter.reset()

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens, reporter=self.reporter)
        statements: list[Stmt] | None = parser.parse()

        if self.reporter.had_error or statements is None:
            return

        Resolver(self.interpreter, self.reporter).resolve(statements)

        if self.reporter.had_error:
            return

        self.interpreter.interpret(statements)

    def run_repl(self, source: str) -> None:
        self.reporter.reset()

        scanner = Scanner(source, self.reporter)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens, repl=True, reporter=self.reporter)

        statements = parser.parse_repl()

        if self.reporter.had_error or statements is None:
            return

        Resolver(self.interpreter, self.reporter).resolve(statements)

        if self.reporter.had_error:
            return

        self.interpreter.interpret(statements)


    def run_file(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as file:
                source = file.read()
            self.run(source)

            if self.reporter.had_error:
                sys.exit(65)
            if self.reporter.had_runtime_error:
                sys.exit(70)
        except FileNotFoundError:
            print(f"Erro: Arquivo '{path}' não encontrado.", file=sys.stderr)
            sys.exit(66)

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
        usage="%(prog)s [script]",
    )
    parser.add_argument("script", nargs="?", help="Caminho para o script Lox")

    parsed_args = parser.parse_args()
    lox = Lox()

    if parsed_args.script:
        lox.run_file(parsed_args.script)
    else:
        lox.run_prompt()


if __name__ == "__main__":
    main()
