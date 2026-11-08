import argparse
import sys


class Lox:

    def __init__(self):
        self.had_error: bool = False

    def run (self, source:str) -> None:
        # Quando você implementar o Scanner:
        # scanner = Scanner(source)
        # tokens:list = scanner.scan_tokens()
        # for token in tokens:
        #     print(token)

        print(f"Executando:\n{source}")

    def run_file(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as file:
                source = file.read()
            self.run(source)

            if (self.hadError): sys.exit(65)
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
                self.hadError = False
            except (KeyboardInterrupt, EOFError):
                print("\nSaindo...")
                break
    
    @classmethod
    def error (cls, line: int, message: str)-> None:
        cls.report(line, "", message)

    def report (self, line:int, where: str, message:str) -> None:
        print(f"[line {line}] Error{where}: {message}", file=sys.stderr)
        self.had_error = True

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pylox",
        description="Interpretador Lox em Python",
        usage="%(prog)s [script]",
    )

    # nargs="?" indica argumento opcional (0 ou 1 valor)
    parser.add_argument("script", nargs="?", help="Caminho para o script Lox")

    parsed_args = parser.parse_args()

    lox = Lox()

    if parsed_args.script:
        lox.run_file(parsed_args.script)
    else:
        lox.run_prompt()


if __name__ == "__main__":
    main()