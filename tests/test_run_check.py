# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fases 2/3 do ADR-0142: `run` checa (gradual) antes de executar e bloqueia erro de tipo."""

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


def test_run_cli_blocks_a_type_error(tmp_path: Path) -> None:
    program = tmp_path / "prog.lx"
    program.write_text(BLOCKS, encoding="utf-8")

    blocked = run_cli("run", str(program))

    assert blocked.returncode == 65
    assert blocked.stdout == ""
    assert "error[E3001]" in blocked.stderr


def test_no_check_escape_was_removed(tmp_path: Path) -> None:
    program = tmp_path / "prog.lx"
    program.write_text(BLOCKS, encoding="utf-8")

    assert run_cli("run", "--no-check", str(program)).returncode == 2
    assert run_cli("--no-check", str(program)).returncode == 2
    assert run_cli("test", "--no-check", str(tmp_path)).returncode == 2


def test_repl_sees_previous_snippets(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()

    lox.run_repl("var x = 41\n")
    lox.run_repl("print(x + 1)\n")
    lox.run_repl("class P { fn m() -> Int { return 1 } }\n")
    lox.run_repl("val p = P()\n")
    lox.run_repl("val b: P = P()\n")
    lox.run_repl("print(p.m())\n")

    captured = capsys.readouterr()
    assert captured.out == "42\n1\n"
    assert "E3007" not in captured.err
    assert "E3001" not in captured.err
    assert "E3005" not in captured.err


def test_repl_json_lines_reports_the_advisory_warning() -> None:
    result = run_cli("repl", "--json-lines", stdin='var x: Int = "a"\n')

    assert result.returncode == 0
    assert '"code":"E3001"' in result.stderr
    assert '"warnings":1' in result.stderr


def test_run_blocks_a_spread_into_a_non_variadic_call(tmp_path: Path) -> None:
    program = tmp_path / "spread.lx"
    program.write_text(
        "fn f(a: Int, b: Int) -> Int { return a + b }\nprint(f(...[1, 2]))\n",
        encoding="utf-8",
    )

    blocked = run_cli("run", str(program))

    assert blocked.returncode == 65
    assert "E3002" in blocked.stderr
    assert blocked.stdout == ""


def test_repl_ignores_werror_and_still_executes() -> None:
    result = run_cli("repl", "-Werror", stdin='var x: Int = "a"\nprint(x)\n')

    assert result.returncode == 0
    assert result.stdout == "a\n"
    assert "warning[E3001]" in result.stderr
