# SPDX-License-Identifier: MIT OR Apache-2.0
"""Valor `Bytes` e a superfície de `Bytes` no interpretador (ADR-0125).

O valor em runtime é `bytes` do Python: imutável, contíguo e com igualdade/hash
estruturais. Este módulo concentra o namespace estático, os métodos do valor e a classe
`BytesError`; o checker lê as assinaturas de `bytes_api.py`.
"""

from __future__ import annotations

import base64
import binascii

from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.errors import LoxRuntimeError, NativeError
from loxia_core.execution import numeric
from loxia_core.execution.bytes_api import BYTES_METHODS, BYTES_STATICS
from loxia_core.execution.lox_class import FieldInfo, LoxClass
from loxia_core.execution.lox_enum import LoxEnumValue
from loxia_core.execution.lox_instance import LoxInstance
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.native_module import NativeModule
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def make_ok(value: object) -> LoxEnumValue:
    return LoxEnumValue("Result", "Ok", (value,), "Result")


def make_err(error: object) -> LoxEnumValue:
    return LoxEnumValue("Result", "Err", (error,), "Result")


class BytesErrorClass(LoxClass):
    """Classe built-in `BytesError(kind, message)` (sem import)."""

    def __init__(self) -> None:
        self._kind_token = Token(TokenType.IDENTIFIER, "kind", None, 0)
        self._message_token = Token(TokenType.IDENTIFIER, "message", None, 0)
        super().__init__(
            "BytesError",
            None,
            {},
            {
                "kind": FieldInfo(self._kind_token, None, False),
                "message": FieldInfo(self._message_token, None, False),
            },
        )

    def make(self, kind: str, message: str) -> LoxInstance:
        instance = LoxInstance(self)
        instance.set(self._kind_token, kind)
        instance.set(self._message_token, message)
        return instance

    def min_arity(self) -> int:
        return 2

    def max_arity(self) -> int:
        return 2

    def call(self, interpreter: object, arguments: list[object]) -> object:
        kind, message = arguments
        if not isinstance(kind, str) or not isinstance(message, str):
            raise NativeError("BytesError() expects two strings.")
        return self.make(kind, message)

    def __str__(self) -> str:
        return "<class BytesError>"


class BytesStatic:
    """Membro do namespace `Bytes` (`Bytes.fromHex`, ...)."""

    def __init__(self, name: str, errors: BytesErrorClass) -> None:
        self._name = name
        self._errors = errors
        self._arity = len(BYTES_STATICS[name].params)

    def min_arity(self) -> int:
        return self._arity

    def max_arity(self) -> int:
        return self._arity

    def call(self, interpreter: object, arguments: list[object]) -> object:
        match self._name:
            case "empty":
                return b""
            case "fromList":
                return _from_list(arguments[0])
            case "fromText":
                return _from_text(arguments[0])
            case "fromHex":
                return _from_hex(arguments[0], self._errors)
            case "fromBase64":
                return _from_base64(arguments[0], self._errors)
            case _:  # pragma: no cover - a tabela e o match são fechados
                raise NativeError(f"Unknown Bytes member '{self._name}'.")

    def __str__(self) -> str:
        return "<native fn>"


