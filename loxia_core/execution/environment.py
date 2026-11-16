from __future__ import annotations

from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.errors import LoxRuntimeError, immutable_assignment_message
from loxia_core.frontend.tokens import Token


class Environment:
    def __init__(self, enclosing: Environment | None = None):
        self.values: dict[str, object] = {}
        self.enclosing: Environment | None = enclosing
        self._mutable: dict[str, bool] = {}

    def define(self, name: str, value: object, mutable: bool = True) -> None:
        self.values[name] = value
        self._mutable[name] = mutable

    def is_mutable(self, name: str) -> bool:
        return self._mutable.get(name, True)

    def get(self, name: Token) -> object:
        if name.lexeme in self.values:
            return self.values[name.lexeme]

        if self.enclosing is not None:
            return self.enclosing.get(name)

        raise LoxRuntimeError(
                name,
                f"Undefined variable '{name.lexeme}'.",
                code=Code.UNDEFINED_VARIABLE,
            )

    def assign(self, name: Token, value: object) -> None:
        if name.lexeme in self.values:
            if not self.is_mutable(name.lexeme):
                raise LoxRuntimeError(
                    name,
                    immutable_assignment_message(name.lexeme),
                    code=Code.RUNTIME_IMMUTABLE,
                )

            self.values[name.lexeme] = value
            return

        if self.enclosing is not None:
            self.enclosing.assign(name, value)
            return

        raise LoxRuntimeError(
                name,
                f"Undefined variable '{name.lexeme}'.",
                code=Code.UNDEFINED_VARIABLE,
            )

    def get_at(self, distance: int, name: str) -> object:
        return self.ancestor(distance).values[name]

    def assign_at(self, distance: int, name: Token, value: object) -> None:
        target = self.ancestor(distance)
        if not target.is_mutable(name.lexeme):
            raise LoxRuntimeError(
                    name,
                    immutable_assignment_message(name.lexeme),
                    code=Code.RUNTIME_IMMUTABLE,
                )

        target.values[name.lexeme] = value

    def ancestor(self, distance: int) -> Environment:
        environment = self
        for _ in range(distance):
            assert environment.enclosing is not None
            environment = environment.enclosing
        return environment
