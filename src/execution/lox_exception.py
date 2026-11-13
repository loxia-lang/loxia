from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.execution.lox_class import FieldInfo, LoxClass
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token

if TYPE_CHECKING:
    from src.execution.interpreter import Interpreter


@dataclass(frozen=True, eq=False)
class LoxExceptionValue:
    """Instância de uma exceção embutida (`Exception`/`LoxRuntimeError`)."""

    type_name: str
    message: str

    def is_instance_of(self, name: str) -> bool:
        return name in ("Exception", self.type_name)


def _message_field() -> FieldInfo:
    token = Token(TokenType.IDENTIFIER, "message", None, 0)
    return FieldInfo(token, None, False)


class LoxExceptionClass(LoxClass):
    """Classe nativa de exceção; chamar com uma `String` cria um valor."""

    def __init__(self, name: str, superclass: LoxClass | None) -> None:
        super().__init__(name, superclass, {}, {"message": _message_field()})

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        message = arguments[0]
        return LoxExceptionValue(self.name, str(message))
