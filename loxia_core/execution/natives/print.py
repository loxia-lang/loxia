from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.execution.values import stringify

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Print:
    """`print(valor)` — escreve a representação de exibição e uma newline; devolve nil."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        print(stringify(arguments[0]))
        return None

    def __str__(self) -> str:
        return "<native fn>"
