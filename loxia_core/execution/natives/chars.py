# SPDX-License-Identifier: MIT OR Apache-2.0
"""`chars`: split a string into one-code-point strings (docs: loxia/builtins_docs.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution.lox_list import LoxList

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class Chars:
    """Returns a `List[String]` with one element per Unicode code point.

    A non-string argument raises `NativeError`; the empty string yields `[]`.
    """

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        value = arguments[0]
        if not isinstance(value, str):
            raise NativeError("chars() expects a string.")

        return LoxList(list(value))

    def __str__(self) -> str:
        return "<native fn>"
