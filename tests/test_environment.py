from __future__ import annotations

import pytest

from src.environment import Environment
from src.errors import LoxRuntimeError
from src.token_type import TokenType
from src.tokens import Token


def ident(name: str) -> Token:
    return Token(TokenType.IDENTIFIER, name, None, 1)


def test_gets_value_from_enclosing_scope() -> None:
    outer = Environment()
    outer.define("a", 1.0)
    inner = Environment(outer)

    assert inner.get(ident("a")) == 1.0


def test_assign_updates_the_scope_that_owns_the_name() -> None:
    outer = Environment()
    outer.define("a", 1.0)
    inner = Environment(outer)

    inner.assign(ident("a"), 2.0)

    assert outer.get(ident("a")) == 2.0


def test_assignment_does_not_leak_into_outer_scope() -> None:
    outer = Environment()
    outer.define("a", 1.0)
    inner = Environment(outer)
    inner.define("a", 10.0)

    inner.assign(ident("a"), 20.0)

    assert inner.get(ident("a")) == 20.0
    assert outer.get(ident("a")) == 1.0


def test_get_undefined_variable_raises() -> None:
    with pytest.raises(LoxRuntimeError, match="Undefined variable 'x'"):
        Environment().get(ident("x"))


def test_assign_undefined_variable_raises() -> None:
    with pytest.raises(LoxRuntimeError, match="Undefined variable 'x'"):
        Environment().assign(ident("x"), 1.0)


def test_define_is_local_to_the_environment() -> None:
    outer = Environment()
    Environment(outer).define("x", 1.0)

    with pytest.raises(LoxRuntimeError):
        outer.get(ident("x"))


def test_get_at_and_assign_at_by_distance() -> None:
    outer = Environment()
    outer.define("a", 1.0)
    inner = Environment(outer)

    assert inner.get_at(1, "a") == 1.0

    inner.assign_at(1, ident("a"), 2.0)

    assert outer.get(ident("a")) == 2.0


def test_ancestor_walks_enclosing_chain() -> None:
    outer = Environment()
    inner = Environment(outer)

    assert inner.ancestor(0) is inner
    assert inner.ancestor(1) is outer
