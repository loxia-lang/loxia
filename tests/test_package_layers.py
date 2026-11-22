# SPDX-License-Identifier: MIT OR Apache-2.0
"""Direção das dependências entre os pacotes de `loxia_core` (AGENTS.md §3-§4).

A regra mora aqui, não só na documentação: sem este teste uma aresta para cima passa
despercebida e o mapa dos docs mente (foi o caso de `frontend -> execution`). Exceção
declarada precisa de motivo e continua sendo verificada.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "loxia_core"

# Pacote -> pacotes que ele não pode importar (dependência só para baixo).
FORBIDDEN: dict[str, set[str]] = {
    "frontend": {"execution", "semantics", "backend"},
    "diagnostics": {"execution", "semantics", "backend"},
    "loader": {"execution", "semantics", "backend"},
    "execution": {"semantics", "backend"},
    "semantics": {"backend"},
}

# Exceções declaradas: (arquivo relativo a `loxia_core`, módulo importado).
# `ast_printer` formata valores dinâmicos no dump; mover o formatador para `loxia/`
# quebraria os links dos ADRs, então a aresta é declarada e testada em vez de escondida.
ALLOWED: set[tuple[str, str]] = {
    ("frontend/ast_printer.py", "loxia_core.execution.values"),
}


def _package(path: Path) -> str:
    parts = path.relative_to(CORE).parts
    return parts[0] if len(parts) > 1 else "(root)"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def _violations() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in CORE.rglob("*.py"):
        blocked = FORBIDDEN.get(_package(path), set())
        if not blocked:
            continue
        for module in _imports(path):
            parts = module.split(".")
            if len(parts) < 2 or parts[0] != "loxia_core" or parts[1] not in blocked:
                continue
            found.add((str(path.relative_to(CORE)), module))
    return found


def test_dependencias_apontam_so_para_baixo() -> None:
    violations = _violations() - ALLOWED
    assert not violations, "dependência para cima em loxia_core (AGENTS.md §3): " + ", ".join(
        f"{source} -> {module}" for source, module in sorted(violations)
    )


def test_excecoes_declaradas_continuam_necessarias() -> None:
    stale = ALLOWED - _violations()
    assert not stale, "exceção de camada que não existe mais; remova de ALLOWED: " + ", ".join(
        f"{source} -> {module}" for source, module in sorted(stale)
    )


def test_core_nao_importa_o_cli() -> None:
    offenders = sorted(
        str(path.relative_to(CORE))
        for path in CORE.rglob("*.py")
        if any(module == "loxia" or module.startswith("loxia.") for module in _imports(path))
    )
    assert not offenders, "loxia_core não pode depender de loxia/: " + ", ".join(offenders)
