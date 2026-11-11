import sys

from src.errors import LoxRuntimeError
from src.token_type import TokenType
from src.tokens import Token


class ErrorReporter:
    """Coleta e imprime os diagnósticos de **uma** execução.

    Não há estado global: cada `Lox.run` cria a sua instância e a injeta no scanner,
    no parser e no interpretador. Assim um erro do REPL (ou de um teste) nunca vaza
    para a execução seguinte.
    """

    def __init__(self) -> None:
        self.had_error: bool = False
        self.had_runtime_error: bool = False
        self.silent: bool = False

    def error(self, target: Token | int, message: str) -> None:
        if isinstance(target, int):
            self.report(target, "", message)
        elif target.type == TokenType.EOF:
            self.report(target.line, " at end", message)
        else:
            self.report(target.line, f" at '{target.lexeme}'", message)

    def runtime_error(self, error: LoxRuntimeError) -> None:
        print(f"{error.message}\n[line {error.token.line}]", file=sys.stderr)
        self.had_runtime_error = True

    def report(self, line: int, where: str, message: str) -> None:
        self.had_error = True
        if self.silent:
            return

        print(f"[line {line}] Error{where}: {message}", file=sys.stderr)

    def reset(self) -> None:
        self.had_error = False
        self.had_runtime_error = False
        self.silent = False

    @property
    def has_error(self) -> bool:
        """Houve erro de sintaxe/resolução ou de runtime nesta execução?"""
        return self.had_error or self.had_runtime_error
