from __future__ import annotations

from typing import TYPE_CHECKING

from src.errors import NativeError
from src.lox_list import LoxList
from src.lox_map import LoxMap

if TYPE_CHECKING:
    from src.interpreter import Interpreter


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
        if isinstance(value, str):
            return len(value)

        raise NativeError("len() expects a string, a list or a map.")

    def __str__(self) -> str:
        return "<native fn>"
