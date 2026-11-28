# SPDX-License-Identifier: MIT OR Apache-2.0
"""Contrato de memória: o lowering só aloca pela ABI do runtime (ADR-0074/ADR-0155).

O ponto do teste é impedir que a pergunta “e se trocarmos o coletor?” volte a ter custo
no codegen: enquanto o backend só chamar `lox_alloc*`, a troca é local a `runtime/core.c`.

Escopo: os módulos Python do backend (o texto é lido pela AST, então comentário e
docstring não contam) e as declarações da ABI no header do runtime. O runtime C em si é
onde o coletor vive — não é auditado aqui.
"""

from __future__ import annotations

import ast
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

_HOST_ALLOCATOR = frozenset({"malloc", "calloc", "realloc", "free"})


def _module_docstrings(tree: ast.AST) -> set[int]:
    """Ids dos `Constant` que são docstring (o texto de documentação não é código)."""
    docstrings: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _code_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _module_docstrings(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _code_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name)
    return names


def _backend_sources() -> list[Path]:
    return sorted(BACKEND.rglob("*.py"))


def test_lowering_never_calls_the_host_allocator() -> None:
    offenders: list[str] = []
    for path in _backend_sources():
        where = path.relative_to(ROOT)
        for text in _code_strings(path):
            if text in _HOST_ALLOCATOR:
                offenders.append(f"{where}: chama {text}()")
        for name in _code_names(path):
            if name.startswith("GC_"):
                offenders.append(f"{where}: referencia {name}")
    assert not offenders, (
        "o lowering só pode alocar por lox_alloc* (ADR-0155); "
        "alocação/coletor fora da ABI do runtime: " + ", ".join(offenders)
    )


def test_runtime_header_declares_the_allocation_abi() -> None:
    header = HEADER.read_text(encoding="utf-8")
    missing = [name for name in ALLOCATION_WRAPPERS if f"{name} (" not in header]
    assert not missing, f"runtime/lox_runtime.h não declara: {', '.join(missing)}"
