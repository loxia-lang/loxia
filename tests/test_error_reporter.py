from __future__ import annotations

import pytest

from src.error_reporter import ErrorReporter
from src.errors import LoxRuntimeError
from src.token_type import TokenType
from src.tokens import Token


def test_reset_clears_both_error_flags() -> None:
    reporter = ErrorReporter()
    reporter.had_error = True
    reporter.had_runtime_error = True
    reporter.silent = True

    reporter.reset()

    assert reporter.had_error is False
    assert reporter.had_runtime_error is False
    assert reporter.silent is False


def test_instances_do_not_share_state() -> None:
    first = ErrorReporter()
    second = ErrorReporter()

    first.silent = True
    first.report(1, "", "boom")

    assert first.had_error is True
    assert second.had_error is False


def test_has_error_aggregates_both_flags() -> None:
    reporter = ErrorReporter()
    assert reporter.has_error is False

    reporter.had_runtime_error = True

    assert reporter.has_error is True


def test_runtime_error_sets_flag_and_prints(
    capsys: pytest.CaptureFixture[str],
) -> None:
    reporter = ErrorReporter()
    token = Token(TokenType.IDENTIFIER, "x", None, 3)

    reporter.runtime_error(LoxRuntimeError(token, "boom"))

    captured = capsys.readouterr()
    assert reporter.had_runtime_error is True
    assert "boom" in captured.err
    assert "[line 3]" in captured.err


def test_silent_suppresses_output_but_still_records_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    reporter = ErrorReporter()
    reporter.silent = True

    reporter.report(1, " at 'x'", "boom")

    assert reporter.had_error is True
    assert capsys.readouterr().err == ""
