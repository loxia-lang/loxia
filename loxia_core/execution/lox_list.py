# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

from typing import TYPE_CHECKING

from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.errors import LoxRuntimeError
from loxia_core.execution import numeric
from loxia_core.execution.lox_callable import LoxCallable
from loxia_core.frontend.tokens import Token

if TYPE_CHECKING:
    from loxia_core.execution.interpreter import Interpreter


class LoxList:
    """Lista mutável da linguagem.

    O tipo do elemento é apagado em runtime (como no resto da linguagem); a
    homogeneidade é contrato do checker. `version` existe para o `for-in` detectar
    mutação durante a iteração e falhar de forma explícita, em vez de iterar sobre
    um estado imprevisível.
    """

    def __init__(self, elements: list[object] | None = None) -> None:
        self._elements: list[object] = [] if elements is None else elements
        self._version = 0

    @property
    def elements(self) -> list[object]:
        return self._elements

    @property
    def version(self) -> int:
        return self._version

    def push(self, value: object) -> None:
        self._elements.append(value)
        self._version += 1

    def pop(self, token: Token) -> object:
        if not self._elements:
            raise LoxRuntimeError(
                token, "Can't pop from an empty list.", code=Code.INDEX_OUT_OF_BOUNDS
            )

        self._version += 1
        return self._elements.pop()

    def get(self, index: object, token: Token) -> object:
        position = self._check_index(index, token)
        return self._elements[position]

    def set(self, index: object, value: object, token: Token) -> object:
        position = self._check_index(index, token)
        self._elements[position] = value
        self._version += 1
        return value

    def get_method(self, name: Token) -> LoxCallable:
        if name.lexeme == "push":
            return ListPushMethod(self)
        if name.lexeme == "pop":
            return ListPopMethod(self, name)

        raise LoxRuntimeError(
            name,
            f"Undefined property '{name.lexeme}'.",
            code=Code.UNDEFINED_PROPERTY,
        )

    def _check_index(self, index: object, token: Token) -> int:
        if not numeric.is_int(index):
            raise LoxRuntimeError(
                token, "List index must be an integer.", code=Code.RUNTIME_OPERANDS
            )

        length = len(self._elements)
        if index < 0 or index >= length:
            raise LoxRuntimeError(
                token,
                f"List index {index} out of bounds for length {length}.",
                code=Code.INDEX_OUT_OF_BOUNDS,
            )

        return index

    def __str__(self) -> str:
        return "<list>"


class ListPushMethod:
    """`xs.push(valor)` — muta a lista e devolve `nil`."""

    def __init__(self, target: LoxList) -> None:
        self._target = target

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        self._target.push(arguments[0])
        return None

    def __str__(self) -> str:
        return "<native fn>"


class ListPopMethod:
    """`xs.pop()` — remove e devolve o último elemento; lista vazia é erro."""

    def __init__(self, target: LoxList, token: Token) -> None:
        self._target = target
        self._token = token

    def min_arity(self) -> int:
        return 0

    def max_arity(self) -> int:
        return 0

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return self._target.pop(self._token)

    def __str__(self) -> str:
        return "<native fn>"
