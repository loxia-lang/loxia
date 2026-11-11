from __future__ import annotations

import pytest

from src.ast_printer import AstPrinter
from src.parser import Parser
from src.scanner import Scanner
from src.stmt import Class, Expression, Function, If, Print, Return, Stmt, Var, While


def parser_for(source: str, *, repl: bool = False) -> Parser:
    return Parser(Scanner(source).scan_tokens(), repl=repl)


def parse(source: str) -> list[Stmt]:
    statements = parser_for(source).parse()

    assert statements is not None
    return statements


def ast(expression: str) -> str:
    statements = parse(f"{expression};")

    assert len(statements) == 1
    statement = statements[0]
    assert isinstance(statement, Expression)
    return AstPrinter().print(statement.expression)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", "(+ 1 (* 2 3))"),
        ("(1 + 2) * 3", "(* (group (+ 1 2)) 3)"),
        ("-1 * 2", "(* (- 1) 2)"),
        ("a = 1", "(= a 1)"),
        ("true and false or nil", "(or (and true false) nil)"),
        ("1 < 2 == true", "(== (< 1 2) true)"),
        ("!nil", "(! nil)"),
        ("a", "a"),
    ],
)
def test_precedence_and_ast_shape(expression: str, expected: str) -> None:
    assert ast(expression) == expected


def test_parses_statements() -> None:
    statements = parse("var a = 1; print a; if (a) print 0; while (a) a = 0;")

    assert isinstance(statements[0], Var)
    assert isinstance(statements[1], Print)
    assert isinstance(statements[2], If)
    assert isinstance(statements[3], While)


def test_missing_semicolon_reports_error_and_recovers() -> None:
    parser = parser_for("print 1")
    statements = parser.parse()

    assert parser.reporter.had_error
    assert statements == []


def test_invalid_assignment_target_reports_error() -> None:
    parser = parser_for("1 = 2;")
    statements = parser.parse()

    assert parser.reporter.had_error
    assert statements is not None
    assert isinstance(statements[0], Expression)


def test_error_recovery_keeps_parsing_after_bad_declaration() -> None:
    parser = parser_for("var = 1;\nprint 2;")
    statements = parser.parse()

    assert parser.reporter.had_error
    assert statements is not None
    assert len(statements) == 1
    assert isinstance(statements[0], Print)


@pytest.mark.parametrize("source", ["1 + 1", "1 + 1;", "print 1", "var x = 5"])
def test_repl_accepts_missing_final_semicolon(source: str) -> None:
    parser = parser_for(source, repl=True)
    statements = parser.parse_repl()

    assert statements is not None
    assert len(statements) == 1


def test_repl_wraps_bare_expression_in_print() -> None:
    statements = parser_for("1 + 1", repl=True).parse_repl()

    assert statements is not None
    assert isinstance(statements[0], Print)


def test_repl_keeps_statements_as_statements() -> None:
    statements = parser_for("var x = 5", repl=True).parse_repl()

    assert statements is not None
    assert isinstance(statements[0], Var)


def test_repl_does_not_print_declaration_errors() -> None:
    parser = parser_for("var = 1", repl=True)

    parser.parse_repl()

    assert parser.reporter.had_error


def test_call_ast_shape() -> None:
    assert ast("f()") == "(call f)"
    assert ast("f(1, 2)") == "(call f 1 2)"
    assert ast("f(g(1), 2 + 3)") == "(call f (call g 1) (+ 2 3))"


def test_call_binds_tighter_than_unary() -> None:
    assert ast("-f(1)") == "(- (call f 1))"


def test_parses_function_declaration() -> None:
    statements = parse("fun soma(a, b) { return a + b; }")

    assert len(statements) == 1
    function = statements[0]
    assert isinstance(function, Function)
    assert function.name.lexeme == "soma"
    assert [param.lexeme for param in function.params] == ["a", "b"]
    assert len(function.body) == 1
    assert isinstance(function.body[0], Return)


def test_parses_class_declaration() -> None:
    statements = parse("class Foo { bar(a) { return a; } }")

    assert len(statements) == 1
    klass = statements[0]
    assert isinstance(klass, Class)
    assert klass.name.lexeme == "Foo"
    assert klass.superclass is None
    assert len(klass.methods) == 1
    assert klass.methods[0].name.lexeme == "bar"
    assert [param.lexeme for param in klass.methods[0].params] == ["a"]


def test_property_and_this_ast_shape() -> None:
    assert ast("a.b") == "(. b a)"
    assert ast("this.x") == "(. x this)"
    assert ast("a.b = 1") == "(set b a 1)"


def test_parses_class_with_superclass() -> None:
    statements = parse("class B < A {}")

    klass = statements[0]
    assert isinstance(klass, Class)
    assert klass.superclass is not None
    assert klass.superclass.name.lexeme == "A"


def test_super_ast_shape() -> None:
    assert ast("super.m()") == "(call (super m))"
