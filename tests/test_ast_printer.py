from __future__ import annotations

from src.ast_printer import AstPrinter
from src.parser import Parser
from src.scanner import Scanner


def dump(source: str) -> str:
    statements = Parser(Scanner(source).scan_tokens()).parse()

    assert statements is not None
    return AstPrinter().print_program(statements)


def test_dump_program_statements() -> None:
    source = """
    var a = 1;
    val b = a + 2;
    print b;
    if (b) print b; else print 0;
    while (b) b = b - 1;
    { var z = 3; }
    fn soma(x, var y) { return x + y; }
    return;
    """

    assert dump(source) == (
        "(var a 1)\n"
        "(val b (+ a 2))\n"
        "(print b)\n"
        "(if b (print b) (print 0))\n"
        "(while b (expr (= b (- b 1))))\n"
        "(block (var z 3))\n"
        "(fn soma (x var y) (return (+ x y)))\n"
        "(return)"
    )


def test_dump_class_and_for_in() -> None:
    source = """
    class A { init(x) { this.x = x; } }
    class B(A) {}
    for i in 0..2 { print i; }
    """

    assert dump(source) == (
        "(class A (fn init (x) (expr (set x this x))))\n"
        "(class B (super A))\n"
        "(for-in i (.. 0 2) (block (print i)))"
    )


def test_dump_list_nodes() -> None:
    source = """
    val xs = [1, 2]
    print xs[0]
    xs[1] = 3
    """

    assert dump(source) == (
        "(val xs (list 1 2))\n"
        "(print (index xs 0))\n"
        "(expr (index-set xs 1 3))"
    )


def test_dump_map_nodes() -> None:
    source = """
    val m = {"a": 1, "b": 2}
    print m["a"]
    m["b"] = 3
    print {}
    """

    assert dump(source) == (
        '(val m (map ("a" 1) ("b" 2)))\n'
        '(print (index m "a"))\n'
        '(expr (index-set m "b" 3))\n'
        "(print (map))"
    )


def test_dump_lambda_nodes() -> None:
    source = """
    val f = fn(x: Int) => x * 2
    val g = fn(a: Int, b: Int) -> Int { return a + b }
    """

    assert dump(source) == (
        "(val f (lambda (x: Int) (return (* x 2))))\n"
        "(val g (lambda (a: Int b: Int) -> Int (return (+ a b))))"
    )


def test_dump_interpolated_string() -> None:
    source = """
    val s = "a ${1 + 2} b"
    print "${nome}"
    """

    assert dump(source) == (
        '(val s (interp "a " (+ 1 2) " b"))\n'
        "(print (interp nome))"
    )
