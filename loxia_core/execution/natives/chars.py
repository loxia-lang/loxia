from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution.lox_list import LoxList

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Chars:
    """`chars(s)` — code points da string, cada um como `String` de 1 cp."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = arguments[0]
        if not isinstance(value, str):
            raise NativeError("chars() expects a string.")

        return LoxList(list(value))

    def __str__(self) -> str:
        return "<native fn>"
