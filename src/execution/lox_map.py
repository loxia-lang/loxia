from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.diagnostics.codes import Code
from src.diagnostics.errors import LoxRuntimeError
from src.execution import numeric
from src.execution.lox_callable import LoxCallable
from src.execution.lox_list import LoxList
from src.frontend.tokens import Token

if TYPE_CHECKING:
    from src.execution.interpreter import Interpreter


@dataclass(frozen=True)
class _MapKey:
    """Chave canônica: separa `Bool` de `Int` e restringe os tipos aceitos."""

    tag: str
    value: object


def _canonical_key(key: object) -> _MapKey | None:
    if isinstance(key, bool):
        return _MapKey("bool", key)
    if numeric.is_int(key):
        return _MapKey("int", key)
    if isinstance(key, str):
        return _MapKey("string", key)

    return None


class LoxMap:
    """Mapa mutável da linguagem.

    A ordem de inserção é preservada (o `dict` do Python já faz isso) porque I3 exige
    iteração determinística. O tipo da chave/valor é apagado em runtime; a checagem de
    tipo é contrato do checker. `version` detecta mutação durante a iteração.
    """

    def __init__(self) -> None:
        self._entries: dict[_MapKey, object] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def items(self) -> list[tuple[object, object]]:
        return [(key.value, value) for key, value in self._entries.items()]

    def keys(self) -> list[object]:
        return [key.value for key in self._entries]

    def values(self) -> list[object]:
        return list(self._entries.values())

    def get(self, key: object, token: Token) -> object:
        wrapped = self._require_key(key, token)
        if wrapped not in self._entries:
            raise LoxRuntimeError(
                token, "Key not found in map.", code=Code.KEY_NOT_FOUND
            )

        return self._entries[wrapped]

    def get_or_nil(self, key: object, token: Token) -> object:
        wrapped = self._require_key(key, token)
        return self._entries.get(wrapped)

    def has(self, key: object, token: Token) -> bool:
        wrapped = self._require_key(key, token)
        return wrapped in self._entries

    def set(self, key: object, value: object, token: Token) -> object:
        wrapped = self._require_key(key, token)
        self._entries[wrapped] = value
        self._version += 1
        return value

    def remove(self, key: object, token: Token) -> object:
        wrapped = self._require_key(key, token)
        if wrapped not in self._entries:
            raise LoxRuntimeError(
                token, "Key not found in map.", code=Code.KEY_NOT_FOUND
            )

        self._version += 1
        return self._entries.pop(wrapped)

    def find(self, key: object) -> tuple[bool, object]:
        """Consulta interna da igualdade; a chave veio de outro `LoxMap`."""
        wrapped = _canonical_key(key)
        if wrapped is None or wrapped not in self._entries:
            return False, None

        return True, self._entries[wrapped]

    def get_method(self, name: Token) -> LoxCallable:
        if name.lexeme == "get":
            return MapGetMethod(self, name)
        if name.lexeme == "has":
            return MapHasMethod(self, name)
        if name.lexeme == "remove":
            return MapRemoveMethod(self, name)
        if name.lexeme == "keys":
            return MapKeysMethod(self)
        if name.lexeme == "values":
            return MapValuesMethod(self)

        raise LoxRuntimeError(
                name,
                f"Undefined property '{name.lexeme}'.",
                code=Code.UNDEFINED_PROPERTY,
            )

    def _require_key(self, key: object, token: Token) -> _MapKey:
        wrapped = _canonical_key(key)
        if wrapped is None:
            raise LoxRuntimeError(
                token,
                "Map keys must be strings, integers or booleans.",
                code=Code.INVALID_VALUE,
            )

        return wrapped

    def __str__(self) -> str:
        return "<map>"


class MapGetMethod:
    """`m.get(k)` — devolve `nil` quando a chave não existe."""

    def __init__(self, target: LoxMap, token: Token) -> None:
        self._target = target
        self._token = token

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return self._target.get_or_nil(arguments[0], self._token)

    def __str__(self) -> str:
        return "<native fn>"


class MapHasMethod:
    """`m.has(k)` — `Bool`; não confunde chave ausente com valor `nil`."""

    def __init__(self, target: LoxMap, token: Token) -> None:
        self._target = target
        self._token = token

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return self._target.has(arguments[0], self._token)

    def __str__(self) -> str:
        return "<native fn>"


class MapRemoveMethod:
    """`m.remove(k)` — remove e devolve o valor; chave ausente é erro."""

    def __init__(self, target: LoxMap, token: Token) -> None:
        self._target = target
        self._token = token

    def min_arity(self) -> int:
        return 1

    def max_arity(self) -> int:
        return 1

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return self._target.remove(arguments[0], self._token)

    def __str__(self) -> str:
        return "<native fn>"


class MapKeysMethod:
    """`m.keys()` — snapshot das chaves na ordem de inserção."""

    def __init__(self, target: LoxMap) -> None:
        self._target = target

    def min_arity(self) -> int:
        return 0

    def max_arity(self) -> int:
        return 0

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return LoxList(self._target.keys())

    def __str__(self) -> str:
        return "<native fn>"


class MapValuesMethod:
    """`m.values()` — snapshot dos valores na ordem de inserção."""

    def __init__(self, target: LoxMap) -> None:
        self._target = target

    def min_arity(self) -> int:
        return 0

    def max_arity(self) -> int:
        return 0

    def call(self, interpreter: Interpreter, arguments: list[object]) -> object:
        return LoxList(self._target.values())

    def __str__(self) -> str:
        return "<native fn>"
