# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import sys

import pytest

from loxia_core.diagnostics.errors import ParseError
from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.destructuring import NamePattern, TuplePattern, pattern_names
from loxia_core.frontend.expr import Call, Expr, Is, Lambda, MapLiteral, Match, Variable
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import (
    Class,
    Destructure,
    EnumDecl,
    ErrorStmt,
    Expression,
    ForIn,
    Function,
    If,
    Raise,
    Return,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from loxia_core.frontend.ty import ClassTy, ListTy, display


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
        ("not nil", "(not nil)"),
        ("a", "a"),
        ("0..10", "(.. 0 10)"),
        ("0..1 + 2", "(.. 0 (+ 1 2))"),
    ],
)
def test_precedence_and_ast_shape(expression: str, expected: str) -> None:
    assert ast(expression) == expected


def test_parses_statements() -> None:
    statements = parse("var a = 1; print(a); if (a) print(0); while (a) a = 0;")

    assert isinstance(statements[0], Var)
    assert isinstance(statements[1], Expression)
    assert isinstance(statements[2], If)
    assert isinstance(statements[3], While)


def test_parses_for_in_statement() -> None:
    statements = parse("for i in 0..3 print(i);")

    assert isinstance(statements[0], ForIn)
    assert statements[0].name.lexeme == "i"


def test_c_style_for_is_rejected_with_migration_hint() -> None:
    parser = parser_for("for (var i = 0; i < 3; i = i + 1) print(i);")
    parser.parse()

    assert parser.reporter.had_error
    assert any(
        "C-style 'for' was removed" in item.message for item in parser.reporter.batch().diagnostics
    )


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
    statements = parse("val a = 1\nprint(a)\n")

    assert len(statements) == 2
    assert isinstance(statements[0], Var)
    assert isinstance(statements[1], Expression)


def test_elif_is_nested_if() -> None:
    statements = parse("if (a) print(1)\nelif (b) print(2)\nelse print(3)")

    outer = statements[0]
    assert isinstance(outer, If)
    assert isinstance(outer.else_branch, If)
    assert isinstance(outer.else_branch.else_branch, Expression)


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
    parser = parser_for("var = 1;\nprint(2);")
    statements = parser.parse()

    assert parser.reporter.had_error
    assert statements is not None
    assert len(statements) == 2
    assert isinstance(statements[0], ErrorStmt)
    assert isinstance(statements[1], Expression)


@pytest.mark.parametrize("source", ["1 + 1", "1 + 1;", "print(1)", "var x = 5"])
def test_repl_accepts_missing_final_semicolon(source: str) -> None:
    parser = parser_for(source, repl=True)
    statements = parser.parse_repl()

    assert statements is not None
    assert len(statements) == 1


def test_repl_wraps_bare_expression_in_print() -> None:
    statements = parser_for("1 + 1", repl=True).parse_repl()

    assert statements is not None
    assert isinstance(statements[0], Expression)
    assert isinstance(statements[0].expression, Call)
    callee = statements[0].expression.callee
    assert isinstance(callee, Variable)
    assert callee.name.lexeme == "print"


def test_repl_does_not_double_print_explicit_print() -> None:
    statements = parser_for("print(1)", repl=True).parse_repl()

    assert statements is not None
    assert isinstance(statements[0], Expression)
    assert isinstance(statements[0].expression, Call)


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
    parser = parser_for("print(xs[]);")
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
    assert ast("1 if true else 2 if false else 3") == ("(if true 1 (if false 2 3))")


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


def test_parses_generic_function_type_params() -> None:
    statements = parse("fn map[T, U](xs: List[T], f: fn(T) -> U) -> List[U] { return []; }")

    function = statements[0]
    assert isinstance(function, Function)
    assert [token.lexeme for token in function.type_params] == ["T", "U"]
    first = function.params[0].type_annotation
    second = function.params[1].type_annotation
    assert first is not None and second is not None
    assert display(first) == "List[T]"
    assert display(second) == "fn(T) -> U"


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


def test_class_type_annotation_preserva_token_sem_mudar_igualdade() -> None:
    statements = parse("fn f(a: Point) -> List[Point] { return a; }")
    function = statements[0]
    assert isinstance(function, Function)
    annotation = function.params[0].type_annotation
    return_type = function.return_type
    assert isinstance(annotation, ClassTy)
    assert annotation.token is not None
    assert annotation.token.lexeme == "Point"

    assert isinstance(return_type, ListTy)
    element = return_type.element
    assert isinstance(element, ClassTy)
    assert element.token is not None
    assert element.token.lexeme == "Point"

    assert annotation == ClassTy("Point")
    assert hash(annotation) == hash(ClassTy("Point"))


