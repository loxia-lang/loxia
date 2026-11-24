# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fase 2 do ADR-0142: `run` checa (gradual) antes de executar e bloqueia erro de tipo."""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia.engine import Loxia
from tests.inprocess import run_cli

BLOCKS = 'var x: Int = "a"\nprint(x)\n'
DEFERS = "print(1 + true)\n"
UNANNOTATED = "fn f(x) { return x }\nprint(f(1))\n"


def test_run_blocks_a_non_lowerable_type_error(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()

    lox.run(BLOCKS)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error[E3001]" in captured.err
    assert lox.reporter.had_error is True


def test_run_defers_a_lowerable_error_to_runtime(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()

    lox.run(DEFERS)

    captured = capsys.readouterr()
    assert "error[R1006]" in captured.err
    assert lox.reporter.had_runtime_error is True
    assert lox.reporter.had_error is False


def test_run_is_silent_about_missing_annotations(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()

    lox.run(UNANNOTATED)

    captured = capsys.readouterr()
    assert captured.out == "1\n"
    assert captured.err == ""
    assert lox.reporter.had_error is False


def test_run_no_check_executes_the_program(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia(check_on_run=False)

    lox.run(BLOCKS)

    assert capsys.readouterr().out == "a\n"


def test_repl_only_warns_and_keeps_the_environment(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()

    lox.run_repl('var x: Int = "a"\n')
    lox.run_repl("print(x)\n")

    captured = capsys.readouterr()
    assert "warning[E3001]" in captured.err
    assert captured.out == "a\n"
    # O check é por snippet; nomes de linhas anteriores não viram falso positivo.
    assert "E3003" not in captured.err
    assert lox.reporter.had_error is False


def test_run_cli_checks_first_and_no_check_bypasses(tmp_path: Path) -> None:
    program = tmp_path / "prog.lx"
    program.write_text(BLOCKS, encoding="utf-8")

    blocked = run_cli("run", str(program))
    assert blocked.returncode == 65
    assert blocked.stdout == ""
    assert "error[E3001]" in blocked.stderr

    allowed = run_cli("run", "--no-check", str(program))
    assert allowed.returncode == 0
    assert allowed.stdout == "a\n"


def test_legacy_no_check_flag_and_conflict(tmp_path: Path) -> None:
    program = tmp_path / "prog.lx"
    program.write_text(BLOCKS, encoding="utf-8")

    allowed = run_cli("--no-check", str(program))
    assert allowed.returncode == 0
    assert allowed.stdout == "a\n"

    conflict = run_cli("--no-check", "--check", str(program))
    assert conflict.returncode == 2


def test_no_check_still_reports_a_runtime_error(tmp_path: Path) -> None:
    program = tmp_path / "prog.lx"
    program.write_text(DEFERS, encoding="utf-8")

    result = run_cli("run", "--no-check", str(program))

    assert result.returncode == 70
    assert "error[R1006]" in result.stderr
