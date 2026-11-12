"""Montagem dos namespaces nativos globais."""

from __future__ import annotations

from src.native_module import NativeModule
from src.natives.math import (
    MathAbs,
    MathCeil,
    MathClamp,
    MathFloor,
    MathMax,
    MathMin,
    MathRound,
    MathSqrt,
    MathTrunc,
)
from src.natives.parse import FloatParse, IntParse


def int_module() -> NativeModule:
    return NativeModule("Int", {"parse": IntParse()})


def float_module() -> NativeModule:
    return NativeModule("Float", {"parse": FloatParse()})


def math_module() -> NativeModule:
    return NativeModule(
        "math",
        {
            "abs": MathAbs(),
            "min": MathMin(),
            "max": MathMax(),
            "clamp": MathClamp(),
            "floor": MathFloor(),
            "ceil": MathCeil(),
            "round": MathRound(),
            "trunc": MathTrunc(),
            "sqrt": MathSqrt(),
        },
    )
