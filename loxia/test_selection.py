# SPDX-License-Identifier: MIT OR Apache-2.0
"""Seleção de testes por mudança (`--changed`) e por shard (`--shard`).

O grafo é conservador: qualquer mudança que não seja um `.lx` existente roda todos os
testes; um `.lx` deletado ou fora do projeto também. Para `.lx`, o runner lê os imports
(aceitando falso positivo de comentário/string, que só seleciona testes a mais) e segue a
closure transitiva dos testes descobertos.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from loxia_core.loader.loader import SOURCE_SUFFIX, STD_ROOT

SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".uv-cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)
_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)",
    re.MULTILINE,
)


class SelectionError(Exception):
    """Falha ao consultar o git ou ao interpretar a seleção."""


def _git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        reason = completed.stderr.strip().splitlines()
        raise SelectionError("git: " + (reason[-1] if reason else "command failed"))
    return [line for line in completed.stdout.splitlines() if line]


def changed_paths(ref: str = "HEAD") -> list[Path]:
    """Arquivos alterados desde `ref`, incluindo worktree, index e untracked."""
    if not ref or ref.startswith("-"):
        raise SelectionError(f"ref inválida: {ref!r}")
    root = Path.cwd().resolve()
    paths: set[Path] = set()
    for line in _git("diff", "--name-only", "--diff-filter=ACDMRT", "--relative", ref, "--"):
        paths.add((root / line).resolve())
    for line in _git("ls-files", "--others", "--exclude-standard"):
        paths.add((root / line).resolve())
    return sorted(paths)


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _project_sources(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")
        )
        for name in filenames:
            if name.endswith(SOURCE_SUFFIX):
                files.append(Path(directory) / name)
    return files


def _resolve_import(module: str, root: Path) -> Path | None:
    parts = module.split(".")
    if parts[0] == "std":
        if len(parts) == 1:
            return None
        candidate = STD_ROOT.joinpath(*parts[1:]).with_suffix(SOURCE_SUFFIX)
    else:
        candidate = root.joinpath(*parts).with_suffix(SOURCE_SUFFIX)
    return candidate.resolve() if candidate.is_file() else None


def _imports(path: Path, root: Path) -> set[Path]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    result: set[Path] = set()
    for match in _IMPORT.finditer(text):
        resolved = _resolve_import(match.group(1), root)
        if resolved is not None:
            result.add(resolved)
    return result


def _closure(path: Path, graph: dict[Path, set[Path]], seen: set[Path]) -> set[Path]:
    if path in seen:
        return set()
    seen.add(path)
    result = {path}
    for dependency in graph.get(path, set()):
        result |= _closure(dependency, graph, seen)
    return result


def select_changed(tests: list[Path], changed: list[Path]) -> list[Path]:
    """Mantém os testes cuja closure de imports toca algum arquivo alterado."""
    if not changed:
        return []
    root = Path.cwd().resolve()
    changed_set = {path.resolve() for path in changed}
    if any(
        path.suffix != SOURCE_SUFFIX or not path.is_file() or not _under(path, root)
        for path in changed_set
    ):
        return list(tests)

    graphs: dict[Path, dict[Path, set[Path]]] = {}
    selected: list[Path] = []
    for test in tests:
        resolved = test.resolve()
        test_root = resolved.parent
        if test_root not in graphs:
            sources = [path.resolve() for path in _project_sources(test_root)]
            graphs[test_root] = {path: _imports(path, test_root) for path in sources}
        closure = _closure(resolved, graphs[test_root], set())
        if closure & changed_set:
            selected.append(test)
    return selected


def parse_shard(value: str) -> tuple[int, int]:
    """Interpreta `INDEX/TOTAL` (1-based, INDEX <= TOTAL)."""
    if value.count("/") != 1:
        raise ValueError("use INDEX/TOTAL")
    index_text, total_text = value.split("/")
    if not index_text.isdigit() or not total_text.isdigit():
        raise ValueError("use INDEX/TOTAL")
    index, total = int(index_text), int(total_text)
    if total < 1 or index < 1 or index > total:
        raise ValueError("INDEX must be between 1 and TOTAL")
    return index, total


def shard_files(files: list[Path], value: str) -> list[Path]:
    index, total = parse_shard(value)
    return files[index - 1 :: total]
