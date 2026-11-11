from __future__ import annotations

import pytest

from src import numeric


def test_int_division_truncates_toward_zero() -> None:
    assert numeric.int_divide(7, 2) == 3
    assert numeric.int_divide(-7, 2) == -3
    assert numeric.int_divide(7, -2) == -3
    assert numeric.int_divide(-7, -2) == 3


def test_int_division_overflow_wraps_i64() -> None:
    assert numeric.int_divide(numeric.INT_MIN, -1) == numeric.INT_MIN


def test_integer_power_wraps_i64() -> None:
    assert numeric.power(2, 0) == 1
    assert numeric.power(2, 10) == 1024
    assert numeric.power(2, 63) == numeric.INT_MIN
    assert numeric.power(-2, 3) == -8


def test_integer_power_rejects_negative_exponent() -> None:
    with pytest.raises(ValueError):
        numeric.power(2, -1)


def test_bitwise_operations_use_i64() -> None:
    assert numeric.bit_and(5, 3) == 1
    assert numeric.bit_or(5, 3) == 7
    assert numeric.bit_xor(5, 3) == 6
    assert numeric.bit_not(0) == -1
    assert numeric.bit_not(5) == -6
    assert numeric.shift_left(1, 63) == numeric.INT_MIN
    assert numeric.shift_right(-8, 1) == -4
    assert numeric.shift_right_logical(-1, 1) == numeric.INT_MAX
    assert numeric.shift_right_logical(-1, 63) == 1


def test_float_power_accepts_negative_exponent() -> None:
    assert numeric.power(2.0, -1) == 0.5
    assert numeric.power(2, -1.0) == 0.5
