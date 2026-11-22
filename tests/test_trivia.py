# SPDX-License-Identifier: MIT OR Apache-2.0
"""Trivia: round-trip da fonte e attachment determinístico (ADR-0134)."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from loxia.engine import Loxia
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.trivia import Trivia, TriviaKind, TriviaTable, render

ROOT = Path(__file__).resolve().parents[1]


def _scan(source: str) -> tuple[list[Token], list[Trivia]]:
    scanner = Scanner(source)
    tokens = scanner.scan_tokens()
    return list(tokens), list(scanner.trivia)


@pytest.mark.parametrize(
    "source",
    [
        "# topo\nval x = 1  # trailing\n\n# leading\nval y = 2\n",
        "/// doc\nfn f() -> Int { return 1 }\n",
        "/* bloco\n   com /* aninhado */ fim */\nval x = 1\n",
        'val s = "é"  # utf-8\nprint(s)\n',
        "val xs = [\n  1,  # um\n  2,  # dois\n]\n",
        "class C {\n  val n: Int\n\n  fn get() -> Int { return this.n }\n}\n",
        "",
    ],
)
def test_render_roundtrips_fixtures(source: str) -> None:
    tokens, trivia = _scan(source)

    assert render(tokens, trivia, source) == source


def test_render_roundtrips_the_corpus() -> None:
    paths = sorted(
        {
            *ROOT.glob("std/**/*.lx"),
            *ROOT.glob("tests/cases/**/*.lx"),
            *ROOT.glob("examples/**/*.lx"),
        }
    )
    assert paths

    for path in paths:
        source = path.read_text(encoding="utf-8")
        scanner = Scanner(source)
        tokens = scanner.scan_tokens()
        assert render(tokens, scanner.trivia, source) == source, path


def test_engine_exposes_trivia_and_attachment() -> None:
    source = "val x = 1  # trailing\n\n# leading\nval y = 2\n"
    lox = Loxia()
    lox.use_file("trivia.lx")
    lox.check(source, emit=False)

    statements = lox.last_statements
    assert statements is not None
    tokens = lox.last_tokens
    assert tokens is not None
    table = TriviaTable(tuple(tokens), tuple(lox.last_trivia))
    spans = lox.last_source_index
    assert spans is not None
    x_span = spans.span_of(statements[0])
    y_span = spans.span_of(statements[1])
    assert x_span is not None
    assert y_span is not None

    assert [item.text for item in table.comments_after(x_span)] == ["# trailing"]
    assert [item.text for item in table.comments_before(y_span)] == ["# leading"]
    assert table.blank_lines_before(y_span) == 0


def test_blank_line_breaks_comment_ownership() -> None:
    source = "val x = 1\n# orphan\n\nval y = 2\n"
    lox = Loxia()
    lox.use_file("trivia.lx")
    lox.check(source, emit=False)
    statements = lox.last_statements
    tokens = lox.last_tokens
    assert statements is not None
    assert tokens is not None
    table = TriviaTable(tuple(tokens), tuple(lox.last_trivia))
    spans = lox.last_source_index
    assert spans is not None
    span = spans.span_of(statements[1])
    assert span is not None

    assert table.comments_before(span) == ()
    assert table.blank_lines_before(span) == 1


def test_render_rejects_uncovered_source() -> None:
    source = "val x = 1\n"
    tokens, _ = _scan(source)
    with pytest.raises(ValueError, match="uncovered source bytes"):
        render(tokens, [], source)


def test_trailing_after_multiline_token_is_not_leading() -> None:
    source = 'val s = """\nabc"""  # trailing\nval y = 2\n'
    lox = Loxia()
    lox.use_file("trivia.lx")
    lox.check(source, emit=False)
    statements = lox.last_statements
    tokens = lox.last_tokens
    assert statements is not None
    assert tokens is not None
    table = TriviaTable(tuple(tokens), tuple(lox.last_trivia))
    spans = lox.last_source_index
    assert spans is not None
    first = spans.span_of(statements[0])
    second = spans.span_of(statements[1])
    assert first is not None
    assert second is not None

    assert [item.text for item in table.comments_after(first)] == ["# trailing"]
    assert table.comments_before(second) == ()


def test_doc_comment_is_trivia_and_token_doc() -> None:
    source = "/// documenta\nfn f() -> Int { return 1 }\n"
    tokens, trivia = _scan(source)

    doc = next(item for item in trivia if item.kind is TriviaKind.DOC_COMMENT)
    assert doc.text == "/// documenta"
    fn_token = next(token for token in tokens if token.type is TokenType.FN)
    assert fn_token.doc == "documenta"


def test_blank_line_count_uses_only_consecutive_newlines() -> None:
    source = "val x = 1\n\n\nval y = 2\n"
    lox = Loxia()
    lox.use_file("trivia.lx")
    lox.check(source, emit=False)
    statements = lox.last_statements
    tokens = lox.last_tokens
    assert statements is not None
    assert tokens is not None
    table = TriviaTable(tuple(tokens), tuple(lox.last_trivia))
    spans = lox.last_source_index
    assert spans is not None
    span = spans.span_of(statements[1])
    assert span is not None

    assert table.blank_lines_before(span) == 2


@given(
    st.text(
        alphabet="#/*\n abc123()[]{}\t",
        max_size=80,
    )
)
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_render_roundtrip_property(source: str) -> None:
    tokens, trivia = _scan(source)

    assert render(tokens, trivia, source) == source
