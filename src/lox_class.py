from __future__ import annotations

from typing import TYPE_CHECKING

from src.lox_function import LoxFunction
from src.lox_instance import LoxInstance

if TYPE_CHECKING:
    from src.interpreter import Interpreter


class LoxClass:
    def __init__(self, name: str, methods: dict[str, LoxFunction]) -> None:
        self._name = name
        self._methods = methods

    @property
    def name(self) -> str:
        return self._name

    def find_method(self, name: str) -> LoxFunction | None:
        return self._methods.get(name)

    def arity(self) -> int:
        initializer = self.find_method("init")
        if initializer is None:
            return 0

        return initializer.arity()

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        instance = LoxInstance(self)

        initializer = self.find_method("init")
        if initializer is not None:
            initializer.bind(instance).call(interpreter, arguments)

        return instance

    def __str__(self) -> str:
        return self._name
