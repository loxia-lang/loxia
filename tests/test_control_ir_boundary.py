# SPDX-License-Identifier: MIT OR Apache-2.0
"""All backend block creation goes through the control IR (ADR-0153).

The scan is intentionally static: it catches identifiers and static aliases. Dynamic access
(``getattr(llvm_ir, "append_block")``) is closed at runtime by ``ControlIR.verify_all``,
which rejects any LLVM block missing from the model. ``IRBuilder`` is forbidden as an
identifier, including annotations; use ``ControlIRBuilder``.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "loxia_core/backend"
FORBIDDEN = frozenset({"append_block", "append_basic_block", "block_of", "IRBuilder"})
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
    files: list[Path] = []
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND)
        if relative.parts[:1] == ("control_ir",) or relative == Path("llvm_ir.py"):
            continue
        files.append(path)
    return files


def test_scanner_catches_static_bypass_spellings() -> None:
    assert "append_basic_block" in _names("self._function_ir.append_basic_block('x')")
    assert "append_block" in _names("from loxia_core.backend.llvm_ir import append_block")
    assert "block_of" in _names("llvm_ir.block_of(fn, 'entry')")
    assert "IRBuilder" in _names("ir.IRBuilder(block)")


def test_scanner_ignores_comments_and_strings() -> None:
    assert not (_names('# append_block\nx = "IRBuilder"') & FORBIDDEN)


def test_backend_scan_is_not_empty() -> None:
    assert _backend_files()


def test_backend_scan_uses_paths_relative_to_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import tests.test_control_ir_boundary as boundary

    backend = tmp_path / "control_ir" / "loxia_core" / "backend"
    (backend / "control_ir").mkdir(parents=True)
    (backend / "pkg").mkdir()
    (backend / "lower.py").write_text("x = 1\n", encoding="utf-8")
    (backend / "llvm_ir.py").write_text("x = 1\n", encoding="utf-8")
    (backend / "pkg" / "llvm_ir.py").write_text("x = 1\n", encoding="utf-8")
    (backend / "control_ir" / "builder.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(boundary, "BACKEND", backend)

    found = {path.relative_to(backend).as_posix() for path in boundary._backend_files()}

    assert found == {"lower.py", "pkg/llvm_ir.py"}


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
