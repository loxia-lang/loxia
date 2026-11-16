from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, eq=False)
class LoxTuple:
    """Tupla imutável da linguagem: aridade fixa, elementos apagados em runtime."""

    items: tuple[object, ...]

    def __len__(self) -> int:
        return len(self.items)
