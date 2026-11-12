from __future__ import annotations

import pytest

from src.ast_printer import AstPrinter
from src.expr import Is, Lambda, MapLiteral
from src.parser import Parser
from src.scanner import Scanner
from src.stmt import (
    Class,
    Expression,
    ForIn,
    Function,
    If,
    Print,
    Return,
    Stmt,
    Var,
    While,
)
from src.ty import display


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
        ("0..10", "(.. 0 10)"),
        ("0..1 + 2", "(.. 0 (+ 1 2))"),
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


def test_parses_for_in_statement() -> None:
    statements = parse("for i in 0..3 print i;")

    assert isinstance(statements[0], ForIn)
    assert statements[0].name.lexeme == "i"


def test_parses_map_literal_with_expression_keys() -> None:
    statements = parse('val m = {"a": 1, nome: 2};')

    var = statements[0]
    assert isinstance(var, Var)
    assert isinstance(var.initializer, MapLiteral)
    assert len(var.initializer.entries) == 2


def test_missing_semicolon_reports_error_and_recovers() -> None:
    parser = parser_for("val a = 1 val b = 2")
    parser.parse()

    assert parser.reporter.had_error


def test_newline_ends_statement_without_semicolon() -> None:
    statements = parse("val a = 1\nprint a\n")

    assert len(statements) == 2
    assert isinstance(statements[0], Var)
    assert isinstance(statements[1], Print)


def test_elif_is_nested_if() -> None:
    statements = parse("if (a) print 1\nelif (b) print 2\nelse print 3")

    outer = statements[0]
    assert isinstance(outer, If)
    assert isinstance(outer.else_branch, If)
    assert isinstance(outer.else_branch.else_branch, Print)


def test_return_at_line_end_is_bare() -> None:
    statements = parse("fn f() {\n  return\n  1\n}")

    function = statements[0]
    assert isinstance(function, Function)
    ret = function.body[0]
    assert isinstance(ret, Return)
    assert ret.value is None


def test_operator_on_next_line_starts_new_statement() -> None:
    statements = parse("var x = 1\n-2\n")

    assert len(statements) == 2
    assert isinstance(statements[0], Var)
    assert isinstance(statements[1], Expression)
    assert "- 2" in AstPrinter().print_program(statements)


def test_class_field_without_semicolon() -> None:
    statements = parse("class C {\n  var x\n  m() {}\n}")

    klass = statements[0]
    assert isinstance(klass, Class)
    assert [field.name.lexeme for field in klass.fields] == ["x"]


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


def test_int_division_and_power_ast_shape() -> None:
    assert ast("7 // 2") == "(// 7 2)"
    assert ast("2 ** 3 ** 2") == "(** 2 (** 3 2))"
    assert ast("-2 ** 2") == "(- (** 2 2))"
    assert ast("2 ** -1") == "(** 2 (- 1))"


def test_bitwise_precedence_ast_shape() -> None:
    assert ast("1 & 3 == 1") == "(== (& 1 3) 1)"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("[1, 2, 3]", "(list 1 2 3)"),
        ("[]", "(list)"),
        ("[[1], [2, 3]]", "(list (list 1) (list 2 3))"),
        ("xs[0]", "(index xs 0)"),
        ("xs[0] = 1", "(index-set xs 0 1)"),
        ("f()[0]", "(index (call f) 0)"),
    ],
)
def test_list_and_index_ast_shape(expression: str, expected: str) -> None:
    assert ast(expression) == expected


def test_empty_index_reports_error() -> None:
    parser = parser_for("print xs[];")
    parser.parse()

    assert parser.reporter.had_error


def test_bare_list_type_reports_error() -> None:
    parser = parser_for("val xs: List = [];")
    parser.parse()

    assert parser.reporter.had_error
    assert ast("1 + 2 << 2") == "(<< (+ 1 2) 2)"
    assert ast("1 << 1 + 2") == "(<< 1 (+ 1 2))"
    assert ast("5 & 3 | 8") == "(| (& 5 3) 8)"
    assert ast("~0 & 0xFF") == "(& (~ 0) 255)"


def test_conditional_and_coalesce_ast_shape() -> None:
    assert ast("1 if true else 2") == "(if true 1 2)"
    assert ast("1 ?? 2") == "(?? 1 2)"
    assert ast("1 ?? 2 or 3") == "(?? 1 (or 2 3))"
    assert ast("1 ?? 2 if true else 3") == "(if true (?? 1 2) 3)"
    assert ast("1 if true else 2 ?? 3") == "(if true 1 (?? 2 3))"
    assert ast("1 if true else 2 if false else 3") == (
        "(if true 1 (if false 2 3))"
    )


def test_optional_chain_ast_shape() -> None:
    assert ast("a?.b") == "(?. b a)"
    assert ast("a?.b.c") == "(. c (?. b a))"
    assert ast("a?.m()") == "(?call (?. m a))"
    assert ast("a?.m()?.x") == "(?. x (?call (?. m a)))"
    assert ast("a?.b()") == "(?call (?. b a))"


def test_optional_assignment_reports_error() -> None:
    parser = parser_for("a?.b = 1;")
    parser.parse()

    assert parser.reporter.had_error


