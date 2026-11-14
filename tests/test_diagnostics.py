from __future__ import annotations

import json
from pathlib import Path

from src.diagnostics.codes import Code
from src.diagnostics.diagnostic import (
    Diagnostic,
    DiagnosticBatch,
    Phase,
    Position,
    Severity,
    Span,
)
from src.diagnostics.render import (
    render_batch,
    render_human,
    render_json,
    render_runtime,
    render_short,
)
from src.diagnostics.source import SourceMap, display_path, display_text, display_width


def _span(
    *,
    file: str = "x.lox",
    line: int = 1,
    column: int = 1,
    end_line: int | None = None,
    end_column: int | None = None,
    offset: int = 0,
    end_offset: int | None = None,
) -> Span:
    return Span(
        file,
        Position(line, column, offset),
        Position(
            end_line if end_line is not None else line,
            end_column if end_column is not None else column + 1,
            end_offset if end_offset is not None else offset + 1,
        ),
    )


def _diagnostic(
    *,
    code: Code = Code.SEMANTIC_ERROR,
    phase: Phase = Phase.CHECKER,
    message: str = "boom",
    span: Span | None = None,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        phase=phase,
        severity=Severity.ERROR,
        message=message,
        span=span,
    )


# -- source ---------------------------------------------------------------


def test_display_path_is_relative_to_cwd(tmp_path: Path) -> None:
    script = tmp_path / "sub" / "a.lox"

    assert display_path(script, cwd=tmp_path) == "sub/a.lox"


def test_display_path_outside_cwd_is_basename_only(tmp_path: Path) -> None:
    outside = Path("/tmp") if not str(tmp_path).startswith("/tmp") else Path("/var")
    script = outside / "fora.lox"

    assert display_path(script, cwd=tmp_path) == "fora.lox"


def test_display_path_never_returns_absolute(tmp_path: Path) -> None:
    for path in (tmp_path / "a.lox", tmp_path / "x" / "b.lox", Path("/etc/c.lox")):
        assert not display_path(path, cwd=tmp_path).startswith("/")


def test_display_text_expands_tabs_from_start_width() -> None:
    text, width = display_text("\tx", start_width=0)
    assert text == "    x"
    assert width == 5

    text, width = display_text("\tx", start_width=2)
    assert text == "  x"
    assert width == 5


def test_display_width_counts_wide_and_combining() -> None:
    assert display_width("abc") == 3
    assert display_width("名前") == 4
    assert display_width("e\u0301") == 1


# -- human ----------------------------------------------------------------


def test_render_human_has_header_and_caret() -> None:
    sources = SourceMap()
    sources.add("x.lox", "print 1;\nprint 2;\n  val x = nome\n")
    diagnostic = _diagnostic(
        code=Code.TYPE_MISMATCH,
        message="Expected Float, found String.",
        span=_span(line=3, column=11, end_column=15),
    )

    text = render_human(diagnostic, sources)

    assert text == (
        "x.lox:3:11: error[E3001]: Expected Float, found String.\n"
        "  |\n"
        "3 |   val x = nome\n"
        "  |           ^^^^\n"
    )


def test_render_human_aligns_caret_with_tabs() -> None:
    sources = SourceMap()
    sources.add("tab.lox", "\tval x = nome\n")
    diagnostic = _diagnostic(
        span=_span(file="tab.lox", line=1, column=10, end_column=14)
    )

    text = render_human(diagnostic, sources)

    assert "    val x = nome\n" in text
    assert text.endswith("  |             ^^^^\n")


def test_render_human_counts_wide_characters() -> None:
    sources = SourceMap()
    sources.add("wide.lox", "print 名前;\n")
    diagnostic = _diagnostic(
        span=_span(file="wide.lox", line=1, column=7, end_column=9)
    )

    text = render_human(diagnostic, sources)

    assert text.endswith("  |       ^^^^\n")


def test_render_human_without_source_degrades_to_header() -> None:
    diagnostic = _diagnostic(span=_span(line=2, column=3))

    assert render_human(diagnostic, SourceMap()) == (
        "x.lox:2:3: error[E3000]: boom\n"
    )


