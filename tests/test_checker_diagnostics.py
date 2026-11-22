# SPDX-License-Identifier: MIT OR Apache-2.0
"""Branches de diagnóstico do checker que o corpus não exercita."""

from __future__ import annotations

import pytest

from loxia.engine import Loxia
from loxia_core.diagnostics.codes import Code


def check(source: str) -> Loxia:
    lox = Loxia(max_errors=0)
    lox.use_file("diag.lx")
    lox.check(source)
    return lox


@pytest.mark.parametrize(
    ("source", "message", "code"),
    [
        (
            "type A = A\nval x: A = 1\n",
            "Type alias 'A' is recursive.",
            Code.INVALID_TYPE_ANNOTATION,
        ),
        (
            "type A = Int\ntype A = String\n",
            "Type alias 'A' is already declared.",
            Code.INVALID_CHECKER_DECLARATION,
        ),
        (
            "type A = Int\nfn f[T: A](x: T) -> T { return x }\n",
            "Type alias 'A' isn't an interface.",
            Code.INVALID_TYPE_ANNOTATION,
        ),
        (
            "fn f[T](x: T[Int]) -> T { return x }\n",
            "Type parameter 'T' can't take type arguments.",
            Code.TYPE_ARGUMENTS,
        ),
        ("type A = Int\nval x: A[Int] = 1\n", "Type alias 'A' isn't generic.", Code.TYPE_ARGUMENTS),
        (
            "enum E[T] { A(T) }\nval e: E = E.A(1)\n",
            "Enum 'E' needs 1 type argument(s).",
            Code.TYPE_ARGUMENTS,
        ),
        (
            "enum E[T] { A(T) }\nval e: E[Int, String] = E.A(1)\n",
            "E expects 1 type argument(s), got 2.",
            Code.TYPE_ARGUMENTS,
        ),
        (
            "interface I {}\nval x: I[Int] = 1\n",
            "Interface 'I' isn't generic.",
            Code.TYPE_ARGUMENTS,
        ),
        (
            "class A {}\nfn f(a: A) -> Nil { return nil }\nf(A)\n",
            "Expected an instance of A, found the class A.",
            Code.SEMANTIC_ERROR,
        ),
        (
            "class A {}\nval f: fn() -> Int = A\n",
            "Expected a function fn() -> Int, found the class A.",
            Code.TYPE_MISMATCH,
        ),
        (
            "val f = fn(...xs) => 1\n",
            "Variadic parameter 'xs' needs a type annotation.",
            Code.MISSING_ANNOTATION,
        ),
        (
            "val f = fn(...xs: Int, y: Int) => 1\n",
            "Variadic parameter must be last.",
            Code.INVALID_DECLARATION,
        ),
        (
            "val f = fn(...xs: Int = 1) => 1\n",
            "Lambda parameters can't have defaults.",
            Code.INVALID_DECLARATION,
        ),
        (
            "fn f[T](a: T, b: T) -> T { return a ** b }\n",
            "Operands must be numbers.",
            Code.INVALID_OPERANDS,
        ),
        ("print(true ** 2)\n", "Operands must be numbers.", Code.SEMANTIC_ERROR),
        (
            "val t: (Int, Int) = (1, 2, 3)\n",
            "Expected a tuple of 2 elements, found 3.",
            Code.TYPE_MISMATCH,
        ),
    ],
)
def test_checker_diagnostic_branches(
    source: str,
    message: str,
    code: Code,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err
    assert any(item.code is code for item in lox.reporter.batch().diagnostics)


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
