# SPDX-License-Identifier: MIT OR Apache-2.0
"""All backend block creation goes through the control IR (ADR-0153)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "loxia_core/backend"


def test_poison_uses_the_control_ir() -> None:
    text = (ROOT / "loxia_core/backend/lower.py").read_text(encoding="utf-8")
    start = text.index("    def _poison(")
    end = text.index("    def _panic_function", start)

    assert "llvm_ir.append_block(" not in text[start:end]
    assert "self._control.new_block(" in text[start:end]


def test_every_backend_lowerer_uses_the_control_ir() -> None:
    for path in sorted(BACKEND.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "llvm_ir.append_block(" not in text, f"{path.name}: append_block direto"
        assert "llvm_ir.block_of(" not in text, f"{path.name}: block_of direto"
