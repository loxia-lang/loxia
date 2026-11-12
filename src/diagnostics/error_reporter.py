import sys

from src.diagnostics.errors import LoxRuntimeError
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token


class ErrorReporter:
    """Coleta e imprime os diagnósticos de **uma** execução.

    Não há estado global: cada `Lox.run` cria a sua instância e a injeta no scanner,
    no parser e no interpretador. Assim um erro do REPL (ou de um teste) nunca vaza
    para a execução seguinte.
    """

    def __init__(self) -> None:
        self.had_error: bool = False
        self.had_fatal_error: bool = False
        self.had_runtime_error: bool = False
        self.silent: bool = False
        # No build, erro "rebaixável" vira panic site e não deve ser impresso agora.
        self.defer_lowerable: bool = False

    def error(
        self, target: Token | int, message: str, *, lowerable: bool = False
    ) -> None:
        """Registra um erro de compilação.

        `lowerable=True` marca o erro que o interpretador só levantaria em runtime (ex.:
        operandos de tipo errado). O backend pode rebaixá-lo a `lox_panic` e preservar
        stdout/exit code; os demais erros bloqueiam o build (ADR-0031, decisão 9).
        """
        if not lowerable:
            self.had_fatal_error = True
        elif self.defer_lowerable:
            self.had_error = True
            return

        if isinstance(target, int):
            self.report(target, "", message)
        elif target.type == TokenType.EOF:
            self.report(target.line, " at end", message)
        else:
            self.report(target.line, f" at '{target.lexeme}'", message)

    def runtime_error(self, error: LoxRuntimeError) -> None:
        print(f"{error.message}\n[line {error.token.line}]", file=sys.stderr)
        self.had_runtime_error = True

    def backend_error(self, line: int | None, message: str) -> None:
        """Erro de compilação do backend nativo (exit 65)."""
        self.had_error = True
        self.had_fatal_error = True
        location = f"[line {line}] " if line is not None else ""
        print(f"{location}Error: {message}", file=sys.stderr)

    def report(self, line: int, where: str, message: str) -> None:
        self.had_error = True
        if self.silent:
            return

        print(f"[line {line}] Error{where}: {message}", file=sys.stderr)

    def reset(self) -> None:
        self.had_error = False
        self.had_fatal_error = False
        self.had_runtime_error = False
        self.silent = False
        self.defer_lowerable = False

    @property
    def has_error(self) -> bool:
        """Houve erro de sintaxe/resolução ou de runtime nesta execução?"""
        return self.had_error or self.had_runtime_error
