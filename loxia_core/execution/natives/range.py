# SPDX-License-Identifier: MIT OR Apache-2.0
"""`range`: lazy, reusable integer range (docs: loxia/builtins_docs.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution.lox_range import LoxRange
from loxia_core.execution.numeric import is_int

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class RangeNative:
    """Returns a lazy, reusable `LoxRange`.

    All three arguments are required and must be `Int`; `step` cannot be zero.
    The two-argument `start..end` operator is parsed separately and uses step 1.
    """

    def min_arity(self) -> int:
        return 3

    def max_arity(self) -> int:
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
