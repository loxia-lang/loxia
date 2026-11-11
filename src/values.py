"""Formatação dos valores da linguagem (usada pelo interpretador e por debug)."""

from __future__ import annotations


def stringify(value: object) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)

    return str(value)