class BytesMethod:
    """Método ligado a um valor `bytes` (`b.slice(0, 1)`)."""

    def __init__(self, value: bytes, name: str) -> None:
        self._value = value
        self._name = name
        self._token = Token(TokenType.IDENTIFIER, name, None, 0)

    def min_arity(self) -> int:
        return len(BYTES_METHODS[self._name].params)

    def max_arity(self) -> int:
        return len(BYTES_METHODS[self._name].params)

    def call(self, interpreter: object, arguments: list[object]) -> object:
        match self._name:
            case "slice":
                return self._slice(arguments[0], arguments[1])
            case "concat":
                return self._concat(arguments[0])
            case "toList":
                return LoxList([byte for byte in self._value])
            case "toText":
                return self._to_text()
            case "toHex":
                return self._value.hex()
            case "toBase64":
                return base64.b64encode(self._value).decode("ascii")
            case _:  # pragma: no cover - a tabela e o match são fechados
                raise LoxRuntimeError(
                    self._token,
                    f"Undefined property '{self._name}'.",
                    code=Code.UNDEFINED_PROPERTY,
                )

    def _slice(self, start: object, end: object) -> bytes:
        if not numeric.is_int(start) or not numeric.is_int(end):
            raise LoxRuntimeError(
                self._token,
                "Bytes.slice() expects integer indices.",
                code=Code.RUNTIME_OPERANDS,
            )
        if start < 0 or end < start or end > len(self._value):
            raise LoxRuntimeError(
                self._token,
                "Bytes.slice() index out of bounds.",
                code=Code.INDEX_OUT_OF_BOUNDS,
            )
        return self._value[start:end]

    def _concat(self, other: object) -> bytes:
        if not isinstance(other, bytes):
            raise LoxRuntimeError(
                self._token,
                "Bytes.concat() expects Bytes.",
                code=Code.RUNTIME_OPERANDS,
            )
        return self._value + other

    def _to_text(self) -> LoxEnumValue:
        try:
            return make_ok(self._value.decode("utf-8"))
        except UnicodeDecodeError:
            return make_err(self._error("invalidUtf8", "expected valid UTF-8."))

    def _error(self, kind: str, message: str) -> LoxInstance:
        return _ERRORS.make(kind, message)

    def __str__(self) -> str:
        return "<native fn>"


# Compartilhado por métodos e estáticos: as instâncias de erro não carregam estado
# mutável, então uma única classe basta e evita threading pelo interpretador.
_ERRORS = BytesErrorClass()


def bytes_module() -> NativeModule:
    return NativeModule(
        "Bytes",
        {name: BytesStatic(name, _ERRORS) for name in BYTES_STATICS},
    )


def bytes_error_class() -> BytesErrorClass:
    return _ERRORS


def bytes_method(value: bytes, name: Token) -> BytesMethod:
    if name.lexeme not in BYTES_METHODS:
        raise LoxRuntimeError(
            name,
            f"Undefined property '{name.lexeme}'.",
            code=Code.UNDEFINED_PROPERTY,
        )
    return BytesMethod(value, name.lexeme)


def _from_list(value: object) -> bytes:
    if not isinstance(value, LoxList):
        raise NativeError("Bytes.fromList() expects a list.")
    result = bytearray()
    for item in value.elements:
        if not numeric.is_int(item) or item < 0 or item > 255:
            raise NativeError("Bytes.fromList() expects integers in 0..255.")
        result.append(item)
    return bytes(result)


def _from_text(value: object) -> bytes:
    if not isinstance(value, str):
        raise NativeError("Bytes.fromText() expects a string.")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError:
        raise NativeError("Bytes.fromText() expects valid Unicode.") from None


def _from_hex(value: object, errors: BytesErrorClass) -> LoxEnumValue:
    if not isinstance(value, str):
        raise NativeError("Bytes.fromHex() expects a string.")
    if len(value) % 2 != 0:
        return make_err(errors.make("invalidHex", "expected an even number of hex digits."))
    if any(char not in _HEX_DIGITS for char in value):
        return make_err(errors.make("invalidHex", "expected hexadecimal digits."))
    return make_ok(bytes.fromhex(value))


def _from_base64(value: object, errors: BytesErrorClass) -> LoxEnumValue:
    if not isinstance(value, str):
        raise NativeError("Bytes.fromBase64() expects a string.")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return make_err(errors.make("invalidBase64", "expected canonical base64."))
    if base64.b64encode(decoded).decode("ascii") != value:
        return make_err(errors.make("invalidBase64", "expected canonical base64."))
    return make_ok(decoded)
