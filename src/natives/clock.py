from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.interpreter import Interpreter


class Clock:
    """`clock()` nativa: segundos desde a época, como no livro."""

    def arity(self) -> int:
        return 0

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return time.time()

    def __str__(self) -> str:
        return "<native fn>"
