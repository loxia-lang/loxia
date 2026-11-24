# SPDX-License-Identifier: MIT OR Apache-2.0
"""High-risk checker branches: members, calls, generics, lambdas and init flow."""

from __future__ import annotations

import pytest

from loxia.engine import Loxia
from loxia_core.diagnostics.codes import Code


def check(source: str) -> Loxia:
    lox = Loxia(max_errors=0)
    lox.use_file("branch.lx")
    lox.check(source)
    return lox


CASES: list[tuple[str, Code | None]] = [
    # Member/property inference and diagnostics.
    ("val xs: List[Int] = [1]\nprint(xs.nope)\n", Code.UNDEFINED_NAME),
    ("val m: Map[String, Int] = {}\nprint(m.nope)\n", Code.UNDEFINED_NAME),
    ("val b: Bytes = Bytes.fromList([1])\nprint(b.nope)\n", Code.UNDEFINED_NAME),
    ("enum E { A }\nprint(E.A.nope)\n", Code.TYPE_MISMATCH),
    ("enum E { A }\nprint(E.Nope)\n", Code.UNDEFINED_NAME),
    ("enum E[T] { A }\nprint(E.A)\n", Code.GENERIC_UNSUPPORTED),
    ("class C {}\nprint(C().nope)\n", Code.UNDEFINED_NAME),
    ("val x: Int = 1\nprint(x.nope)\n", Code.TYPE_MISMATCH),
    ("val x: Int? = 1\nprint(x.nope)\n", Code.TYPE_MISMATCH),
    ("val x: Int? = 1\nprint(x?.nope)\n", Code.TYPE_MISMATCH),
    ("val x: Int? = nil\nprint(x?.nope)\n", Code.TYPE_MISMATCH),
    (
        "interface I { fn f() -> Int }\n"
        "class C(I) { fn f() -> Int { return 1 } }\n"
        "val i: I = C()\nprint(i.nope)\n",
        Code.UNDEFINED_NAME,
    ),
    (
        "interface I { fn f() -> Int }\n"
        "class C implements I { fn f() -> Int { return 1 } }\n"
        "fn use[T: I](x: T) -> Int { return x.f() }\n"
        "print(use(C()))\n",
        None,
    ),
    (
        "interface I { fn f() -> Int }\n"
        "interface J { fn f() -> String }\n"
        "fn use[T: I + J](x: T) -> Int { return x.f() }\n",
        Code.INVALID_OVERRIDE,
    ),
    (
        "fn use[T](x: T) -> Int { return x.foo() }\n",
        Code.UNDEFINED_NAME,
    ),
    (
        "class A { var x: Int; init() { this.x = 1 } }\n"
        "class B { var x: Int; init() { this.x = 2 } }\n"
        "fn get(c: A | B) -> Int { return c.x }\n",
        None,
    ),
    (
        "interface I { fn f() -> Int }\n"
        "interface J { fn f() -> Int }\n"
        "fn use(x: I | J) -> Int { return x.f() }\n",
        None,
    ),
    ("print(math.nope)\n", Code.UNDEFINED_NAME),
    ("print(Int.nope)\n", Code.UNDEFINED_NAME),
    # Calls, generic inference and arity.
    ("fn f[T](x: T) -> T { return x }\nprint(f())\n", Code.ARITY_MISMATCH),
    ("fn f[T](x: T) -> T { return x }\nprint(f(1, 2))\n", Code.ARITY_MISMATCH),
    (
        "fn f[T](...xs: T) -> T { return xs[0] }\nprint(f())\n",
        Code.GENERIC_INFERENCE,
    ),
    (
        'fn f[T](x: T, y: T) -> T { return x }\nprint(f(1, "a"))\n',
        Code.TYPE_MISMATCH,
    ),
    (
        "fn f[T](x: T) -> T { return x }\nval g: fn(Int) -> Int = f\n",
        Code.GENERIC_INFERENCE,
    ),
    (
        "fn first[T](xs: List[T]) -> T { return xs[0] }\nprint(first([1]))\n",
        None,
    ),
    (
        'fn get[T](m: Map[String, T]) -> T { return m["a"] }\nprint(get({"a": 1}))\n',
        None,
    ),
    (
        "class Box[T] { var v: T; init(v: T) { this.v = v } }\nval b: Box[Int] = Box(1)\n",
        None,
    ),
    (
        "class Box[T] { var v: T; init(v: T) { this.v = v } }\nprint(Box())\n",
        Code.ARITY_MISMATCH,
    ),
    (
        "class Box[T] { var v: T }\nprint(Box())\n",
        Code.GENERIC_INFERENCE,
    ),
    (
        "fn f(...xs: Int) -> Int { return 0 }\nprint(f(...[1, 2]))\n",
        None,
    ),
    (
        "fn f(a: Int, ...xs: Int) -> Int { return a }\nprint(f(1, ...[2]))\n",
        None,
    ),
    (
        "fn f(a: Int, ...xs: Int) -> Int { return a }\nprint(f(...[1]))\n",
        Code.ARITY_MISMATCH,
    ),
    (
        "fn f(a: Int) -> Int { return a }\nprint(f(...[1]))\n",
        Code.ARITY_MISMATCH,
    ),
    # Lambdas: contextual parameters, defaults and variadics.
    ("val f: fn(Int) -> Int = fn(x) => x\nprint(f(1))\n", None),
    ('val f: fn(Int, String) -> Int = fn(x, y) => x\nprint(f(1, "a"))\n', None),
    (
        "fn take(f: fn(Int) -> Int) -> Int { return f(1) }\nprint(take(fn(x, y) => x))\n",
        Code.MISSING_ANNOTATION,
    ),
    (
        "val f: fn(Int) -> Int = fn(...xs: Int) => 1\n",
        Code.TYPE_MISMATCH,
    ),
    ("val f = fn(...xs: Int) => xs[0]\nprint(f(1, 2))\n", None),
    ("val f: fn(Int) -> Int = fn() => 1\n", Code.TYPE_MISMATCH),
    # Unary operators and type parameters.
    ("val x: Any = 1\nprint(-x)\n", None),
    ("fn f[T](x: T) -> T { return -x }\n", Code.INVALID_OPERANDS),
    ("fn f[T: Num](x: T) -> T { return -x }\nprint(f(1))\n", None),
    ("print(-true)\n", Code.INVALID_OPERANDS),
    ("print(~true)\n", Code.INVALID_OPERANDS),
    ("print(~1.0)\n", Code.INVALID_OPERANDS),
    ('print(-"a")\n', Code.INVALID_OPERANDS),
    # Field initialization flow.
    (
        "class C { var x: Int; init(flag: Bool) { "
        "if (flag) { this.x = 1 } else { this.x = 2 } } }\n",
        None,
    ),
    (
        "class C { var x: Int; init(flag: Bool) { if (flag) { return; } this.x = 1 } }\n",
        Code.MISSING_INITIALIZATION,
    ),
    (
        "class C { var x: Int; init() { while (false) { this.x = 1 } } }\n",
        Code.MISSING_INITIALIZATION,
    ),
    (
        "class C { var x: Int; init() { for i in 0..1 { this.x = i } } }\n",
        Code.MISSING_INITIALIZATION,
    ),
    (
        "class C { var x: Int; init() { val y = 1; this.x = y } }\n",
        None,
    ),
    ("class C { var x: Int; init() { return; } }\n", Code.MISSING_INITIALIZATION),
    ("class C { var x: Int; init() { return 1; } }\n", Code.INVALID_RETURN),
    # Annotation fixes and default values for missing initialization.
    ("class C { var x: Float; init() {} }\n", Code.MISSING_INITIALIZATION),
    ("class C { var x: Bool; init() {} }\n", Code.MISSING_INITIALIZATION),
    ("class C { var x: String; init() {} }\n", Code.MISSING_INITIALIZATION),
    ("class C { var x: List[Int]; init() {} }\n", Code.MISSING_INITIALIZATION),
    ("class C { var x: Map[String, Int]; init() {} }\n", Code.MISSING_INITIALIZATION),
    ("class C { var x: (Int, Int); init() {} }\n", Code.MISSING_INITIALIZATION),
    # Literal/default inference in signatures.
    ("fn f(x: Int = 1.0) -> Int { return x }\n", Code.TYPE_MISMATCH),
    ("fn f(x: Int = true) -> Int { return x }\n", Code.TYPE_MISMATCH),
    ('fn f(x: Int = "a") -> Int { return x }\n', Code.TYPE_MISMATCH),
    ('fn f() -> Int { return "a" }\n', Code.TYPE_MISMATCH),
    ("fn f() -> Int { return 1 + 2 }\n", None),
    ("fn f() -> Int { return -1 }\n", None),
    ("fn f() -> Int { if (true) { return 1 } }\n", Code.RETURN_PATH),
]


@pytest.mark.parametrize(("source", "code"), CASES)
def test_checker_branch(source: str, code: Code | None, capsys: pytest.CaptureFixture[str]) -> None:
    lox = check(source)
    capsys.readouterr()

    if code is None:
        assert lox.reporter.had_error is False
        return
    assert lox.reporter.had_error is True
    assert any(item.code is code for item in lox.reporter.batch().diagnostics), (
        [item.code for item in lox.reporter.batch().diagnostics],
        [item.message for item in lox.reporter.batch().diagnostics],
    )
