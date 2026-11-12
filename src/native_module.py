"""Namespace nativo somente leitura para `Int`, `Float` e `math`."""

from __future__ import annotations


class NativeModule:
    """Objeto global com membros estáticos (ex.: `Int.parse`, `math.sqrt`)."""

    def __init__(self, name: str, members: dict[str, object]) -> None:
        self.name = name
        self._members = dict(members)

    def get(self, name: str) -> object | None:
        return self._members.get(name)

    def __str__(self) -> str:
        return f"<native module {self.name}>"
