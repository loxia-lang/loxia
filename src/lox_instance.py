from __future__ import annotations

from typing import TYPE_CHECKING

from src.errors import LoxRuntimeError
from src.tokens import Token

if TYPE_CHECKING:
    from src.lox_class import LoxClass


class LoxInstance:
    def __init__(self, klass: LoxClass) -> None:
        self._klass = klass
        self._fields: dict[str, object] = {}

    def get(self, name: Token) -> object:
        if name.lexeme in self._fields:
            return self._fields[name.lexeme]

        method = self._klass.find_method(name.lexeme)
        if method is not None:
            return method.bind(self)

        raise LoxRuntimeError(name, f"Undefined property '{name.lexeme}'.")

    def set(self, name: Token, value: object) -> None:
        self._fields[name.lexeme] = value

    def __str__(self) -> str:
        return f"{self._klass.name} instance"
