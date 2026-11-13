"""Formatação dos valores da linguagem (usada pelo interpretador e por debug)."""

from __future__ import annotations

import math

from src.execution.lox_list import LoxList
from src.execution.lox_map import LoxMap
from src.execution.lox_tuple import LoxTuple
from src.execution.numeric import is_float, is_int


def stringify(value: object) -> str:
    return _stringify(value, set())


def repr_value(value: object) -> str:
    """Forma de debug: string sempre citada/escapada; o resto igual a `stringify`."""
    if isinstance(value, str):
        return _quote(value)

    return _stringify(value, set())


def _stringify(value: object, stack: set[int]) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return str(value).lower()
    if is_int(value):
        return str(value)
    if is_float(value):
        return _stringify_float(value)
    if isinstance(value, LoxList):
        return _stringify_list(value, stack)
    if isinstance(value, LoxMap):
        return _stringify_map(value, stack)
    if isinstance(value, LoxTuple):
        return _stringify_tuple(value, stack)

    return str(value)


def _stringify_list(value: LoxList, stack: set[int]) -> str:
    identity = id(value)
    if identity in stack:
        return "[...]"

    stack.add(identity)
    try:
        parts = [_stringify_element(item, stack) for item in value.elements]
    finally:
        stack.remove(identity)

    return "[" + ", ".join(parts) + "]"


def _stringify_tuple(value: LoxTuple, stack: set[int]) -> str:
    identity = id(value)
    if identity in stack:
        return "(...)"

    stack.add(identity)
    try:
        parts = [_stringify_element(item, stack) for item in value.items]
    finally:
        stack.remove(identity)

    return "(" + ", ".join(parts) + ")"


def _stringify_map(value: LoxMap, stack: set[int]) -> str:
    identity = id(value)
    if identity in stack:
        return "{...}"

    stack.add(identity)
    try:
        parts = [
            f"{_stringify_element(key, stack)}: {_stringify_element(item, stack)}"
            for key, item in value.items
        ]
    finally:
        stack.remove(identity)

    return "{" + ", ".join(parts) + "}"


def _stringify_element(value: object, stack: set[int]) -> str:
    if isinstance(value, str):
        return _quote(value)

    return _stringify(value, stack)


def _quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("\0", "\\0")
    )
    return f'"{escaped}"'


def _stringify_float(value: float) -> str:
    """Representação curta que volta ao mesmo `double` (D-6)."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"

    # `repr` do Python é a menor string que faz round-trip e sempre distingue
    # Float de Int (`1.0`, não `1`).
    return repr(value)
