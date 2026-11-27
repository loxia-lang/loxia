# SPDX-License-Identifier: MIT OR Apache-2.0
"""Camadas de motor (ADR-0128): passe estatico e recusa do interpretador."""

from __future__ import annotations

from pathlib import Path

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


def test_run_recusa_regex_sem_o_toolchain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import loxia.engine as engine_module

    monkeypatch.setattr(engine_module, "cargo_binary", lambda: None)

    lox = Loxia()
    lox.run('print(1)\nregex_engine.compile("a", 0, 0)\n')

    captured = capsys.readouterr()
    assert lox.reporter.had_error
    assert captured.out == ""
    assert "E3022" in captured.err
    assert "Rust toolchain" in captured.err


def test_check_nao_exige_o_toolchain_do_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    import loxia.engine as engine_module

    monkeypatch.setattr(engine_module, "cargo_binary", lambda: None)

    lox = Loxia()
    exit_code = lox.check('val r = regex_engine.compile("a", 0, 0)\nprint(r[1])\n')

    assert exit_code == 0
    assert not lox.reporter.had_error


def test_run_recusa_group_names_sem_o_toolchain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import loxia.engine as engine_module

    monkeypatch.setattr(engine_module, "cargo_binary", lambda: None)

    lox = Loxia()
    lox.run("print(regex_engine.groupNames(1))\n")

    captured = capsys.readouterr()
    assert lox.reporter.had_error
    assert "E3022" in captured.err


def test_build_recusa_regex_sem_o_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import loxia.engine as engine_module

    monkeypatch.setattr(engine_module, "cargo_binary", lambda: None)

    lox = Loxia()
    built = lox.build(
        'regex_engine.compile("a", 0, 0)\n',
        emit="exe",
        output=tmp_path / "app",
        stem="app",
    )

    assert built is False
    assert "E3022" in capsys.readouterr().err
    assert not (tmp_path / "app").exists()


def test_build_nao_confunde_erro_rebaixavel_com_regex_sem_toolchain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sem cargo, um erro que vira panic (`1 + true`) não é falta de toolchain.

    Regressão: o gate de regex consultava `reporter.had_error`, que já estava
    verdadeiro pelo erro rebaixável deferido; o build saía 65 sem imprimir nada.
    """
    import loxia.engine as engine_module

    pytest.importorskip("llvmlite")
    import loxia_core.backend.driver as driver_module

    monkeypatch.setattr(engine_module, "cargo_binary", lambda: None)
    calls: list[str] = []
    monkeypatch.setattr(driver_module, "build", lambda *args, **kwargs: calls.append("build"))

    lox = Loxia()
    built = lox.build("print(1 + true)\n", emit="ll", output=None, stem="caso")

    assert built is True
    assert calls == ["build"]
    assert not lox.reporter.had_fatal_error
    assert lox.reporter.batch().diagnostics == ()
    assert capsys.readouterr().err == ""
