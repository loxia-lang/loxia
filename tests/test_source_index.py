# SPDX-License-Identifier: MIT OR Apache-2.0
"""Spans de expressão: índice offset → menor expressão (ADR-0090)."""

from __future__ import annotations

import pytest

from loxia.engine import Loxia
from loxia.source_index import ExprSpan, SourceIndex
from loxia_core.diagnostics.diagnostic import Position, Span
from loxia_core.frontend.expr import LiteralPattern, Match
from loxia_core.frontend.source_index import NodeSpan
from loxia_core.frontend.stmt import Function, Var


def index(source: str) -> SourceIndex:
    lox = Loxia()
    lox._file = "test.lx"
    lox._sources.add("test.lx", source)
    lox.check(source, emit=False)
    value = lox.last_source_index
    assert isinstance(value, SourceIndex)
    return value


def test_span_de_binaria_e_literal() -> None:
    source = "val x = 1 + 2 * 3\n"
    spans = index(source)
    plus = source.index("+")
    span = spans.at(plus)
    assert span is not None
    assert source[span.start : span.end] == "1 + 2 * 3"
    two = source.index("2")
    literal = spans.at(two)
    assert literal is not None
    assert source[literal.start : literal.end] == "2"


def test_span_de_agrupamento_inclui_parenteses_e_indexa_filhos() -> None:
    source = "val x = (1 + 2)\n"
    spans = index(source)
    span = spans.at(source.index("("))
    assert span is not None
    assert source[span.start : span.end] == "(1 + 2)"
    literal = spans.at(source.index("1"))
    assert literal is not None
    assert source[literal.start : literal.end] == "1"


def test_span_de_chamada_inclui_parentese() -> None:
    source = "fn f(a: Int) -> Int { return a }\nval x = f(1)\n"
    spans = index(source)
    span = spans.at(source.index("(1)"))
    assert span is not None
    assert source[span.start : span.end] == "f(1)"


def test_texto_e_linha_do_span() -> None:
    source = "val x = 1\nval y = (x + 2)\n"
    spans = index(source)
    span = spans.at(source.index("("))

    assert span is not None
    assert spans.text_of(span) == "(x + 2)"
    assert spans.line_of(span) == 2


def test_span_of_declaracao_e_de_anotacao_de_tipo() -> None:
    source = "fn f(x: List[Int]) -> Int { return 1 }\n"
    lox = Loxia()
    lox._file = "test.lx"
    lox._sources.add("test.lx", source)
    lox.check(source, emit=False)
    spans = lox.last_source_index
    assert isinstance(spans, SourceIndex)
    parsed = lox.last_statements
    assert parsed is not None
    function = parsed[0]
    assert isinstance(function, Function)
    param = function.params[0]
    assert param.type_span is not None

    declaration = spans.span_of(param)
    annotation = spans.span_of(param.type_span)

    assert declaration is not None
    assert spans.text_of(declaration) == "x: List[Int]"
    assert annotation is not None
    assert spans.text_of(annotation) == "List[Int]"


def test_node_span_expression_rejects_non_expr() -> None:
    span = NodeSpan(object(), 0, 1)
    with pytest.raises(TypeError):
        _ = span.expression


def test_literal_pattern_span_covers_negative_literal() -> None:
    source = 'val n = 5\nval x = match n { 1 => "um"\n  -2 => "menos dois"\n  _ => "outro" }\n'
    lox = Loxia()
    lox._file = "test.lx"
    lox._sources.add("test.lx", source)
    lox.check(source, emit=False)
    spans = lox.last_source_index
    statements = lox.last_statements
    assert isinstance(spans, SourceIndex)
    assert statements is not None

    declaration = statements[1]
    assert isinstance(declaration, Var)
    expression = declaration.initializer
    assert isinstance(expression, Match)
    positive = expression.arms[0].pattern
    negative = expression.arms[1].pattern
    assert isinstance(positive, LiteralPattern)
    assert isinstance(negative, LiteralPattern)

    positive_span = spans.span_of(positive)
    negative_span = spans.span_of(negative)
    assert positive_span is not None
    assert negative_span is not None
    assert spans.text_of(positive_span) == "1"
    assert spans.text_of(negative_span) == "-2"

    at_minus = spans.at(source.index("-2"))
    assert at_minus is not None
    assert spans.text_of(at_minus) == "-2"


def test_source_index_out_of_range_and_missing_source() -> None:
    source = "val x = 1\n"
    spans = index(source)
    assert spans.at(len(source) + 10) is None
    assert spans.text_of(NodeSpan(object(), 0, 1, "missing.lx")) is None
    assert spans.line_of(NodeSpan(object(), 0, 1, "missing.lx")) is None

    invalid = NodeSpan(object(), -1, 1)
    assert spans.text_of(invalid) is None
    assert spans.line_of(invalid) is None


