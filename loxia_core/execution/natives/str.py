from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.execution.values import stringify

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Str:
    """`str(valor)` — representação de exibição, sem aspas em string."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return stringify(arguments[0])

    def __str__(self) -> str:
        return "<native fn>"
