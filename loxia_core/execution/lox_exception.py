# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loxia_core.execution.lox_class import FieldInfo, LoxClass
from loxia_core.frontend.expr import Literal
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


@dataclass(frozen=True, eq=False)
class LoxExceptionValue:
    """Instância de uma exceção embutida (`Exception`/`RuntimeError`)."""

    type_name: str
    message: str
    site: str = ""

    def is_instance_of(self, name: str) -> bool:
        return name in ("Exception", self.type_name)


def format_site(file: str | None, line: int, column: int | None) -> str:
    """`arquivo:linha:coluna` relativo, ou `""` quando não há posição (I3)."""
    if not file or line <= 0:
        return ""
    return f"{file}:{line}:{column or 1}"


def _message_field() -> FieldInfo:
    token = Token(TokenType.IDENTIFIER, "message", None, 0)
    return FieldInfo(token, None, False)


def _site_field() -> FieldInfo:
    token = Token(TokenType.IDENTIFIER, "site", None, 0)
    return FieldInfo(token, Literal("", token), False)


class LoxExceptionClass(LoxClass):
    """Classe nativa de exceção; chamar com uma `String` cria um valor."""

    def __init__(self, name: str, superclass: LoxClass | None) -> None:
        super().__init__(
            name,
            superclass,
            {},
            {"message": _message_field(), "site": _site_field()},
        )

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        message = arguments[0]
        return LoxExceptionValue(self.name, str(message), interpreter.current_site())