def test_nested_optional_assignment_reports_error() -> None:
    parser = parser_for("a?.b.c = 1;")
    parser.parse()

    assert parser.reporter.had_error


def test_parses_function_declaration() -> None:
    statements = parse("fn soma(a, b) { return a + b; }")

    assert len(statements) == 1
    function = statements[0]
    assert isinstance(function, Function)
    assert function.name.lexeme == "soma"
    assert [param.name.lexeme for param in function.params] == ["a", "b"]
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
    assert [param.name.lexeme for param in klass.methods[0].params] == ["a"]


def test_property_and_this_ast_shape() -> None:
    assert ast("a.b") == "(. b a)"
    assert ast("this.x") == "(. x this)"
    assert ast("a.b = 1") == "(set b a 1)"


def test_parses_class_with_superclass() -> None:
    statements = parse("class B(A) {}")

    klass = statements[0]
    assert isinstance(klass, Class)
    assert klass.superclass is not None
    assert klass.superclass.name.lexeme == "A"


def test_parses_type_annotations() -> None:
    statements = parse('fn f(a: Int, b: String = "x") -> Bool { return true; }')

    function = statements[0]
    assert isinstance(function, Function)

    first, second = function.params[0].type_annotation, function.params[1].type_annotation
    return_type = function.return_type
    assert first is not None and second is not None and return_type is not None
    assert display(first) == "Int"
    assert display(second) == "String"
    assert display(return_type) == "Bool"


def test_parses_function_type_annotations() -> None:
    statements = parse(
        "fn aplicar(f: fn(Int) -> String, g: (fn() -> Int)?)"
        " -> fn(String) -> Int { return f; }"
    )

    function = statements[0]
    assert isinstance(function, Function)

    first, second = function.params[0].type_annotation, function.params[1].type_annotation
    return_type = function.return_type
    assert first is not None and second is not None and return_type is not None
    assert display(first) == "fn(Int) -> String"
    assert display(second) == "(fn() -> Int) | Nil"
    assert display(return_type) == "fn(String) -> Int"


def test_parses_lambda_expression_body() -> None:
    statements = parse("val f = fn(x: Int) => x * 2;")

    declaration = statements[0]
    assert isinstance(declaration, Var)
    initializer = declaration.initializer
    assert isinstance(initializer, Lambda)

    param = initializer.params[0]
    assert param.type_annotation is not None
    assert display(param.type_annotation) == "Int"
    assert initializer.return_type is None
    assert len(initializer.body) == 1
    assert isinstance(initializer.body[0], Return)


def test_parses_lambda_block_body_and_return_type() -> None:
    statements = parse("val f = fn(x: Int) -> Int { return x * 2; };")

    declaration = statements[0]
    assert isinstance(declaration, Var)
    initializer = declaration.initializer
    assert isinstance(initializer, Lambda)

    assert initializer.return_type is not None
    assert display(initializer.return_type) == "Int"
    assert isinstance(initializer.body[0], Return)


def test_parses_lambda_at_statement_start() -> None:
    statements = parse("fn(x: Int) => x * 2;")

    statement = statements[0]
    assert isinstance(statement, Expression)
    assert isinstance(statement.expression, Lambda)


def test_lambda_parameters_cannot_have_defaults() -> None:
    parser = parser_for("val f = fn(x: Int = 1) => x;")
    parser.parse()

    assert parser.reporter.had_error


def test_parses_is_expression() -> None:
    statements = parse("val ok = x is Int | String;")

    declaration = statements[0]
    assert isinstance(declaration, Var)
    initializer = declaration.initializer
    assert isinstance(initializer, Is)
    assert display(initializer.test_type) == "Int | String"


def test_is_binds_tighter_than_equality() -> None:
    assert ast("1 is Int == true") == "(== (is 1 Int) true)"
    assert ast("xs is List[Int]") == "(is xs List[Int])"


def test_parses_field_and_variable_types() -> None:
    statements = parse("class C { val x: Int; var y: List[Int]? = nil; }")

    klass = statements[0]
    assert isinstance(klass, Class)

    field_type = klass.fields[0].type_annotation
    list_type = klass.fields[1].type_annotation
    assert field_type is not None and list_type is not None
    assert display(field_type) == "Int"
    assert display(list_type) == "List[Int] | Nil"


def test_old_inheritance_syntax_reports_error() -> None:
    parser = parser_for("class B < A {}")
    parser.parse()

    assert parser.reporter.had_error


def test_super_ast_shape() -> None:
    assert ast("super.m()") == "(call (super m))"


def test_val_and_var_mutability_flags() -> None:
    statements = parse("val a = 1; var b = 2;")

    val_stmt, var_stmt = statements
    assert isinstance(val_stmt, Var)
    assert isinstance(var_stmt, Var)
    assert val_stmt.mutable is False
    assert var_stmt.mutable is True


def test_val_requires_initializer() -> None:
    parser = parser_for("val a;")
    parser.parse()

    assert parser.reporter.had_error


def test_parameters_can_be_var() -> None:
    statements = parse("fn f(a, var b) {}")

    function = statements[0]
    assert isinstance(function, Function)
    assert [(param.name.lexeme, param.mutable) for param in function.params] == [
        ("a", False),
        ("b", True),
    ]
