# SPDX-License-Identifier: MIT OR Apache-2.0
"""Formato e classificação dos erros do backend (E4001/E4002)."""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia_core.backend import driver, llvm_ir
from loxia_core.backend.lower import BackendError
from loxia_core.backend.lower_model import _unsupported
from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.render import render_batch
from loxia_core.diagnostics.source import SourceMap


def test_unsupported_tem_codigo_e4001() -> None:
    error = _unsupported("Feature X", 4)

    assert error.code is Code.BACKEND_UNSUPPORTED
    assert error.line == 4
    assert error.message == "Feature X is not supported by the backend yet."


def test_interno_ganha_contexto_e_codigo_e4002() -> None:
    error = BackendError("Undefined variable 'x'.", 7)

    assert error.code is Code.BACKEND_INTERNAL
    assert error.message.startswith("internal lowering error: ")
    assert "Undefined variable 'x'." in error.message


def test_render_backend_short_sem_caret() -> None:
    reporter = ErrorReporter()
    reporter.file = "caso.lx"
    reporter.backend_error(7, "Feature X is not supported.", code=Code.BACKEND_UNSUPPORTED)

    text = render_batch(reporter.batch(), SourceMap(), error_format="human", color=False)

    assert text == "caso.lx:7: error[E4001]: Feature X is not supported.\n"
    assert "^" not in text


def test_compiler_error_sanitiza_caminhos_temporarios(tmp_path: Path) -> None:
    build_dir = tmp_path / "lox-build-abc"
    build_dir.mkdir()
    error = BackendError(f"cc failed: {build_dir}/program.o: erro")

    sanitized = driver._sanitize_compiler_error(error, build_dir)

    assert str(build_dir) not in sanitized.message
    assert "<build>" in sanitized.message


def test_driver_embrulha_falha_inesperada_de_emissao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Module:
        def __str__(self) -> str:
            return "define i32 @f() {\nentry:\n  ret i32 0\n}\n"

    monkeypatch.setattr(driver, "lower_program", lambda *args, **kwargs: _Module())
    monkeypatch.setattr(driver, "_verify", lambda module: None)
    monkeypatch.setattr(
        llvm_ir,
        "emit_object",
        lambda module: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(BackendError) as raised:
        driver.build(
            [],
            emit="obj",
            output=None,
            stem="caso",
            types={},
            depths={},
        )

    assert raised.value.code is Code.BACKEND_INTERNAL
    assert "internal error" in raised.value.message
    assert "RuntimeError: boom" in raised.value.message


def test_link_sanitiza_erro_do_compilador(tmp_path: Path) -> None:
    build_dir = tmp_path / "lox-build-xyz"
    build_dir.mkdir()
    error = BackendError(f"cc failed: {build_dir}/program.o: erro")

    sanitized = driver._sanitize_compiler_error(error, build_dir)

    assert sanitized.code is Code.BACKEND_INTERNAL
    assert str(build_dir) not in sanitized.message
