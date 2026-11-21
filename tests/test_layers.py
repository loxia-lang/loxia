# SPDX-License-Identifier: MIT OR Apache-2.0
"""Camadas de motor (ADR-0128): passe estatico e recusa do interpretador."""

from __future__ import annotations

import pytest

from loxia.engine import Loxia
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.execution.primitives import API_LAYERS
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Stmt
from loxia_core.semantics.layers import native_only_uses


def _parse(source: str) -> list[Stmt]:
    reporter = ErrorReporter()
    tokens = Scanner(source, reporter).scan_tokens()
    statements = Parser(tokens, reporter=reporter).parse()
    assert statements is not None
    assert not reporter.had_error
    return statements


def test_detecta_chamada_e_uso_como_valor() -> None:
    statements = _parse("fake.nativeFn()\nval f = fake.nativeFn\n")

    uses = native_only_uses(statements, {}, index={"fake.nativeFn": "native-only"})

    assert [use.name for use in uses] == ["fake.nativeFn", "fake.nativeFn"]
    assert uses[0].token.lexeme == "nativeFn"


def test_nao_marca_core_nem_ambient() -> None:
    statements = _parse('math.sqrt(4.0)\nfs.open("x", "r")\n')

    uses = native_only_uses(
        statements,
        {},
        index={"math.sqrt": "core", "fs.open": "ambient"},
    )

    assert uses == []


def test_run_recusa_native_only_antes_de_executar(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(API_LAYERS, "fake.nativeFn", "native-only")

    lox = Loxia()
    lox.run("print(1)\nfake.nativeFn()\n")

    captured = capsys.readouterr()
    assert lox.reporter.had_error
    assert captured.out == ""  # nada executou, nem o print anterior
    assert "E3021" in captured.err
    assert "not supported by the interpreter" in captured.err


def test_sombreamento_local_nao_e_recusado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(API_LAYERS, "fake.nativeFn", "native-only")

    lox = Loxia()
    lox.run(
        "class Fake { fn nativeFn() -> Int { return 7 } }\n"
        "fn run() { val fake = Fake(); print(fake.nativeFn()) }\n"
        "run()\n"
    )

    assert not lox.reporter.had_error
    assert capsys.readouterr().out == "7\n"


def test_run_aceita_programa_sem_capacidade_nativa(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()
    lox.run("print(1 + 2)\n")

    assert not lox.reporter.had_error
    assert capsys.readouterr().out == "3\n"
