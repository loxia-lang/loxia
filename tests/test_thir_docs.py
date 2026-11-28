# SPDX-License-Identifier: MIT OR Apache-2.0
"""`docs/tech/thir.md` cobre todo nó do modelo THIR.

A página é o contrato de revisão do modelo: um nó novo sem linha na tabela é um contrato
incompleto, do mesmo jeito que a tabela da IR de controle é policiada por
`test_control_ir_docs.py`.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from pathlib import Path

from loxia_core.thir import model

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "tech" / "thir.md"


def _node_names() -> set[str]:
    names: set[str] = set()
    for name, value in inspect.getmembers(model, inspect.isclass):
        if not name.startswith("T") or value.__module__ != model.__name__:
            continue
        if dataclasses.is_dataclass(value):
            names.add(name)
    return names


REQUIRED_NAMES = ("Decl", "Ref", "Storage", "DeclId")


def test_page_lists_every_thir_node() -> None:
    text = PAGE.read_text(encoding="utf-8")
    missing = sorted(name for name in (*_node_names(), *REQUIRED_NAMES) if f"`{name}`" not in text)
    assert not missing, f"docs/tech/thir.md não documenta: {', '.join(missing)}"


def test_page_mentions_no_ghost_node() -> None:
    text = PAGE.read_text(encoding="utf-8")
    known = _node_names()
    ghosts = sorted(
        {name for name in re.findall(r"`(T[A-Z][A-Za-z]*)`", text) if name not in known}
    )
    assert not ghosts, f"docs/tech/thir.md cita nós que não existem: {', '.join(ghosts)}"
