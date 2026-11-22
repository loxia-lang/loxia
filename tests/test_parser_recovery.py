# SPDX-License-Identifier: MIT OR Apache-2.0
"""Recuperação do parser: nós de erro inertes para LSP e `--allow-errors`."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loxia.engine import Loxia
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.expr import ErrorExpr
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import ErrorStmt, Expression, Function, Var

ROOT = Path(__file__).resolve().parents[1]


def _parse(source: str) -> tuple[list[object], ErrorReporter]:
    reporter = ErrorReporter()
    reporter.file = "recovery.lx"
    tokens = Scanner(source, reporter).scan_tokens()
    statements = Parser(tokens, reporter=reporter).parse()
    assert statements is not None
    return list(statements), reporter


def test_failed_declaration_becomes_error_stmt() -> None:
    statements, reporter = _parse("fn f(x: \n")

    assert reporter.had_error is True
    assert len(statements) == 1
    error = statements[0]
    assert isinstance(error, ErrorStmt)
    assert error.message == "Expect type name."


def test_error_inside_function_keeps_the_function_and_its_body() -> None:
    statements, reporter = _parse("fn f() { val x = ; }\nprint(1)\n")

    assert reporter.had_error is True
    assert isinstance(statements[0], Function)
    assert isinstance(statements[0].body[0], ErrorStmt)
    assert isinstance(statements[1], Expression)


def test_failed_expression_does_not_swallow_the_next_statement() -> None:
    statements, reporter = _parse("print(1 + )\nprint(2)\n")

    assert reporter.had_error is True
    assert len(statements) == 2
    first = statements[0]
    assert isinstance(first, Expression)
    assert isinstance(first.expression, ErrorExpr)
    second = statements[1]
    assert isinstance(second, Expression)


def test_engine_returns_recovered_tree_only_with_allow_errors() -> None:
    source = "print(1 + )\nprint(2)\n"
    default = Loxia(max_errors=0)
    default.use_file("recovery.lx")
    assert default.parse_file(source) is None

    lox = Loxia(max_errors=0)
    lox.use_file("recovery.lx")
    parsed = lox.parse_file(source, allow_errors=True)

    assert parsed is not None
    tokens, statements = parsed
    assert tokens
    assert len(statements) == 2


def test_cli_allow_errors_emits_json_and_keeps_exit_65() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "main.py"),
            "ast",
            "--file-only",
            "--format=json",
            "--allow-errors",
            "--stdin",
        ],
        cwd=ROOT,
        input="print(1 + )\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 65
    payload = json.loads(result.stdout)
    assert payload["statements"][0]["expression"]["kind"] == "error_expr"
    assert "error_expr" in result.stdout or "error_expr" in result.stderr


def test_cli_without_allow_errors_does_not_emit_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "main.py"),
            "ast",
            "--file-only",
            "--format=json",
            "--stdin",
        ],
        cwd=ROOT,
        input="print(1 + )\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 65
    assert result.stdout == ""


def test_unclosed_list_does_not_swallow_the_next_statement() -> None:
    statements, reporter = _parse("val x = [1, 2\nprint(x)\n")

    assert reporter.had_error is True
    assert len(statements) == 2
    assert isinstance(statements[0], ErrorStmt)
    assert isinstance(statements[1], Expression)


def test_unclosed_paren_does_not_swallow_the_next_declaration() -> None:
    statements, reporter = _parse("val b = (\nval c = 3\n")

    assert reporter.had_error is True
    assert len(statements) == 2
    assert isinstance(statements[0], ErrorStmt)
    assert isinstance(statements[1], Var)


def test_error_stmt_span_starts_at_the_declaration() -> None:
    statements, reporter = _parse("fn f(x: \n")

    assert reporter.had_error is True
    error = statements[0]
    assert isinstance(error, ErrorStmt)
    assert error.start.offset == 0
    assert error.end is not None
    assert (error.end.offset or 0) > 0


def test_recovery_does_not_loop_on_a_non_starter_token() -> None:
    statements, reporter = _parse("val x = (\n)\nval y = 1\n")

    assert reporter.had_error is True
    assert len(statements) >= 2
    assert any(isinstance(statement, ErrorStmt) for statement in statements)
