from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.lox_function import LoxFunction
from src.lox_instance import LoxInstance

if TYPE_CHECKING:
    from src.expr import Expr
    from src.interpreter import Interpreter
    from src.tokens import Token


@dataclass(frozen=True)
class FieldInfo:
    name: Token
    initializer: Expr | None
    mutable: bool


class LoxClass:
    def __init__(
        self,
        name: str,
        superclass: LoxClass | None,
        methods: dict[str, LoxFunction],
        fields: dict[str, FieldInfo],
    ) -> None:
        self._name = name
        self._superclass = superclass
        self._methods = methods
        self._fields = fields

    @property
    def name(self) -> str:
        return self._name

    @property
    def fields(self) -> dict[str, FieldInfo]:
        return self._fields

    def find_field(self, name: str) -> FieldInfo | None:
        if name in self._fields:
            return self._fields[name]

        if self._superclass is not None:
            return self._superclass.find_field(name)

        return None

    def find_method(self, name: str) -> LoxFunction | None:
        if name in self._methods:
            return self._methods[name]

        if self._superclass is not None:
            return self._superclass.find_method(name)

        return None

    def min_arity(self) -> int:
        initializer = self.find_method("init")
        if initializer is None:
            return 0

        return initializer.min_arity()

    def max_arity(self) -> int:
        initializer = self.find_method("init")
        if initializer is None:
            return 0

        return initializer.max_arity()

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        instance = LoxInstance(self)

        for field in self._fields.values():
            if field.initializer is not None:
                instance.initialize(field, interpreter.evaluate(field.initializer))

        initializer = self.find_method("init")
        if initializer is not None:
            initializer.bind(instance).call(interpreter, arguments)

        instance.assert_initialized()

        return instance

    def __str__(self) -> str:
        return self._name
