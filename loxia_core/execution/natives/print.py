# SPDX-License-Identifier: MIT OR Apache-2.0
"""`print`: display form plus newline (docs: loxia/builtins_docs.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.execution.values import stringify

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Print:
    """Writes the display form and a newline, then returns `nil`.

    Uses the same `stringify` as interpolation, so strings print without quotes
    and container elements are formatted consistently.
    """

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        print(stringify(arguments[0]))
        return None

    def __str__(self) -> str:
        return "<native fn>"
