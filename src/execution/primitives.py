"""Tabela única das primitivas monomórficas do kernel (ADR-0071).

Cada entrada liga a assinatura Lox (`lox`), o símbolo C (`c_symbol`), os tipos da
tabela e o corpo Python que serve de oráculo. O checker, o interpretador e o backend
consomem esta tabela; não há regra de tipo duplicada por nome.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.diagnostics.errors import NativeError
from src.execution.lox_list import LoxList
from src.frontend.ty import INT, STRING, ListTy, Ty


def _substr(text: str, start: int, end: int) -> str:
    if start < 0 or end < start or end > len(text):
        raise NativeError("substr() index out of bounds.")
    return text[start:end]


def _join(parts: LoxList, separator: str) -> str:
    values: list[str] = []
    for item in parts.elements:
        if not isinstance(item, str):
            raise NativeError("join() expects List[String].")
        values.append(item)
    return separator.join(values)


def _char_code_at(text: str, index: int) -> int:
    if index < 0 or index >= len(text):
        raise NativeError("charCodeAt() index out of bounds.")
    return ord(text[index])


def _from_code_point(code_point: int) -> str:
    if (
        code_point < 0
        or code_point > 0x10FFFF
        or 0xD800 <= code_point <= 0xDFFF
    ):
        raise NativeError("fromCodePoint() expects a valid Unicode code point.")
    return chr(code_point)


@dataclass(frozen=True)
class Primitive:
    lox: str
    c_symbol: str
    params: tuple[Ty, ...]
    result: Ty
    py: Callable[..., object]
    ambient: bool = False


PRIMITIVES: tuple[Primitive, ...] = (
    Primitive(
        "substr", "lox_substr", (STRING, INT, INT), STRING, _substr
    ),
    Primitive(
        "join", "lox_join", (ListTy(STRING), STRING), STRING, _join
    ),
    Primitive(
        "charCodeAt", "lox_char_code_at", (STRING, INT), INT, _char_code_at
    ),
    Primitive(
        "fromCodePoint", "lox_from_code_point", (INT,), STRING, _from_code_point
    ),
)

PRIMITIVE_BY_LOX: dict[str, Primitive] = {
    primitive.lox: primitive for primitive in PRIMITIVES
}


class PrimitiveCallable:
    """Adaptador do corpo Python para o protocolo `LoxCallable`."""

    def __init__(self, primitive: Primitive) -> None:
        self.primitive = primitive

    def min_arity(self) -> int:
        return len(self.primitive.params)

    def max_arity(self) -> int:
        return len(self.primitive.params)

    def call(self, interpreter: object, arguments: list[object]) -> object:
        return self.primitive.py(*arguments)

    def __str__(self) -> str:
        return "<native fn>"
