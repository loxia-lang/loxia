# SPDX-License-Identifier: MIT OR Apache-2.0
"""`str`: display representation (docs: loxia/builtins_docs.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.execution.values import stringify

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Str:
    """Returns the display representation.

    Strings are returned unchanged; other values match `print` without the
    trailing newline.
    """

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return stringify(arguments[0])

    def __str__(self) -> str:
        return "<native fn>"
