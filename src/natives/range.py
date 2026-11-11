from __future__ import annotations

from typing import TYPE_CHECKING

from src.errors import NativeError
from src.lox_range import LoxRange
from src.numeric import is_int

if TYPE_CHECKING:
    from src.interpreter import Interpreter


class RangeNative:
    """`range(start, end, step)` — devolve um `LoxRange` lazy e reutilizável."""

    def arity(self) -> int:
        return 3

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        values: list[int] = []
        for argument in arguments:
            if not is_int(argument):
                raise NativeError("range() arguments must be integers.")

            values.append(argument)

        start, end, step = values
        if step == 0:
            raise NativeError("range() step can't be zero.")

        return LoxRange(start, end, step)

    def __str__(self) -> str:
        return "<native fn>"
