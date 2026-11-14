from __future__ import annotations

from typing import TYPE_CHECKING

from src.diagnostics.codes import Code
from src.diagnostics.errors import LoxRuntimeError
from src.frontend.tokens import Token

if TYPE_CHECKING:
    from src.execution.lox_class import FieldInfo, LoxClass


class LoxInstance:
    def __init__(self, klass: LoxClass) -> None:
        self._klass = klass
        self._fields: dict[str, object] = {}
        self._initialized: set[str] = set()

    def get(self, name: Token) -> object:
        if name.lexeme in self._fields:
            return self._fields[name.lexeme]

        method = self._klass.find_method(name.lexeme)
        if method is not None:
            return method.bind(self)

        raise LoxRuntimeError(
                name,
                f"Undefined property '{name.lexeme}'.",
                code=Code.UNDEFINED_PROPERTY,
            )

    def set(self, name: Token, value: object) -> None:
        field = self._klass.find_field(name.lexeme)
        if field is None:
            raise LoxRuntimeError(
                name,
                f"Undefined field '{name.lexeme}'.",
                code=Code.UNDEFINED_PROPERTY,
            )

        if not field.mutable and name.lexeme in self._initialized:
            raise LoxRuntimeError(
                name,
                f"Can't assign to immutable field '{name.lexeme}'.",
                code=Code.RUNTIME_IMMUTABLE,
            )

        self._fields[name.lexeme] = value
        self._initialized.add(name.lexeme)

    def initialize(self, field: FieldInfo, value: object) -> None:
        self._fields[field.name.lexeme] = value
        self._initialized.add(field.name.lexeme)

    def is_instance_of(self, name: str) -> bool:
        return self._klass.is_subclass_of(name)

    def is_instance_of_class(self, klass: LoxClass) -> bool:
        return self._klass.is_subclass_of_class(klass)

    def assert_initialized(self) -> None:
        for field in self._klass.fields.values():
            if field.name.lexeme not in self._initialized:
                raise LoxRuntimeError(
                    field.name,
                    f"Field '{field.name.lexeme}' must be initialized.",
                    code=Code.FIELD_NOT_INITIALIZED,
                )

    def __str__(self) -> str:
        if self.is_instance_of("Exception") and "message" in self._fields:
            return f"{self._klass.name}: {self._fields['message']}"

        return f"{self._klass.name} instance"
