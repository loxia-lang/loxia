# SPDX-License-Identifier: MIT OR Apache-2.0
"""Migrated lowerers keep block creation inside the control IR (ADR-0153)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "loxia_core/backend/lower_exceptions.py",
    "loxia_core/backend/lower_enums.py",
    "loxia_core/backend/lower_class_codegen.py",
)


def test_poison_uses_the_control_ir() -> None:
    text = (ROOT / "loxia_core/backend/lower.py").read_text(encoding="utf-8")
    start = text.index("    def _poison(")
    end = text.index("    def _panic_function", start)

    assert "llvm_ir.append_block(" not in text[start:end]
    assert "self._control.new_block(" in text[start:end]


def test_migrated_lowerers_do_not_create_blocks_directly() -> None:
    for name in TARGETS:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "llvm_ir.append_block(" not in text, f"{name}: append_block direto"
        assert "llvm_ir.block_of(" not in text, f"{name}: block_of direto"
        assert "self._control.new_block(" in text, f"{name}: não usa o ControlIR"
