from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.interpreter import Interpreter


@runtime_checkable
class LoxCallable(Protocol):
    """Algo que pode ser chamado com `(...)`: funções de usuário e nativas."""

    def arity(self) -> int: ...

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object: ...
