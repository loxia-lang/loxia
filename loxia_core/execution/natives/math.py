# SPDX-License-Identifier: MIT OR Apache-2.0
"""Deterministic `math.*` builtins (public docs: loxia/builtins_docs.py).

`_number` validates the argument type and `_to_int` enforces the finite/i64-range
contract shared by `floor`, `ceil`, `round` and `trunc`. None of these functions
consult locale or host state.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution import numeric

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


def _number(value: object, name: str) -> int | float:
    if not numeric.is_number(value):
        raise NativeError(f"{name}() expects numbers.")
    return value


def _to_int(value: float, name: str) -> int:
    if not math.isfinite(value):
        raise NativeError(f"{name}() requires a finite Float in Int range.")

    result = math.trunc(value)
    if not numeric.INT_MIN <= result <= numeric.INT_MAX:
        raise NativeError(f"{name}() requires a finite Float in Int range.")

    return result


class MathAbs:
    """`math.abs` — keeps Int/Float; Int negation honors `--debug` overflow."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = _number(arguments[0], "math.abs")
        if numeric.is_int(value):
            if value < 0:
                return numeric.negate(value, checked=interpreter.checked_overflow)
            return value
        return abs(value)

    def __str__(self) -> str:
        return "<native fn>"


class MathMin:
    """`math.min` — promotes to Float and propagates NaN."""

    def min_arity(self) -> int:
        return 2

    def max_arity(self) -> int:
        return 2

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        left = _number(arguments[0], "math.min")
        right = _number(arguments[1], "math.min")
        if numeric.is_float(left) or numeric.is_float(right):
            if math.isnan(float(left)) or math.isnan(float(right)):
                return float("nan")
            return min(float(left), float(right))
        assert numeric.is_int(left) and numeric.is_int(right)
        return min(left, right)

    def __str__(self) -> str:
        return "<native fn>"


class MathMax:
    """`math.max` — promotes to Float and propagates NaN."""

    def min_arity(self) -> int:
        return 2

    def max_arity(self) -> int:
        return 2

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        left = _number(arguments[0], "math.max")
        right = _number(arguments[1], "math.max")
        if numeric.is_float(left) or numeric.is_float(right):
            if math.isnan(float(left)) or math.isnan(float(right)):
                return float("nan")
            return max(float(left), float(right))
        assert numeric.is_int(left) and numeric.is_int(right)
        return max(left, right)

    def __str__(self) -> str:
        return "<native fn>"


class MathClamp:
    """`math.clamp` — requires `low <= high`; promotes and propagates NaN."""

    def min_arity(self) -> int:
        return 3

    def max_arity(self) -> int:
        return 3

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = _number(arguments[0], "math.clamp")
        low = _number(arguments[1], "math.clamp")
        high = _number(arguments[2], "math.clamp")
        if math.isnan(float(value)) or math.isnan(float(low)) or math.isnan(float(high)):
            return float("nan")
        if low > high:
            raise NativeError("math.clamp() requires low <= high.")

        if numeric.is_float(value) or numeric.is_float(low) or numeric.is_float(high):
            return min(max(float(value), float(low)), float(high))
        assert numeric.is_int(value) and numeric.is_int(low) and numeric.is_int(high)
        return min(max(value, low), high)

    def __str__(self) -> str:
        return "<native fn>"


class MathFloor:
    """`math.floor` — Int unchanged; Float must be finite and fit in i64."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = _number(arguments[0], "math.floor")
        if numeric.is_int(value):
            return value
        if not math.isfinite(float(value)):
            raise NativeError("math.floor() requires a finite Float in Int range.")
        return _to_int(math.floor(value), "math.floor")

    def __str__(self) -> str:
        return "<native fn>"


class MathCeil:
    """`math.ceil` — Int unchanged; Float must be finite and fit in i64."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = _number(arguments[0], "math.ceil")
        if numeric.is_int(value):
            return value
        if not math.isfinite(float(value)):
            raise NativeError("math.ceil() requires a finite Float in Int range.")
        return _to_int(math.ceil(value), "math.ceil")

    def __str__(self) -> str:
        return "<native fn>"


class MathRound:
    """`math.round` — ties away from zero; Float must be finite and fit in i64."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = _number(arguments[0], "math.round")
        if numeric.is_int(value):
            return value
        if not math.isfinite(value):
            raise NativeError("math.round() requires a finite Float in Int range.")
        rounded = math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)
        return _to_int(rounded, "math.round")

    def __str__(self) -> str:
        return "<native fn>"


class MathTrunc:
    """`math.trunc` — toward zero; Float must be finite and fit in i64."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = _number(arguments[0], "math.trunc")
        if numeric.is_int(value):
            return value
        return _to_int(value, "math.trunc")

    def __str__(self) -> str:
        return "<native fn>"


class MathSqrt:
    """`math.sqrt` — promotes Int to Float; negative input returns NaN."""

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = _number(arguments[0], "math.sqrt")
        number = float(value)
        if number < 0:
            return float("nan")
        return math.sqrt(number)

    def __str__(self) -> str:
        return "<native fn>"
