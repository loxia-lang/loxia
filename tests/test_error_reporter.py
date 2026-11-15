from __future__ import annotations

import pytest

from src.diagnostics.codes import Code
from src.diagnostics.error_reporter import ErrorReporter
from src.diagnostics.errors import LoxRuntimeError
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token


def _token(lexeme: str = "x", line: int = 1, column: int = 1) -> Token:
    return Token(TokenType.IDENTIFIER, lexeme, None, line, column, 0)


def test_reset_clears_flags_and_bag() -> None:
    reporter = ErrorReporter()
    reporter.error(_token(), "boom", code=Code.SEMANTIC_ERROR)
    reporter.had_runtime_error = True

    reporter.reset()

    assert reporter.had_error is False
    assert reporter.had_runtime_error is False
    assert reporter.batch().diagnostics == ()


def test_instances_do_not_share_state() -> None:
    first = ErrorReporter()
    second = ErrorReporter()

    first.error(_token(), "boom", code=Code.SEMANTIC_ERROR)

    assert first.had_error is True
    assert second.had_error is False
    assert second.batch().diagnostics == ()


def test_has_error_aggregates_both_flags() -> None:
    reporter = ErrorReporter()
    assert reporter.has_error is False

    reporter.had_runtime_error = True

    assert reporter.has_error is True


def test_runtime_error_is_collected_with_span_and_default_code() -> None:
    reporter = ErrorReporter()
    reporter.file = "exemplo.lx"
    token = Token(TokenType.IDENTIFIER, "x", None, 3, 7, 20)

    reporter.runtime_error(LoxRuntimeError(token, "boom"))

    batch = reporter.batch()
    assert reporter.had_runtime_error is True
    assert len(batch.diagnostics) == 1
    diagnostic = batch.diagnostics[0]
    assert diagnostic.code is Code.RUNTIME_ERROR
    assert diagnostic.message == "boom"
    assert diagnostic.span is not None
    assert diagnostic.span.file == "exemplo.lx"
    assert diagnostic.span.start.line == 3
    assert diagnostic.span.start.column == 7
    assert diagnostic.span.start.offset == 20
    # Fim half-open: lexema de 1 code point / 1 byte.
    assert diagnostic.span.end.column == 8
    assert diagnostic.span.end.offset == 21


def test_error_at_builds_lexer_span() -> None:
    from src.diagnostics.diagnostic import Position

    reporter = ErrorReporter()
    reporter.file = "a.lx"

    reporter.error_at(
        Position(1, 3, 2),
        Position(1, 4, 3),
        "Unexpected character: @",
        code=Code.UNEXPECTED_CHARACTER,
    )

    diagnostic = reporter.batch().diagnostics[0]
    assert diagnostic.phase.value == "lexer"
    assert diagnostic.span is not None
    assert diagnostic.span.start.column == 3
    assert diagnostic.span.end.column == 4


def test_batch_sorts_by_offset_and_dedups() -> None:
    reporter = ErrorReporter()
    later = Token(TokenType.IDENTIFIER, "b", None, 1, 10, 9)
    earlier = Token(TokenType.IDENTIFIER, "a", None, 1, 2, 1)

    reporter.error(later, "segundo", code=Code.SEMANTIC_ERROR)
    reporter.error(earlier, "primeiro", code=Code.SEMANTIC_ERROR)
    reporter.error(earlier, "primeiro", code=Code.SEMANTIC_ERROR)

    batch = reporter.batch()
    assert [item.message for item in batch.diagnostics] == ["primeiro", "segundo"]
    assert batch.suppressed == 0


def test_batch_respects_max_errors_and_counts_suppressed() -> None:
    reporter = ErrorReporter(max_errors=2)
    for index in range(5):
        token = Token(TokenType.IDENTIFIER, "x", None, 1, index + 1, index)
        reporter.error(token, f"erro {index}", code=Code.SEMANTIC_ERROR)

    batch = reporter.batch()
    assert len(batch.diagnostics) == 2
    assert batch.suppressed == 3


def test_max_errors_zero_means_unlimited() -> None:
    reporter = ErrorReporter(max_errors=0)
    for index in range(5):
        token = Token(TokenType.IDENTIFIER, "x", None, 1, index + 1, index)
        reporter.error(token, f"erro {index}", code=Code.SEMANTIC_ERROR)

    assert len(reporter.batch().diagnostics) == 5


def test_lowerable_diagnostic_is_deferred_in_build_mode() -> None:
    reporter = ErrorReporter()
    reporter.defer_lowerable = True
    token = _token()

    reporter.error(
        token, "Operands must be numbers.", code=Code.INVALID_OPERANDS, lowerable=True
    )

    assert reporter.had_error is True
    assert reporter.had_fatal_error is False
    assert reporter.batch().diagnostics == ()


def test_lowerable_diagnostic_is_reported_outside_build_mode() -> None:
    reporter = ErrorReporter()

    reporter.error(
        _token(), "Operands must be numbers.", code=Code.INVALID_OPERANDS, lowerable=True
    )

    assert reporter.had_fatal_error is False
    assert len(reporter.batch().diagnostics) == 1


def test_mark_and_restore_discard_speculative_diagnostics() -> None:
    reporter = ErrorReporter()
    reporter.error(_token(), "antes", code=Code.SEMANTIC_ERROR)
    state = reporter.mark()

    reporter.error(_token(line=2), "especulativo", code=Code.SEMANTIC_ERROR)
    reporter.restore(state)

    batch = reporter.batch()
    assert [item.message for item in batch.diagnostics] == ["antes"]
    assert reporter.had_error is True


@pytest.mark.parametrize("line", [1, 42])
def test_backend_error_uses_current_file(line: int) -> None:
    reporter = ErrorReporter()
    reporter.file = "prog.lx"

    reporter.backend_error(line, "not supported")

    diagnostic = reporter.batch().diagnostics[0]
    assert diagnostic.phase.value == "backend"
    assert diagnostic.span is not None
    assert diagnostic.span.file == "prog.lx"
    assert diagnostic.span.start.line == line
