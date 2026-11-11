import argparse
import sys

from src.error_reporter import ErrorReporter
from src.interpreter import Interpreter
from src.parser import Parser
from src.scanner import Scanner
from src.stmt import Stmt


class Lox:
    def __init__(self):
        self.interpreter = Interpreter()

    def run(self, source: str) -> None:
        scanner = Scanner(source)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens)
        statements:list[Stmt] | None = parser.parse()

        if ErrorReporter.had_error or statements is None:
            return

        self.interpreter.interpret(statements)

    def run_repl(self, source: str) -> None:
        scanner = Scanner(source)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens)

        statements = parser.parse_repl()

        if ErrorReporter.had_error or statements is None:
            return

        self.interpreter.interpret(statements)


    def run_file(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as file:
                source = file.read()
            self.run(source)

            if ErrorReporter.had_error:
                sys.exit(65)
            if ErrorReporter.had_runtime_error:
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
                ErrorReporter.had_error = False
                ErrorReporter.had_runtime_error = False
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
