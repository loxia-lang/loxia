from __future__ import annotations

from typing import TYPE_CHECKING

from src.environment import Environment
from src.errors import ReturnSignal
from src.stmt import Function

if TYPE_CHECKING:
    from src.interpreter import Interpreter


class LoxFunction:
    """Função declarada pelo usuário, com closure sobre o ambiente de declaração."""

    def __init__(self, declaration: Function, closure: Environment) -> None:
        self._declaration = declaration
        self._closure = closure

    def arity(self) -> int:
        return len(self._declaration.params)

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        environment = Environment(self._closure)
        for param, argument in zip(self._declaration.params, arguments, strict=True):
            environment.define(param.lexeme, argument)

        try:
            interpreter.execute_block(self._declaration.body, environment)
        except ReturnSignal as return_value:
            return return_value.value

        return None

    def __str__(self) -> str:
        return f"<fn {self._declaration.name.lexeme}>"
