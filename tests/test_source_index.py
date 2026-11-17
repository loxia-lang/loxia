# SPDX-License-Identifier: MIT OR Apache-2.0
"""Spans de expressão: índice offset → menor expressão (ADR-0090)."""

from __future__ import annotations

from loxia.cli import Loxia
from loxia.source_index import SourceIndex


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


def test_span_de_agrupamento_inclui_parenteses() -> None:
    source = "val x = (1 + 2)\n"
    spans = index(source)
    span = spans.at(source.index("("))
    assert span is not None
    assert source[span.start : span.end] == "(1 + 2)"


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
