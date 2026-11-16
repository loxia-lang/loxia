from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


@dataclass(frozen=True, eq=False)
class LoxEnumValue:
    """Valor de enum: nome do enum, variante e payload imutável."""

    enum: str
    variant: str
    payload: tuple[object, ...] = ()
    key: str = ""


class LoxEnumVariant:
    """Construtor de uma variante com payload (`Shape.Circle`)."""

    def __init__(
        self, enum: str, variant: str, arity: int, key: str = ""
    ) -> None:
        self.enum = enum
        self.variant = variant
        self._arity = arity
        self.key = key

    def min_arity(self) -> int:
        return self._arity

    def max_arity(self) -> int:
        return self._arity

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return LoxEnumValue(
            self.enum, self.variant, tuple(arguments), self.key
        )


class LoxEnumObject:
    """Namespace de variantes (`Cor`, `Result`)."""

    def __init__(
        self, name: str, arities: dict[str, int], key: str | None = None
    ) -> None:
        self.name = name
        self.key = key or name
        self._variants: dict[str, object] = {}
        for variant, arity in arities.items():
            if arity == 0:
                self._variants[variant] = LoxEnumValue(
                    name, variant, (), self.key
                )
            else:
                self._variants[variant] = LoxEnumVariant(
                    name, variant, arity, self.key
                )

    def get(self, variant: str) -> object | None:
        return self._variants.get(variant)

    def __str__(self) -> str:
        return f"<enum {self.name}>"


def is_enum_value(value: object) -> bool:
    return isinstance(value, LoxEnumValue)