def test_render_human_without_column_omits_location_suffix() -> None:
    diagnostic = _diagnostic(span=Span("x.lox", Position(4), Position(4)))

    assert render_human(diagnostic, SourceMap()) == "x.lox:4: error[E3000]: boom\n"


def test_render_human_colorizes_label_and_caret() -> None:
    sources = SourceMap()
    sources.add("x.lox", "nome\n")
    diagnostic = _diagnostic(span=_span(line=1, column=1, end_column=5))

    text = render_human(diagnostic, sources, color=True)

    assert "\x1b[1;31merror[E3000]\x1b[0m" in text
    assert "\x1b[31m^^^^\x1b[0m" in text
    assert "\x1b[34m1\x1b[0m" in text


def test_render_short_is_one_line() -> None:
    diagnostic = _diagnostic(span=_span(line=2, column=3))

    assert render_short(diagnostic) == "x.lox:2:3: error[E3000]: boom\n"


def test_render_short_without_span() -> None:
    assert render_short(_diagnostic()) == "error[E3000]: boom\n"


# -- runtime (formato do livro, congelado no commit 1) --------------------


def test_render_runtime_uses_header() -> None:
    diagnostic = _diagnostic(
        code=Code.DIVISION_BY_ZERO,
        phase=Phase.RUNTIME,
        message="Division by zero not allowed",
        span=_span(line=2, column=9),
    )

    assert render_runtime(diagnostic) == (
        "x.lox:2:9: error[R1002]: Division by zero not allowed\n"
    )


def test_render_batch_human_uses_runtime_header() -> None:
    runtime = _diagnostic(
        code=Code.DIVISION_BY_ZERO,
        phase=Phase.RUNTIME,
        message="Division by zero not allowed",
        span=_span(line=2, column=9),
    )
    batch = DiagnosticBatch((runtime,))

    text = render_batch(batch, SourceMap(), error_format="human", color=False)

    assert text == "x.lox:2:9: error[R1002]: Division by zero not allowed\n"


def test_render_batch_short_always_uses_header() -> None:
    runtime = _diagnostic(
        code=Code.DIVISION_BY_ZERO,
        phase=Phase.RUNTIME,
        message="Division by zero not allowed",
        span=_span(line=2, column=9),
    )
    batch = DiagnosticBatch((runtime,))

    text = render_batch(batch, SourceMap(), error_format="short", color=False)

    assert text == "x.lox:2:9: error[R1002]: Division by zero not allowed\n"


# -- json -----------------------------------------------------------------


def test_render_json_envelope_is_deterministic_and_complete() -> None:
    diagnostic = _diagnostic(
        code=Code.TYPE_MISMATCH,
        message="Expected Float, found String.",
        span=_span(line=3, column=11, end_column=15, offset=41, end_offset=45),
    )
    batch = DiagnosticBatch((diagnostic,), suppressed=2)

    text = render_json(batch, command="check", success=False, exit_code=65)

    assert text.endswith("\n")
    payload = json.loads(text)
    assert payload["schema_version"] == 1
    assert payload["command"] == "check"
    assert payload["success"] is False
    assert payload["exit_code"] == 65
    assert payload["summary"] == {"errors": 1, "warnings": 0, "suppressed": 2}

    entry = payload["diagnostics"][0]
    assert entry["code"] == "E3001"
    assert entry["phase"] == "checker"
    assert entry["severity"] == "error"
    assert entry["message"] == "Expected Float, found String."
    assert entry["span"]["file"] == "x.lox"
    assert entry["span"]["start"] == {"line": 3, "column": 11, "offset": 41}
    assert entry["span"]["end"] == {"line": 3, "column": 15, "offset": 45}
    assert entry["labels"] == []
    assert entry["notes"] == []
    assert entry["help"] is None


def test_render_json_is_byte_identical_across_calls() -> None:
    batch = DiagnosticBatch((_diagnostic(span=_span()),))

    first = render_json(batch, command="run", success=False, exit_code=70)
    second = render_json(batch, command="run", success=False, exit_code=70)

    assert first == second
