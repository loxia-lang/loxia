# SPDX-License-Identifier: MIT OR Apache-2.0
"""Assembly of the read-only `Int`, `Float` and `math` namespaces.

Public documentation lives in `loxia/builtins_docs.py`. The `io`, `fs`, `os`,
`time` and `process` namespaces are built from the primitive table in
`loxia_core/execution/primitives.py`, not here.
"""

from __future__ import annotations

from loxia_core.execution.native_module import NativeModule
from loxia_core.execution.natives.math import (
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
from loxia_core.execution.natives.parse import FloatParse, IntParse


def int_module() -> NativeModule:
    """Builds the `Int` namespace (`Int.parse`)."""
    return NativeModule("Int", {"parse": IntParse()})


def float_module() -> NativeModule:
    """Builds the `Float` namespace (`Float.parse`)."""
    return NativeModule("Float", {"parse": FloatParse()})


def math_module() -> NativeModule:
    """Builds the deterministic `math` namespace."""
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
