# SPDX-License-Identifier: MIT OR Apache-2.0
"""Despacho do `run` (AOT x tree-walk) sem depender do backend compilado.

O caminho real (compilar e executar) vive em `tests/test_run_native.py`; aqui o
objetivo é o encanamento do CLI: escolha de motor, dica de recusa, execução do
binário e o fluxo de cache hit/miss com um `compile_prepared` de mentira. Roda no
loop rápido (`make test-fast`/ratchet de cobertura), que exclui o backend.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn

import pytest

from loxia import cli_commands, native_cache
from loxia.cli_commands import (
    _execute_native,
    _native_requested,
    _run_failure_hint,
    _run_native,
)
from loxia.engine import Loxia
from loxia_core.diagnostics.codes import Code

ROOT = Path(__file__).resolve().parents[1]


def _args(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "script": "prog.lx",
        "script_args": [],
        "interpret": False,
        "stdin": False,
        "sandbox": False,
        "json": False,
        "json_lines": False,
        "error_format": "human",
        "color": "auto",
        "timeout": None,
        "no_cache": False,
        "max_heap": None,
        "frozen": False,
        "offline": False,
        "cache_dir": None,
        "module_path": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _lox(tmp_path: Path, source: str = "print(1)\n") -> tuple[Loxia, Path]:
    entry = tmp_path / "prog.lx"
    entry.write_text(source, encoding="utf-8")
    lox = Loxia()
    lox.use_file(str(entry), module_root=tmp_path)
    return lox, entry


# -- escolha de motor ------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, True),
        ({"interpret": True}, False),
        ({"stdin": True}, False),
        ({"sandbox": True}, False),
        ({"json": True}, False),
        ({"json_lines": True}, False),
        ({"error_format": "short"}, False),
        ({"error_format": "json"}, False),
        ({"color": "always"}, False),
        ({"color": "never"}, True),
        ({"script": None}, False),
    ],
)
def test_native_requested(overrides: dict[str, object], expected: bool) -> None:
    assert _native_requested(_args(**overrides)) is expected


# -- dicas -----------------------------------------------------------------


def _reporter_with(code: Code) -> Loxia:
    lox = Loxia()
    lox.reporter.backend_error(1, "erro de teste", code=code)
    return lox


def test_hint_de_anotacao(capsys: pytest.CaptureFixture[str]) -> None:
    _run_failure_hint(_reporter_with(Code.MISSING_ANNOTATION))

    assert "--interpret" in capsys.readouterr().err


def test_hint_de_toolchain(capsys: pytest.CaptureFixture[str]) -> None:
    _run_failure_hint(_reporter_with(Code.NATIVE_TOOLCHAIN))

    assert "native backend is unavailable" in capsys.readouterr().err


def test_sem_dica_para_outro_erro(capsys: pytest.CaptureFixture[str]) -> None:
    _run_failure_hint(_reporter_with(Code.BACKEND_UNSUPPORTED))

    assert capsys.readouterr().err == ""


def test_sem_dica_sem_erro(capsys: pytest.CaptureFixture[str]) -> None:
    _run_failure_hint(Loxia())

    assert capsys.readouterr().err == ""


# -- execução do binário ---------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="usa /bin/true e /bin/false")
def test_executa_e_propaga_o_exit_code(tmp_path: Path) -> None:
    lox, _entry = _lox(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        _execute_native(lox, _args(), Path("/bin/true"))
    assert excinfo.value.code == 0

    with pytest.raises(SystemExit) as excinfo:
        _execute_native(lox, _args(), Path("/bin/false"))
    assert excinfo.value.code == 1


@pytest.mark.skipif(sys.platform == "win32", reason="usa /bin/sleep")
def test_timeout_mata_o_processo_com_124(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lox, _entry = _lox(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        _execute_native(lox, _args(timeout=50, script_args=["5"]), Path("/bin/sleep"))

    assert excinfo.value.code == 124
    assert "Execution timed out after 50 ms." in capsys.readouterr().err


# -- fluxo do cache (build de mentira) ------------------------------------


def test_run_native_reusa_o_cache_e_no_cache_rebuilda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOX_BUILD_CACHE", str(tmp_path / "cache"))
    lox, _entry = _lox(tmp_path)
    builds: list[Path] = []
    executed: list[Path] = []

    def fake_compile(
        statements: object,
        *,
        emit: str,
        output: Path | None,
        stem: str,
        max_heap: int | None = None,
        command: str = "build",
    ) -> bool:
        assert output is not None
        output.write_bytes(b"binario")
        builds.append(output)
        return True

    def fake_execute(lox: Loxia, args: argparse.Namespace, binary: Path) -> NoReturn:
        executed.append(binary)
        raise SystemExit(0)

    monkeypatch.setattr(lox, "compile_prepared", fake_compile)
    monkeypatch.setattr(cli_commands, "_execute_native", fake_execute)

    with pytest.raises(SystemExit):
        _run_native(lox, _args(), source="print(1)\n")
    assert len(builds) == 1
    assert executed[0].exists()

    with pytest.raises(SystemExit):
        _run_native(lox, _args(), source="print(1)\n")
    assert len(builds) == 1, "o segundo run tem que ser cache hit"
    assert executed[1] == executed[0]

    cached = len(list((tmp_path / "cache" / "run").rglob("*")))
    with pytest.raises(SystemExit):
        _run_native(lox, _args(no_cache=True), source="print(1)\n")
    assert len(builds) == 2, "--no-cache ignora o cache"
    assert executed[2] != executed[0], "--no-cache compila num temporário"
    assert len(list((tmp_path / "cache" / "run").rglob("*"))) == cached


def test_run_native_recusa_sem_anotacao_com_dica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOX_BUILD_CACHE", str(tmp_path / "cache"))
    lox, _entry = _lox(tmp_path, "fn soma(a, b) {\n  return a + b\n}\n")

    with pytest.raises(SystemExit) as excinfo:
        _run_native(lox, _args(), source="fn soma(a, b) {\n  return a + b\n}\n")

    assert excinfo.value.code == 65
    assert "--interpret" in capsys.readouterr().err


def test_cache_da_run_fica_na_raiz_configurada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOX_BUILD_CACHE", str(tmp_path / "cache"))
    lox, _entry = _lox(tmp_path)

    def fake_compile(
        statements: object,
        *,
        emit: str,
        output: Path | None,
        stem: str,
        max_heap: int | None = None,
        command: str = "build",
    ) -> bool:
        assert output is not None
        output.write_bytes(b"binario")
        return True

    monkeypatch.setattr(lox, "compile_prepared", fake_compile)

    class _Stop(SystemExit):
        pass

    monkeypatch.setattr(
        cli_commands,
        "_execute_native",
        lambda lox, args, binary: (_ for _ in ()).throw(_Stop(0)),
    )

    with pytest.raises(SystemExit):
        _run_native(lox, _args(), source="print(1)\n")

    binaries = [item for item in (tmp_path / "cache" / "run").rglob("*") if item.is_file()]
    assert binaries
    assert os.access(binaries[0], os.X_OK)
    assert native_cache.cache_size(tmp_path / "cache") > 0


def test_fonte_com_erro_de_sintaxe_sai_65(tmp_path: Path) -> None:
    lox, _entry = _lox(tmp_path, "print(1 + )\n")

    with pytest.raises(SystemExit) as excinfo:
        _run_native(lox, _args(), source="print(1 + )\n")

    assert excinfo.value.code == 65