def test_parses_function_type_annotations() -> None:
    statements = parse(
        "fn aplicar(f: fn(Int) -> String, g: (fn() -> Int)?) -> fn(String) -> Int { return f; }"
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
    statements = parse("val ok = x is (Int | String);")

    declaration = statements[0]
    assert isinstance(declaration, Var)
    initializer = declaration.initializer
    assert isinstance(initializer, Is)
    assert display(initializer.test_type) == "Int | String"


def test_is_union_requires_parentheses() -> None:
    parser = parser_for("val ok = x is Int | String;")
    parser.parse()

    assert parser.reporter.had_error


def test_leading_operator_inside_brackets() -> None:
    assert ast("(1\n + 2)") == "(group (+ 1 2))"
    assert ast("[1\n + 2]") == "(list (+ 1 2))"


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


def test_parse_as_binds_tighter_than_addition() -> None:
    statements = parse("print(3.9 as Int + 1);")
    printed = statements[0]
    assert isinstance(printed, Expression)


def test_tuple_literal_and_grouping() -> None:
    assert ast("(1)") == "(group 1)"
    assert ast("(1, 2)") == "(tuple 1 2)"
    assert ast("(1, (2, 3))") == "(tuple 1 (tuple 2 3))"
    assert ast('("a", 1 + 2)') == '(tuple "a" (+ 1 2))'


def test_destructuring_shape() -> None:
    statements = parse('val (a, b) = (1, 2); var (c, d): (Int, String) = (3, "x");')

    first = statements[0]
    assert isinstance(first, Destructure)
    assert [name.lexeme for name in pattern_names(first.pattern)] == ["a", "b"]
    assert first.mutable is False
    assert first.type_annotation is None

    second = statements[1]
    assert isinstance(second, Destructure)
    assert second.mutable is True
    annotation = second.type_annotation
    assert annotation is not None
    assert display(annotation) == "(Int, String)"


def test_nested_destructuring_shape() -> None:
    statements = parse('val (a, (b, c)): (Int, (Int, String)) = (1, (2, "x"));')

    statement = statements[0]
    assert isinstance(statement, Destructure)
    pattern = statement.pattern
    assert isinstance(pattern, TuplePattern)
    assert isinstance(pattern.elements[0], NamePattern)
    assert isinstance(pattern.elements[1], TuplePattern)
    assert [name.lexeme for name in pattern_names(pattern)] == ["a", "b", "c"]
    assert statement.accept(AstPrinter()) == (
        '(val-destructure (a (b c)): (Int, (Int, String)) (tuple 1 (tuple 2 "x")))'
    )


@pytest.mark.parametrize(
    "source",
    [
        "(1,)",
        "()",
        "val (a) = (1, 2);",
    ],
)
def test_tuple_parse_errors(source: str) -> None:
    parser = parser_for(source)
    parser.parse()

    assert parser.reporter.had_error


def test_parses_type_param_bounds() -> None:
    statements = parse("fn f[T: Ord + Forma, U: Num](a: T, b: U) -> T { return a; }")

    function = statements[0]
    assert isinstance(function, Function)
    assert [token.lexeme for token in function.type_params] == ["T", "U"]
    assert [[token.lexeme for token in bounds] for bounds in function.type_param_bounds] == [
        ["Ord", "Forma"],
        ["Num"],
    ]


def test_class_type_param_bounds_are_rejected() -> None:
    parser = parser_for("class C[T: Ord] {}")
    parser.parse()

    assert parser.reporter.had_error


def test_parses_type_alias() -> None:
    statements = parse("type UserId = Int;")

    alias = statements[0]
    assert isinstance(alias, TypeAlias)
    assert alias.name.lexeme == "UserId"
    assert display(alias.target) == "Int"


def test_generic_type_alias_is_rejected() -> None:
    parser = parser_for("type BoxAlias[T] = List[T];")
    parser.parse()

    assert parser.reporter.had_error


def test_parses_variadic_parameter_and_spread_call() -> None:
    statements = parse('fn f(a: Int, ...xs: String) -> Int { return a; } f(1, ...["a", "b"]);')

    function = statements[0]
    assert isinstance(function, Function)
    assert function.params[0].variadic is False
    assert function.params[1].variadic is True

    call = statements[1]
    assert isinstance(call, Expression)
    assert isinstance(call.expression, Call)
    assert call.expression.spread is True
    assert len(call.expression.arguments) == 2


def test_variadic_parameter_must_be_last() -> None:
    parser = parser_for("fn f(...xs: Int, y: Int) -> Int { return y; }")
    parser.parse()

    assert parser.reporter.had_error


def test_parses_variadic_function_type() -> None:
    statements = parse("val f: fn(String, ...Int) -> String = fn(p, ...xs) => p;")

    var = statements[0]
    assert isinstance(var, Var)
    annotation = var.type_annotation
    assert annotation is not None
    assert display(annotation) == "fn(String, ...Int) -> String"


def test_generic_class_and_type_arguments() -> None:
    statements = parse(
        "class Box[T] { var value: T; init(value: T) { this.value = value; } "
        "get() -> T { return this.value; } }"
    )

    first = statements[0]
    assert isinstance(first, Class)
    assert [token.lexeme for token in first.type_params] == ["T"]
    assert AstPrinter().print_program([first]).startswith("(class Box[T]")


def test_class_type_argument_annotation_parses() -> None:
    statements = parse("val b: Box[Int] = Box(1);")
    statement = statements[0]
    assert isinstance(statement, Var)
    annotation = statement.type_annotation

    assert annotation is not None
    assert display(annotation) == "Box[Int]"


def test_generic_superclass_is_rejected() -> None:
    parser = parser_for("class C(Box[Int]) {}")
    parser.parse()

    assert parser.reporter.had_error


def test_enum_and_match_parse() -> None:
    statements = parse(
        "enum Result[T, E] { Ok(T), Err(E) } "
        "val r = match Result.Ok(1) { Result.Ok(v) => v, Result.Err(e) => e };"
    )

    enum_decl = statements[0]
    assert isinstance(enum_decl, EnumDecl)
    assert [token.lexeme for token in enum_decl.type_params] == ["T", "E"]
    assert [variant.name.lexeme for variant in enum_decl.variants] == [
        "Ok",
        "Err",
    ]
    assert AstPrinter().print_program(statements).startswith("(enum Result[T, E]")

    assert isinstance(statements[1], Var)
    assert isinstance(statements[1].initializer, Match)
    assert len(statements[1].initializer.arms) == 2


def test_try_and_raise_parse() -> None:
    statements = parse(
        'try { raise "x"; } except RuntimeError as e { print(e); } finally { print(1); }'
    )

    first = statements[0]
    assert isinstance(first, Try)
    assert len(first.handlers) == 1
    assert first.handlers[0].type_name.lexeme == "RuntimeError"
    assert first.handlers[0].binding.lexeme == "e"
    assert first.finally_body is not None
    assert isinstance(first.body[0], Raise)
    assert first.body[0].value is not None
    assert AstPrinter().print_program(statements).startswith("(try")


def test_deeply_nested_input_is_a_syntax_error_and_not_a_crash() -> None:
    # Found by the Atheris target (`fuzz/fuzz_frontend.py`): the recursive descent parser
    # exhausted the Python stack on `[[[[...` before it could report anything. The limit
    # is pinned here because the interpreter raises it globally (`execution/limits.py`).
    previous = sys.getrecursionlimit()
    sys.setrecursionlimit(2000)
    try:
        parser = parser_for("[" * 300)
        statements = parser.parse()
    finally:
        sys.setrecursionlimit(previous)

    assert statements == []
    assert parser.reporter.had_error
    assert "Too deeply nested." in [
        diagnostic.message for diagnostic in parser.reporter.batch().diagnostics
    ]


def test_parse_progress_guard_advances_when_a_declaration_does_not_move() -> None:
    class StuckParser(Parser):
        def _declaration(self) -> Stmt | None:
            return None

    parser = StuckParser(Scanner("1\n").scan_tokens())
    assert parser.parse() == []
    assert parser._current > 0


def test_parse_expression_rejects_trailing_tokens() -> None:
    parser = parser_for("1 2")
    with pytest.raises(ParseError, match="Expect end of interpolation"):
        parser.parse_expression()


class _RecursionParser(Parser):
    def _expression(self) -> Expr:
        raise RecursionError


def test_parse_expression_reports_too_deeply_nested() -> None:
    parser = _RecursionParser(Scanner("1\n").scan_tokens())
    with pytest.raises(ParseError, match="Too deeply nested"):
        parser.parse_expression()


def test_parse_repl_falls_back_on_too_deeply_nested() -> None:
    parser = _RecursionParser(Scanner("1\n").scan_tokens(), repl=True)
    statements = parser.parse_repl()
    assert statements is not None
    assert parser.reporter.had_error
