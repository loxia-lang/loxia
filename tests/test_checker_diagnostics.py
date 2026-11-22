# SPDX-License-Identifier: MIT OR Apache-2.0
"""Branches de diagnóstico do checker que o corpus não exercita."""

from __future__ import annotations

import pytest

from loxia.engine import Loxia


def check(source: str) -> Loxia:
    lox = Loxia(max_errors=0)
    lox.use_file("diag.lx")
    lox.check(source)
    return lox


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("type A = A\nval x: A = 1\n", "Type alias 'A' is recursive."),
        ("type A = Int\ntype A = String\n", "Type alias 'A' is already declared."),
        (
            "type A = Int\nfn f[T: A](x: T) -> T { return x }\n",
            "Type alias 'A' isn't an interface.",
        ),
        ("fn f[T](x: T[Int]) -> T { return x }\n", "Type parameter 'T' can't take type arguments."),
        ("type A = Int\nval x: A[Int] = 1\n", "Type alias 'A' isn't generic."),
        ("enum E[T] { A(T) }\nval e: E = E.A(1)\n", "Enum 'E' needs 1 type argument(s)."),
        (
            "enum E[T] { A(T) }\nval e: E[Int, String] = E.A(1)\n",
            "E expects 1 type argument(s), got 2.",
        ),
        ("interface I {}\nval x: I[Int] = 1\n", "Interface 'I' isn't generic."),
        (
            "class A {}\nfn f(a: A) -> Nil { return nil }\nf(A)\n",
            "Expected an instance of A, found the class A.",
        ),
        (
            "class A {}\nval f: fn() -> Int = A\n",
            "Expected a function fn() -> Int, found the class A.",
        ),
        ("val f = fn(...xs) => 1\n", "Variadic parameter 'xs' needs a type annotation."),
        ("val f = fn(...xs: Int, y: Int) => 1\n", "Variadic parameter must be last."),
        ("val f = fn(...xs: Int = 1) => 1\n", "Lambda parameters can't have defaults."),
        ("fn f[T](a: T, b: T) -> T { return a ** b }\n", "Operands must be numbers."),
        ("print(true ** 2)\n", "Operands must be numbers."),
        ("val t: (Int, Int) = (1, 2, 3)\n", "Expected a tuple of 2 elements, found 3."),
    ],
)
def test_checker_diagnostic_branches(
    source: str,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


@pytest.mark.parametrize(
    "source",
    [
        "fn f(xs: List[Int] | Nil) -> Int { return 0 }\nf([1])\n",
        'fn f(m: Map[String, Int] | Nil) -> Int { return 0 }\nf({"a": 1})\n',
        "fn f(g: (fn(Int) -> Int) | Nil) -> Int { return 0 }\nf(fn(x) => x)\n",
        "val a: Any = 1\nval b: Any = 2\nprint(a ** b)\n",
        "val a: Any = 1\nprint(a & 2)\n",
        "fn f[T: Num](a: T, b: T) -> T { return a ** b }\nprint(f(2, 3))\n",
    ],
)
def test_union_and_any_contexts_are_clean(source: str) -> None:
    assert check(source).reporter.had_error is False
