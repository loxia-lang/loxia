from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.lox_map import LoxMap
from loxia_core.execution.lox_tuple import LoxTuple

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Len:
    """`len(valor)` — tamanho de uma lista, de um mapa ou de uma string (code points)."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = arguments[0]
        if isinstance(value, LoxList):
            return len(value.elements)
        if isinstance(value, LoxMap):
            return value.size
        if isinstance(value, LoxTuple):
            return len(value.items)
        if isinstance(value, str):
            return len(value)

        raise NativeError("len() expects a string, a list or a map.")

    def __str__(self) -> str:
        return "<native fn>"
