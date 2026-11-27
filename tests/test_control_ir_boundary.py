# SPDX-License-Identifier: MIT OR Apache-2.0
"""All backend block creation goes through the control IR (ADR-0153)."""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "loxia_core/backend"
FORBIDDEN = frozenset({"append_block", "append_basic_block", "block_of", "IRBuilder"})
# `llvm_ir` is the low-level boundary; `control_ir` is the only allowed user of it.
SKIP = frozenset({"llvm_ir.py"})
CREATORS = (
    "lower.py",
    "lower_bytes.py",
    "lower_calls.py",
    "lower_class_codegen.py",
    "lower_containers.py",
    "lower_enums.py",
    "lower_exceptions.py",
    "lower_functions.py",
    "lower_instances.py",
    "lower_math.py",
    "lower_optionals.py",
    "lower_range.py",
    "lower_strings.py",
    "lower_variables.py",
)


def _names(text: str) -> set[str]:
    """Identifiers in ``text``, ignoring comments/strings and their contents."""
    return {
        token.string
        for token in tokenize.generate_tokens(io.StringIO(text).readline)
        if token.type == tokenize.NAME
    }


def _backend_files() -> list[Path]:
    return [
        path
        for path in sorted(BACKEND.rglob("*.py"))
        if "control_ir" not in path.parts and path.name not in SKIP
    ]


def test_scanner_catches_bypass_spellings() -> None:
    assert "append_basic_block" in _names("self._function_ir.append_basic_block('x')")
    assert "append_block" in _names("from loxia_core.backend.llvm_ir import append_block")
    assert "block_of" in _names("llvm_ir.block_of(fn, 'entry')")
    assert "IRBuilder" in _names("ir.IRBuilder(block)")


def test_no_backend_lowerer_creates_blocks_directly() -> None:
    for path in _backend_files():
        forbidden = _names(path.read_text(encoding="utf-8")) & FORBIDDEN
        assert not forbidden, f"{path.relative_to(ROOT)}: block creation direta {sorted(forbidden)}"


def test_every_block_creating_lowerer_uses_the_control_ir() -> None:
    for name in CREATORS:
        text = (BACKEND / name).read_text(encoding="utf-8")
        assert "self._control.new_block(" in text, f"{name}: não usa ControlIR.new_block"


def test_poison_uses_the_control_ir() -> None:
    text = (BACKEND / "lower.py").read_text(encoding="utf-8")
    start = text.index("    def _poison(")
    end = text.index("    def _panic_function", start)

    assert "self._control.new_block(" in text[start:end]
