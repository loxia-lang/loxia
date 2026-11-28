# SPDX-License-Identifier: MIT OR Apache-2.0
"""Contrato de memória: o lowering só aloca pela ABI do runtime (ADR-0074/ADR-0155).

O ponto do teste é impedir que a pergunta “e se trocarmos o coletor?” volte a ter custo
no codegen: enquanto o backend só chamar `lox_alloc*`, a troca é local a `runtime/core.c`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "loxia_core" / "backend"
HEADER = ROOT / "runtime" / "lox_runtime.h"

ALLOCATION_WRAPPERS = (
    "lox_alloc",
    "lox_alloc_atomic",
    "lox_alloc_cell",
    "lox_alloc_env",
    "lox_alloc_closure",
    "lox_alloc_bytes",
)

_FORBIDDEN_CALLS = re.compile(r'"(malloc|calloc|realloc|free)"')
_GC_SYMBOL = re.compile(r"\bGC_[A-Za-z_]+\b")


def _backend_sources() -> list[Path]:
    return sorted(BACKEND.rglob("*.py"))


def test_lowering_never_calls_the_host_allocator() -> None:
    offenders: list[str] = []
    for path in _backend_sources():
        text = path.read_text(encoding="utf-8")
        for match in _FORBIDDEN_CALLS.finditer(text):
            offenders.append(f"{path.relative_to(ROOT)}:{match.group(0)}")
        if _GC_SYMBOL.search(text):
            offenders.append(f"{path.relative_to(ROOT)}: referencia símbolo do GC")
    assert not offenders, (
        "o lowering só pode alocar por lox_alloc* (ADR-0155); "
        "alocação/coletor fora da ABI do runtime: " + ", ".join(offenders)
    )


def test_runtime_header_declares_the_allocation_abi() -> None:
    header = HEADER.read_text(encoding="utf-8")
    missing = [name for name in ALLOCATION_WRAPPERS if f"{name} (" not in header]
    assert not missing, f"runtime/lox_runtime.h não declara: {', '.join(missing)}"
