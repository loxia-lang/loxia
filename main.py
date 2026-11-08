import argparse
import sys

from src.ast_printer import AstPrinter
from src.error_reporter import ErrorReporter
from src.parser import Parser
from src.scanner import Scanner


class Lox:
    def run(self, source: str) -> None:
        scanner = Scanner(source)
        tokens = scanner.scan_tokens()
        parser = Parser(tokens)
        expression = parser.parse()

        if ErrorReporter.had_error:
            return
        printer = AstPrinter()
        print(printer.print(expression))

    def run_file(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as file:
                source = file.read()
            self.run(source)

            if Lox.had_error:
                sys.exit(65)
        except FileNotFoundError:
            print(f"Erro: Arquivo '{path}' não encontrado.", file=sys.stderr)
            sys.exit(66)

    def run_prompt(self) -> None:
        print("PyLox REPL (Ctrl+C ou Ctrl+D para sair)")
        while True:
            try:
                line = input("> ")
                if not line:
                    break
                self.run(line)
                Lox.had_error = False
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
