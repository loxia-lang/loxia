# SPDX-License-Identifier: MIT OR Apache-2.0
"""`repr`: debug representation (docs: loxia/builtins_docs.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.execution.values import repr_value

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Repr:
    """Returns the debug representation.

    Strings are quoted and escaped; other values match `str`.
    """

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return repr_value(arguments[0])

    def __str__(self) -> str:
        return "<native fn>"