@pytest.mark.parametrize(
    "source",
    [
        "val x: Int = 1\n",
        "fn f(a: Int) -> Int { return a }\n",
        "class C { val n: Int = 1 }\n",
        "enum E { A(Int) }\n",
        "interface I { fn f() -> Int; }\n",
        "type A = Int\n",
    ],
)
def test_declaration_statements_have_spans(source: str) -> None:
    lox = Loxia()
    lox._file = "test.lx"
    lox._sources.add("test.lx", source)
    lox.check(source, emit=False)
    spans = lox.last_source_index
    statements = lox.last_statements
    assert isinstance(spans, SourceIndex)
    assert statements is not None

    span = spans.span_of(statements[0])
    assert span is not None
    assert spans.text_of(span) == source.strip()


def test_expr_span_legacy_constructor_still_works() -> None:
    payload = Loxia().parse_file("val x = 1\n")
    assert payload is not None
    _, statements = payload
    declaration = statements[0]
    assert isinstance(declaration, Var)
    expression = declaration.initializer

    span = ExprSpan(expression=expression, start=8, end=9)

    assert span.expression is expression
    assert span.node is expression


def test_at_filters_spans_by_file() -> None:
    main = Span("main.lx", Position(1, 6, 5), Position(1, 10, 9))
    module = Span("mod.lx", Position(1, 6, 5), Position(1, 8, 7))
    spans = SourceIndex([], "", extra_spans=[main, module])

    main_span = spans.at(5, file="main.lx")
    module_span = spans.at(5, file="mod.lx")
    unfiltered = spans.at(5)

    assert main_span is not None and (main_span.start, main_span.end) == (5, 9)
    assert module_span is not None and (module_span.start, module_span.end) == (5, 7)
    # Sem filtro o menor span vence; o filtro escolhe a autoridade do arquivo.
    assert unfiltered is not None and (unfiltered.start, unfiltered.end) == (5, 7)


def test_type_name_spans_are_exact_inside_annotation() -> None:
    source = "class Foo {}\nval xs: List[Foo] = []\n"
    spans = index(source)

    list_span = spans.at(source.index("List"))
    foo_span = spans.at(source.index("Foo", source.index("[")))

    assert list_span is not None and list_span.kind == "type"
    assert spans.text_of(list_span) == "List"
    assert foo_span is not None and foo_span.kind == "type"
    assert spans.text_of(foo_span) == "Foo"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("val x: Int = 1\n", ["Int"]),
        ("type A = Foo | Bar\n", ["Foo", "Bar"]),
        ("enum E { A(Int, Foo), B }\n", ["Int", "Foo"]),
        (
            "fn f(a: Int, b: List[String]) -> Map[Int, Foo] { return a }\n",
            ["Int", "List", "String", "Map", "Int", "Foo"],
        ),
        ("fn f(g: fn(Int) -> Foo) -> Int { return 1 }\n", ["Int", "Foo", "Int"]),
        ("val xs: Int? = nil\n", ["Int"]),
    ],
)
def test_type_name_spans_cover_all_type_positions(source: str, expected: list[str]) -> None:
    spans = index(source)
    found = [spans.text_of(span) for span in spans.spans if span.kind == "type"]

    assert found == expected


def test_declaration_name_spans_cover_params_fields_and_variants() -> None:
    source = (
        "fn soma(a: Int, b: Int) -> Int { return a + b }\n"
        "enum E { A, B(Int) }\n"
        "class C { val campo: Int = 1 }\n"
        "type Alias = Int\n"
        "val global = 1\n"
        "interface I { fn m(x: Int) -> Int; }\n"
        "fn id[T](x: T) -> T { return x }\n"
        "fn demo() {\n"
        "  val (a, (b, c)) = (1, (2, 3))\n"
        "  for item in 0..3 { print(item) }\n"
        "  val f = fn(y: Int) -> Int => y\n"
        "}\n"
    )
    spans = index(source)
    names = {spans.text_of(span) for span in spans.spans if span.kind == "name"}

    assert {
        "soma",
        "a",
        "b",
        "E",
        "A",
        "B",
        "C",
        "campo",
        "Alias",
        "global",
        "I",
        "m",
        "x",
        "id",
        "T",
        "demo",
        "c",
        "item",
        "f",
        "y",
    } <= names


def test_source_index_has_no_duplicate_extent() -> None:
    source = "fn f(x: List[Int]) -> Int {\n  val y: Int = x\n  return y\n}\n"
    spans = index(source)
    keys = [(span.start, span.end, span.file) for span in spans.spans]

    assert len(keys) == len(set(keys))
    assert spans.spans


def test_type_name_spans_are_utf8_exact_across_lines() -> None:
    source = '# é\nfn f(\n  x: List[Int],\n) -> String {\n  return ""\n}\n'
    spans = index(source)
    found = [span for span in spans.spans if span.kind == "type"]
    texts = {spans.text_of(span) for span in found}

    assert {"List", "Int", "String"} <= texts
    inner = next(span for span in found if spans.text_of(span) == "Int")
    assert inner.start == len(source[: source.index("Int")].encode("utf-8"))
    assert spans.line_of(inner) == 3
