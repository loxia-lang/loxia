from __future__ import annotations

from typing import TYPE_CHECKING

from src.environment import Environment
from src.errors import ReturnSignal
from src.expr import Lambda
from src.stmt import Function

if TYPE_CHECKING:
    from src.interpreter import Interpreter
    from src.lox_instance import LoxInstance


class LoxFunction:
    """Função declarada pelo usuário, com closure sobre o ambiente de declaração."""

    def __init__(
        self,
        declaration: Function | Lambda,
        closure: Environment,
        is_initializer: bool,
    ) -> None:
        self._declaration = declaration
        self._closure = closure
        self._is_initializer = is_initializer

    def bind(self, instance: LoxInstance) -> LoxFunction:
        environment = Environment(self._closure)
        environment.define("this", instance)
        return LoxFunction(self._declaration, environment, self._is_initializer)

    def min_arity(self) -> int:
        return sum(1 for param in self._declaration.params if param.default is None)

    def max_arity(self) -> int:
        return len(self._declaration.params)

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        environment = Environment(self._closure)
        for index, param in enumerate(self._declaration.params):
            if index < len(arguments):
                value = arguments[index]
            else:
                assert param.default is not None
                value = interpreter.evaluate(param.default)

            environment.define(param.name.lexeme, value, param.mutable)

        try:
            interpreter.execute_block(self._declaration.body, environment)
        except ReturnSignal as return_value:
            if self._is_initializer:
                return self._closure.get_at(0, "this")

            return return_value.value

        if self._is_initializer:
            return self._closure.get_at(0, "this")

        return None

    def __str__(self) -> str:
        if isinstance(self._declaration, Lambda):
            return "<lambda>"

        return f"<fn {self._declaration.name.lexeme}>"
