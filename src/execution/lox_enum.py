from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.execution.interpreter import Interpreter


@dataclass(frozen=True, eq=False)
class LoxEnumValue:
    """Valor de enum: nome do enum, variante e payload imutável."""

    enum: str
    variant: str
    payload: tuple[object, ...] = ()


class LoxEnumVariant:
    """Construtor de uma variante com payload (`Shape.Circle`)."""

    def __init__(self, enum: str, variant: str, arity: int) -> None:
        self.enum = enum
        self.variant = variant
        self._arity = arity

    def min_arity(self) -> int:
        return self._arity

    def max_arity(self) -> int:
        return self._arity

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return LoxEnumValue(self.enum, self.variant, tuple(arguments))


class LoxEnumObject:
    """Namespace de variantes (`Cor`, `Result`)."""

    def __init__(self, name: str, arities: dict[str, int]) -> None:
        self.name = name
        self._variants: dict[str, object] = {}
        for variant, arity in arities.items():
            if arity == 0:
                self._variants[variant] = LoxEnumValue(name, variant)
            else:
                self._variants[variant] = LoxEnumVariant(name, variant, arity)

    def get(self, variant: str) -> object | None:
        return self._variants.get(variant)

    def __str__(self) -> str:
        return f"<enum {self.name}>"


def is_enum_value(value: object) -> bool:
    return isinstance(value, LoxEnumValue)
