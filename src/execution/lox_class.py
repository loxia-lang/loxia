from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.execution.lox_function import LoxFunction
from src.execution.lox_instance import LoxInstance

if TYPE_CHECKING:
    from src.execution.interpreter import Interpreter
    from src.execution.lox_interface import LoxInterface
    from src.frontend.expr import Expr
    from src.frontend.tokens import Token


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
        interfaces: list[LoxInterface] | None = None,
    ) -> None:
        self._name = name
        self._superclass = superclass
        self._methods = methods
        self._fields = fields
        self._interfaces = list(interfaces or [])

    @property
    def name(self) -> str:
        return self._name

    @property
    def interfaces(self) -> list[LoxInterface]:
        return self._interfaces

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
        method = self._find_class_method(name)
        if method is not None:
            return method

        return self._find_interface_method(name)

    def _find_class_method(self, name: str) -> LoxFunction | None:
        if name in self._methods:
            return self._methods[name]

        if self._superclass is not None:
            return self._superclass._find_class_method(name)

        return None

    def _find_interface_method(self, name: str) -> LoxFunction | None:
        for interface in self._interfaces:
            method = interface.find_method(name)
            if method is not None:
                return method

        if self._superclass is not None:
            return self._superclass._find_interface_method(name)

        return None

    def is_subclass_of(self, name: str) -> bool:
        klass: LoxClass | None = self
        while klass is not None:
            if klass.name == name:
                return True
            klass = klass._superclass

        return False

    def is_subclass_of_class(self, klass: LoxClass) -> bool:
        """Identidade por objeto de classe (ADR-0044)."""
        current: LoxClass | None = self
        while current is not None:
            if current is klass:
                return True
            current = current._superclass

        return False

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
