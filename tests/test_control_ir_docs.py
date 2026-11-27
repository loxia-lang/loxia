# SPDX-License-Identifier: MIT OR Apache-2.0
"""The control-IR reference table must cover every public model node (ADR-0153)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("llvmlite")

import dataclasses
import inspect

from loxia_core.backend.control_ir import model

PAGE = Path(__file__).resolve().parents[1] / "docs" / "tech" / "control-ir.md"
ROW = re.compile(r"^\| `([A-Z][A-Za-z0-9]*)` \|", re.MULTILINE)
NODES = {
    name
    for name, value in inspect.getmembers(model, inspect.isclass)
    if dataclasses.is_dataclass(value)
}


def test_model_table_covers_every_node() -> None:
    listed = set(ROW.findall(PAGE.read_text(encoding="utf-8")))

    assert listed == NODES, (
        f"control-ir.md missing {sorted(NODES - listed)}, extra {sorted(listed - NODES)}"
    )


def test_invariants_are_listed() -> None:
    text = PAGE.read_text(encoding="utf-8")

    for number in range(1, 8):
        assert f"| C{number} |" in text, f"control-ir.md missing C{number}"
