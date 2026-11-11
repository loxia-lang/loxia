import sys

from src.errors import LoxRuntimeError
from src.token import Token
from src.token_type import TokenType


class ErrorReporter:
    had_error: bool = False
    had_runtime_error: bool = False
    silent: bool = False  # Flag para testes do REPL

    @classmethod
    def error(cls, target: Token | int, message: str) -> None:
        if isinstance(target, int):
            cls.report(target, "", message)
        else:
            if target.type == TokenType.EOF:
                cls.report(target.line, " at end", message)
            else:
                cls.report(target.line, f" at '{target.lexeme}'", message)

    @classmethod
    def runtime_error(cls, error: LoxRuntimeError):
        print(f"{error.message}\n[line {error.token.line}]", file=sys.stderr)
        cls.had_runtime_error = True

    @classmethod
    def report(cls, line: int, where: str, message: str) -> None:
        cls.had_error = True
        if cls.silent:
            return

        print(f"[line {line}] Error{where}: {message}", file=sys.stderr)

    @classmethod
    def reset(cls) -> None:
        cls.had_error = False
