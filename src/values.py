"""Formatação dos valores da linguagem (usada pelo interpretador e por debug)."""

from __future__ import annotations

import math

from src.numeric import is_float, is_int


def stringify(value: object) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return str(value).lower()
    if is_int(value):
        return str(value)
    if is_float(value):
        return _stringify_float(value)

    return str(value)


def _stringify_float(value: float) -> str:
    """Representação curta que volta ao mesmo `double` (D-6)."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"

    # `repr` do Python é a menor string que faz round-trip e sempre distingue
    # Float de Int (`1.0`, não `1`).
    return repr(value)
