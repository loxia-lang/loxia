# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loxia_core.execution.lox_function import LoxFunction


class LoxInterface:
    """Interface nominal em runtime (ADR-0080).

    O valor de uma variável de tipo interface é sempre a instância concreta; este objeto
    guarda só os métodos default, ligados ao ambiente onde a interface foi declarada.
    """

    def __init__(
        self,
        name: str,
        defaults: dict[str, LoxFunction],
        *,
        canonical: str | None = None,
    ) -> None:
        self._name = name
        # O loader renomeia a interface importada no `is`/`as` (`mod$lib$I`), mas o
        # token de `implements` guarda o nome de exibição; o runtime precisa aceitar
        # os dois (ADR-0146).
        self._canonical = canonical or name
        self._defaults = defaults

    @property
    def name(self) -> str:
        return self._name

    @property
    def canonical_name(self) -> str:
        return self._canonical

    def matches(self, name: str) -> bool:
        return name == self._name or name == self._canonical

    def find_method(self, name: str) -> LoxFunction | None:
        return self._defaults.get(name)

    def __str__(self) -> str:
        return self._name
