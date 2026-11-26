# SPDX-License-Identifier: MIT OR Apache-2.0
"""Representação de máquina e teste de tipo de função em runtime (ADR-0147)."""

from __future__ import annotations

from types import SimpleNamespace

from loxia_core.execution.type_test import (
    _fn_abi_compatible,
    _rep_code,
    matches_type,
    same_rep,
)
from loxia_core.frontend.ty import (
    ANY,
    BOOL,
    BYTES,
    FLOAT,
    INT,
    NIL,
    RANGE,
    STRING,
    ClassTy,
    EnumTy,
    FnTy,
    InterfaceTy,
    ListTy,
    MapTy,
    TupleTy,
    UnionTy,
)


def test_rep_code_covers_scalars_pointers_and_unions() -> None:
    assert _rep_code(ANY) == 0
    assert _rep_code(INT) == 1
    assert _rep_code(FLOAT) == 2
    assert _rep_code(BOOL) == 3
    assert _rep_code(NIL) == 4
    for ty in (
        STRING,
        BYTES,
        RANGE,
        ListTy(INT),
        MapTy(STRING, INT),
        TupleTy((INT,)),
        ClassTy("C"),
        InterfaceTy("I"),
        EnumTy("E"),
        FnTy((INT,), INT, 1),
    ):
        assert _rep_code(ty) == 5
    assert _rep_code(UnionTy((INT, NIL))) == 101
    assert _rep_code(UnionTy((STRING, NIL))) == 5
    assert _rep_code(UnionTy((INT, STRING))) == 0
    assert _rep_code(UnionTy((INT, NIL, STRING))) == 0


def test_same_rep_compares_scalars_optionals_and_pointers() -> None:
    assert same_rep(INT, INT)
    assert not same_rep(INT, FLOAT)
    assert same_rep(STRING, ListTy(INT))
    assert same_rep(UnionTy((INT, NIL)), UnionTy((INT, NIL)))
    assert not same_rep(UnionTy((INT, NIL)), UnionTy((FLOAT, NIL)))
    assert same_rep(UnionTy((STRING, NIL)), UnionTy((ListTy(INT), NIL)))
    assert not same_rep(ANY, INT)


def test_same_rep_function_signatures_are_abi_compatible() -> None:
    int_fn = FnTy((INT,), INT, 1)
    any_fn = FnTy((ANY,), INT, 1)
    assert same_rep(int_fn, int_fn)
    assert not same_rep(any_fn, int_fn)
    assert same_rep(FnTy((INT,), INT, 0), int_fn)
    assert not same_rep(FnTy((INT,), INT, 1, True), int_fn)
    assert not same_rep(FnTy((INT,), FLOAT, 1), int_fn)


def test_fn_abi_compatible_rejects_arity_mismatch() -> None:
    two = FnTy((INT, INT), INT, 2)
    one = FnTy((INT,), INT, 1)
    assert not _fn_abi_compatible(two, one)
    assert not _fn_abi_compatible(one, two)


def test_matches_type_function_value() -> None:
    fn = FnTy((INT,), INT, 1)
    value = SimpleNamespace(fn_type=fn)
    assign = lambda expected, actual: expected == actual  # noqa: E731
    assert matches_type(value, fn, None, assign, same_rep)
    assert not matches_type(value, FnTy((STRING,), INT, 1), None, assign, same_rep)
    assert not matches_type(value, fn, None, lambda e, a: False, same_rep)
    assert not matches_type(value, fn, None, assign, lambda left, right: False)
    assert not matches_type(object(), fn, None, assign, same_rep)
    assert not matches_type(value, fn, None, None, None)
