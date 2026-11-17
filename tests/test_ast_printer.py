from __future__ import annotations

from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner


def dump(source: str) -> str:
    statements = Parser(Scanner(source).scan_tokens()).parse()

    assert statements is not None
    return AstPrinter().print_program(statements)


def test_dump_program_statements() -> None:
    source = """
    var a = 1;
    val b = a + 2;
    print(b);
    if (b) print(b); else print(0);
    while (b) b = b - 1;
    { var z = 3; }
    fn soma(x, var y) { return x + y; }
    return;
    """

    assert dump(source) == (
        "(var a 1)\n"
        "(val b (+ a 2))\n"
        "(expr (call print b))\n"
        "(if b (expr (call print b)) (expr (call print 0)))\n"
        "(while b (expr (= b (- b 1))))\n"
        "(block (var z 3))\n"
        "(fn soma (x var y) (return (+ x y)))\n"
        "(return)"
    )


def test_dump_class_and_for_in() -> None:
    source = """
    class A { init(x) { this.x = x; } }
    class B(A) {}
    for i in 0..2 { print(i); }
    """

    assert dump(source) == (
        "(class A (fn init (x) (expr (set x this x))))\n"
        "(class B (super A))\n"
        "(for-in i (.. 0 2) (block (expr (call print i))))"
    )


def test_dump_interface_and_implements() -> None:
    source = """
    interface Forma {
      area() -> Int
      fn nome() -> String { return "forma"; }
    }
    class Circulo implements Forma { area() -> Int { return 1; } }
    """

    assert dump(source) == (
        "(interface Forma (sig area () -> Int) "
        '(fn nome () -> String (return "forma")))\n'
        "(class Circulo (implements Forma) (fn area () -> Int (return 1)))"
    )


def test_dump_list_nodes() -> None:
    source = """
    val xs = [1, 2]
    print(xs[0])
    xs[1] = 3
    """

    assert dump(source) == (
        "(val xs (list 1 2))\n(expr (call print (index xs 0)))\n(expr (index-set xs 1 3))"
    )


def test_dump_map_nodes() -> None:
    source = """
    val m = {"a": 1, "b": 2}
    print(m["a"])
    m["b"] = 3
    print({})
    """

    assert dump(source) == (
        '(val m (map ("a" 1) ("b" 2)))\n'
        '(expr (call print (index m "a")))\n'
        '(expr (index-set m "b" 3))\n'
        "(expr (call print (map)))"
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


def test_dump_generic_function() -> None:
    assert dump("fn id[T](x: T) -> T { return x; }") == ("(fn id[T] (x: T) -> T (return x))")


def test_dump_type_alias() -> None:
    assert dump("type UserId = Int;") == "(type UserId Int)"


def test_dump_variadic_and_spread() -> None:
    assert dump("fn f(...xs: Int) -> Int { return 0; } f(...[1]);") == (
        "(fn f (...xs: Int) -> Int (return 0))\n(expr (call f ...(list 1)))"
    )


def test_dump_generic_function_with_bounds() -> None:
    assert dump("fn max[T: Ord + Forma](a: T, b: T) -> T { return a; }") == (
        "(fn max[T: Ord + Forma] (a: T b: T) -> T (return a))"
    )


def test_dump_is_expression() -> None:
    assert dump("print(x is Int)") == "(expr (call print (is x Int)))"


def test_dump_interpolated_string() -> None:
    source = """
    val s = "a ${1 + 2} b"
    print("${nome}")
    """

    assert dump(source) == ('(val s (interp "a " (+ 1 2) " b"))\n(expr (call print (interp nome)))')


def test_dump_as_expression() -> None:
    assert dump("print(3.9 as Int + 1)") == "(expr (call print (+ (as 3.9 Int) 1)))"


def test_dump_tuples_and_destructuring() -> None:
    source = """
    val (a, b) = (1, "x");
    var (c, d): (Int, String) = (2, "y");
    print((a, (b, c))[1]);
    """

    assert dump(source) == (
        '(val-destructure (a b) (tuple 1 "x"))\n'
        '(var-destructure (c d): (Int, String) (tuple 2 "y"))\n'
        "(expr (call print (index (tuple a (tuple b c)) 1)))"
    )


def test_dump_nested_destructuring() -> None:
    source = "val (a, (b, c)): (Int, (Int, Int)) = (1, (2, 3));"

    assert dump(source) == ("(val-destructure (a (b c)): (Int, (Int, Int)) (tuple 1 (tuple 2 3)))")
