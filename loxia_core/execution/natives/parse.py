# SPDX-License-Identifier: MIT OR Apache-2.0
"""`Int.parse`/`Float.parse`: conversão explícita de texto, sem crash."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution import numeric

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter

_INT_RE = re.compile(r"[+-]?[0-9]+")
_FLOAT_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


class IntParse:
    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        text = arguments[0]
        if not isinstance(text, str):
            raise NativeError("Int.parse() expects a string.")
        if _INT_RE.fullmatch(text) is None:
            return None

        value = int(text)
        if not numeric.INT_MIN <= value <= numeric.INT_MAX:
            return None

        return value

    def __str__(self) -> str:
        return "<native fn>"


class FloatParse:
    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        text = arguments[0]
        if not isinstance(text, str):
            raise NativeError("Float.parse() expects a string.")
        if _FLOAT_RE.fullmatch(text) is None:
            return None

        value = float(text)
        if not math.isfinite(value):
            return None

        return value

    def __str__(self) -> str:
        return "<native fn>"
