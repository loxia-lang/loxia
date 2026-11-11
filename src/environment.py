from __future__ import annotations

from src.errors import LoxRuntimeError
from src.token import Token


class Environment:
    def __init__(self, enclosing: Environment | None = None):
        self.values: dict[str, object] = {}
        self.enclosing: Environment | None = enclosing

    def define(self, name: str, value: object) -> None:
        self.values[name] = value

    def get(self, name: Token) -> object:
        if name.lexeme not in self.values:
            raise LoxRuntimeError(name, f"Undefined variable '{name.lexeme}'.")

        if self.enclosing is not None:
            return self.enclosing.get(name)

        return self.values[name.lexeme]

    def assign(self, name: Token, value: object) -> None:
        if name.lexeme not in self.values:
            raise LoxRuntimeError(name, f"Undefined variable '{name.lexeme}'.")

        if self.enclosing is not None:
            self.enclosing.assign(name, value)

        self.values[name.lexeme] = value
