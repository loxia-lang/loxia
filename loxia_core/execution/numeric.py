# SPDX-License-Identifier: MIT OR Apache-2.0
"""Modelo numérico: `Int` (i64) e `Float` (f64), com promoção e wrapping.

Contrato em [`TIPOS.md`](../TIPOS.md) §3 (decisões `D-1`..`D-6`) e ADR-0006.
As funções recebem `object` porque o interpretador valida os operandos antes; aqui o
`cast` documenta a pré-condição sem pagar o custo de `assert` no caminho quente.
"""

from __future__ import annotations

import math
from typing import TypeGuard, cast

from loxia_core.numeric_bounds import INT_MAX as INT_MAX
from loxia_core.numeric_bounds import INT_MIN as INT_MIN

type Number = int | float

_UINT64 = 1 << 64
_UINT64_MASK = _UINT64 - 1


class NumericError(Exception):
    """Falha numérica que o interpretador converte em erro de runtime."""


class NumericOverflow(NumericError):
    """`Int` saiu do range i64 em modo `--debug`."""


class NumericConversionError(NumericError):
    """Cast numérico inválido (NaN/Inf/fora do range)."""


def is_int(value: object) -> TypeGuard[int]:
    """`bool` é subclasse de `int` em Python, mas `type` exato já o exclui."""
    return type(value) is int


def is_float(value: object) -> TypeGuard[float]:
    return type(value) is float


def is_number(value: object) -> TypeGuard[Number]:
    return type(value) is int or type(value) is float


def to_float(value: object) -> float:
    return float(cast(Number, value))


def wrap_int(value: int) -> int:
    """Simula o `i64` com sinal (wrapping), como o `add`/`mul` do LLVM."""
    if INT_MIN <= value <= INT_MAX:
        return value

    wrapped = value & (_UINT64 - 1)
    return wrapped - _UINT64 if wrapped > INT_MAX else wrapped


def _checked_int(value: int) -> int:
    if not INT_MIN <= value <= INT_MAX:
        raise NumericOverflow
    return value


def float_to_int(value: object) -> int:
    """Trunca um Float em direção a zero; erro se NaN/Inf/fora do range i64."""
    number = cast(float, value)
    if not math.isfinite(number):
        raise NumericConversionError
    truncated = math.trunc(number)
    if not INT_MIN <= truncated <= INT_MAX:
        raise NumericConversionError
    return truncated


def int_to_float(value: object) -> float:
    return float(cast(int, value))


def add(left: object, right: object, *, checked: bool = False) -> Number:
    if type(left) is int and type(right) is int:
        result = left + right
        return _checked_int(result) if checked else wrap_int(result)
    return to_float(left) + to_float(right)


def subtract(left: object, right: object, *, checked: bool = False) -> Number:
    if type(left) is int and type(right) is int:
        result = left - right
        return _checked_int(result) if checked else wrap_int(result)
    return to_float(left) - to_float(right)


def multiply(left: object, right: object, *, checked: bool = False) -> Number:
    if type(left) is int and type(right) is int:
        result = left * right
        return _checked_int(result) if checked else wrap_int(result)
    return to_float(left) * to_float(right)


def divide(left: object, right: object) -> float:
    """`/` é sempre `Float` (D-4): `1 / 2` é `0.5`, não `0`."""
    return to_float(left) / to_float(right)


def modulo(left: object, right: object, *, checked: bool = False) -> Number:
    """Resto truncado (sinal do dividendo), como `srem`/`fmod` (D-4)."""
    if type(left) is int and type(right) is int:
        if checked and left == INT_MIN and right == -1:
            raise NumericOverflow
        remainder = abs(left) % abs(right)
        return -remainder if left < 0 else remainder
    return math.fmod(to_float(left), to_float(right))


def int_divide(left: object, right: object, *, checked: bool = False) -> int:
    """Divisão inteira truncada em direção a zero, com wrap i64 (ADR-0012)."""
    dividend = cast(int, left)
    divisor = cast(int, right)
    if checked and dividend == INT_MIN and divisor == -1:
        raise NumericOverflow

    quotient = abs(dividend) // abs(divisor)
    if (dividend < 0) != (divisor < 0):
        quotient = -quotient

    return wrap_int(quotient)


def power(left: object, right: object, *, checked: bool = False) -> Number:
    """`**`: `Int ** Int` inteiro (expoente >= 0); caso contrário `Float`."""
    if type(left) is int and type(right) is int:
        base = left
        exponent = right
        if exponent < 0:
            raise ValueError("negative integer exponent")

        result = 1
        while exponent:
            if exponent & 1:
                product = result * base
                result = _checked_int(product) if checked else wrap_int(product)
            exponent >>= 1
            if exponent:
                square = base * base
                base = _checked_int(square) if checked else wrap_int(square)

        return result

    return math.pow(to_float(left), to_float(right))


def bit_and(left: object, right: object) -> int:
    return wrap_int(cast(int, left) & cast(int, right))


def bit_or(left: object, right: object) -> int:
    return wrap_int(cast(int, left) | cast(int, right))


def bit_xor(left: object, right: object) -> int:
    return wrap_int(cast(int, left) ^ cast(int, right))


def bit_not(value: object) -> int:
    return wrap_int(~cast(int, value))


def shift_left(value: object, count: object) -> int:
    return wrap_int(cast(int, value) << cast(int, count))


def shift_right(value: object, count: object) -> int:
    """Shift à direita aritmético (preenche com o sinal)."""
    return wrap_int(cast(int, value) >> cast(int, count))


def shift_right_logical(value: object, count: object) -> int:
    """Shift à direita lógico: opera no padrão unsigned de 64 bits."""
    unsigned = cast(int, value) & _UINT64_MASK
    return wrap_int(unsigned >> cast(int, count))


def negate(value: object, *, checked: bool = False) -> Number:
    if type(value) is int:
        result = -value
        return _checked_int(result) if checked else wrap_int(result)
    return -cast(float, value)


def equal(left: object, right: object) -> bool:
    """Igualdade numérica com promoção (`1 == 1.0` → `true`, D-18)."""
    if type(left) is int and type(right) is int:
        return left == right
    return to_float(left) == to_float(right)


def compare(left: object, right: object) -> int | None:
    """Comparação numérica: `-1`, `0` ou `1`; `None` quando há `NaN`."""
    if type(left) is int and type(right) is int:
        if left < right:
            return -1
        return 0 if left == right else 1

    left_float = to_float(left)
    right_float = to_float(right)
    if math.isnan(left_float) or math.isnan(right_float):
        return None
    if left_float < right_float:
        return -1
    return 0 if left_float == right_float else 1
