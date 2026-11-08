import sys

from src.token import Token
from src.token_type import TokenType


class ErrorReporter:
    had_error: bool = False

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
    def report(cls, line: int, where: str, message: str) -> None:
        print(f"[line {line}] Error{where}: {message}", file=sys.stderr)
        cls.had_error = True

    @classmethod
    def reset(cls) -> None:
        cls.had_error = False
