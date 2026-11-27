# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import pytest

from loxia.formatter.doc import (
    Doc,
    TrailingComment,
    concat,
    group,
    hardline,
    if_break,
    indent,
    join,
    line,
    render,
    softline,
    text,
)


def rendered(doc: Doc, width: int = 100) -> list[str]:
    return list(render(doc, width).lines)


def test_flat_group_fits_at_exact_width() -> None:
    doc = group(concat(text("abc"), line(), text("de")))

    assert rendered(doc, 6) == ["abc de"]
    assert rendered(doc, 5) == ["abc", "de"]


def test_softline_is_empty_flat_and_breaks_broken() -> None:
    doc = group(concat(text("f("), indent(concat(softline(), text("x"))), softline(), text(")")))

    assert rendered(doc, 20) == ["f(x)"]
    assert rendered(doc, 2) == ["f(", "  x", ")"]


def test_indent_applies_to_every_broken_line() -> None:
    doc = concat(
        text("f("), indent(concat(line(), text("x"), line(), text("y"))), line(), text(")")
    )

    assert rendered(doc, 100) == ["f(", "  x", "  y", ")"]


def test_hardline_forces_the_enclosing_group_to_break() -> None:
    doc = group(concat(text("a"), hardline(), text("b")))

    assert rendered(doc, 100) == ["a", "b"]


def test_if_break_picks_the_flat_branch_when_the_group_fits() -> None:
    doc = group(
        concat(
            text("["),
            indent(concat(softline(), text("1"), if_break(text(","), text("")))),
            softline(),
            text("]"),
        )
    )

    assert rendered(doc, 20) == ["[1]"]
    assert rendered(doc, 1) == ["[", "  1,", "]"]


def test_nested_group_decides_on_its_own_line() -> None:
    inner = group(concat(text("x"), line(), text("y")))
    outer = group(concat(text("("), indent(concat(softline(), inner)), softline(), text(")")))

    assert rendered(outer, 10) == ["(x y)"]
    assert rendered(outer, 3) == ["(", "  x", "  y", ")"]


def test_multiline_text_is_kept_verbatim() -> None:
    doc = concat(text('val s = """a'), text("\nb"), text('"""'))

    assert rendered(doc, 100) == ['val s = """a', 'b"""']


def test_text_width_counts_code_points() -> None:
    doc = group(concat(text("é"), line(), text("ü")))

    assert rendered(doc, 3) == ["é ü"]
    assert rendered(doc, 2) == ["é", "ü"]


def test_trailing_comment_forces_the_group_to_break() -> None:
    doc = group(concat(text("a"), TrailingComment("# c"), line(), text("b")))

    assert rendered(doc, 100) == ["a # c", "b"]


def test_trailing_comment_records_its_start_column() -> None:
    doc = concat(text("val x = 1"), TrailingComment("# note"))

    result = render(doc, 100)

    assert result.lines == ("val x = 1 # note",)
    assert result.trailing == (9,)


def test_join_inserts_the_separator_between_items() -> None:
    doc = group(join(concat(text(","), line()), (text("a"), text("b"), text("c"))))

    assert rendered(doc, 100) == ["a, b, c"]
    assert rendered(doc, 3) == ["a,", "b,", "c"]


def test_empty_doc_renders_no_lines() -> None:
    assert rendered(concat(), 100) == []


def test_render_is_deterministic() -> None:
    doc = group(join(concat(text(","), line()), (text("a"), text("b"))))

    assert render(doc, 3) == render(doc, 3)


def test_width_must_be_positive() -> None:
    with pytest.raises(ValueError, match="width must be >= 1"):
        render(text("x"), 0)
