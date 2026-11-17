# SPDX-License-Identifier: MIT OR Apache-2.0
"""Gate `mod.verify`: o módulo gerado é verificado antes de qualquer emissão."""

from __future__ import annotations

import pytest

pytest.importorskip("llvmlite")

from loxia_core.backend import driver, llvm_ir
from loxia_core.backend.lower import BackendError

_VALID_IR = "define i32 @f() {\nentry:\n  ret i32 0\n}\n"
_INVALID_IR = "define i32 @f() {\nentry:\n  ret i64 0\n}\n"


def test_verify_text_aceita_ir_valido() -> None:
    llvm_ir.verify_text(_VALID_IR)


def test_verify_text_rejeita_ir_invalido() -> None:
    with pytest.raises(llvm_ir.LLVMVerificationError):
        llvm_ir.verify_text(_INVALID_IR)


class _BrokenModule:
    """Módulo falso: o driver só precisa de `str(module)` para verificar."""

    def __str__(self) -> str:
        return _INVALID_IR


def test_driver_converte_ir_invalido_em_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(driver, "lower_program", lambda *args, **kwargs: _BrokenModule())

    with pytest.raises(BackendError, match="invalid LLVM IR"):
        driver.build(
            [],
            emit="ll",
            output=None,
            stem="broken",
            types={},
            depths={},
        )
