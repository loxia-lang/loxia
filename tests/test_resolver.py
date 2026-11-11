from __future__ import annotations

from src.error_reporter import ErrorReporter
from src.interpreter import Interpreter
from src.parser import Parser
from src.resolver import Resolver
from src.scanner import Scanner
from src.stmt import Stmt


def resolve(source: str) -> tuple[ErrorReporter, Interpreter, list[Stmt]]:
    reporter = ErrorReporter()
    interpreter = Interpreter(reporter)
    statements = Parser(Scanner(source).scan_tokens()).parse()

    assert statements is not None

    Resolver(interpreter, reporter).resolve(statements)
    return reporter, interpreter, statements


def test_global_variables_are_left_to_runtime_lookup() -> None:
    _, interpreter, _ = resolve("var a = 1; print a;")

    assert interpreter.locals == {}


def test_local_variable_gets_depth_zero() -> None:
    reporter, interpreter, _ = resolve("{ var a = 1; print a; }")

    assert not reporter.had_error
    assert list(interpreter.locals.values()) == [0]


def test_shadowing_resolves_to_different_depths() -> None:
    reporter, interpreter, _ = resolve(
        """
        {
          var a = 1;
          print a;
          {
            print a;
          }
        }
        """
    )

    assert not reporter.had_error
    assert sorted(interpreter.locals.values()) == [0, 1]


def test_identical_tokens_do_not_collide_in_locals() -> None:
    # Tudo na mesma linha: os dois nós `a` têm tokens iguais, mas identidades diferentes.
    _, interpreter, _ = resolve("{ var a = 1; print a; { print a; } }")

    assert len(interpreter.locals) == 2
    assert sorted(interpreter.locals.values()) == [0, 1]


def test_function_parameter_depth() -> None:
    reporter, interpreter, _ = resolve("fun f(a) { print a; }")

    assert not reporter.had_error
    assert list(interpreter.locals.values()) == [0]


def test_redeclaration_reports_error() -> None:
    reporter, _, _ = resolve("{ var a = 1; var a = 2; }")

    assert reporter.had_error


def test_self_initializer_reports_error() -> None:
    reporter, _, _ = resolve("{ var a = a; }")

    assert reporter.had_error


def test_return_at_top_level_reports_error() -> None:
    reporter, _, _ = resolve("return 1;")

    assert reporter.had_error


def test_return_inside_function_is_allowed() -> None:
    reporter, _, _ = resolve("fun f() { return 1; }")

    assert not reporter.had_error


def test_parameter_and_local_share_scope() -> None:
    # Decisão do challenge 3: parâmetro e local no mesmo escopo = erro.
    reporter, _, _ = resolve('fun scope(a) { var a = "local"; }')

    assert reporter.had_error


def test_this_outside_class_reports_error() -> None:
    reporter, _, _ = resolve("print this;")

    assert reporter.had_error


def test_this_inside_method_is_resolved() -> None:
    reporter, interpreter, _ = resolve("class Foo { bar() { print this; } }")

    assert not reporter.had_error
    assert list(interpreter.locals.values()) == [1]


def test_initializer_cannot_return_a_value() -> None:
    reporter, _, _ = resolve("class Foo { init() { return 1; } }")

    assert reporter.had_error


def test_initializer_can_return_without_value() -> None:
    reporter, _, _ = resolve("class Foo { init() { return; } }")

    assert not reporter.had_error


def test_super_outside_class_reports_error() -> None:
    reporter, _, _ = resolve("super.method();")

    assert reporter.had_error


def test_super_without_superclass_reports_error() -> None:
    reporter, _, _ = resolve("class Foo { method() { super.method(); } }")

    assert reporter.had_error


def test_class_cannot_inherit_from_itself() -> None:
    reporter, _, _ = resolve("class Foo < Foo {}")

    assert reporter.had_error


def test_super_depth_in_subclass() -> None:
    reporter, interpreter, _ = resolve("class A {} class B < A { m() { super.m(); } }")

    assert not reporter.had_error
    assert list(interpreter.locals.values()) == [2]


def test_this_depth_in_subclass() -> None:
    reporter, interpreter, _ = resolve(
        "class A {} class B < A { m() { print this; } }"
    )

    assert not reporter.had_error
    assert list(interpreter.locals.values()) == [1]
