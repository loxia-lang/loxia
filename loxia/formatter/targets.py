# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resolve alvos do `loxia fmt`: paths explícitos e diretórios recursivos.

A resolução é determinística: paths explícitos entram sempre (mesmo que um padrão de
`--exclude` os cubra), diretórios são varridos em ordem lexical e apenas `*.lx` são
considerados. Diretórios ocultos e caches conhecidos ficam de fora por padrão.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

DEFAULT_IGNORED_DIRS = frozenset({".git", ".venv", ".uv-cache", "node_modules", "dist", "site"})


class TargetError(ValueError):
    """Alvo inválido (uso incorreto); o CLI traduz para exit 2."""


class TargetNotFoundError(TargetError):
    """Path inexistente; o CLI traduz para exit 66."""


def _relative(path: Path, cwd: Path) -> str:
    try:
        return path.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return Path(os.path.relpath(path, cwd)).as_posix()


def _matches(rel: str, patterns: Sequence[str]) -> bool:
    candidate = PurePosixPath(rel)
    ancestors = [
        PurePosixPath(*candidate.parts[:index]) for index in range(1, len(candidate.parts))
    ]
    for pattern in patterns:
        base = pattern.rstrip("/")
        if candidate.full_match(base) or candidate.full_match(base + "/**"):
            return True
        if any(
            ancestor.full_match(base) or PurePosixPath(ancestor.name).full_match(base)
            for ancestor in ancestors
        ):
            return True
    return False


def _walk_error(error: OSError) -> None:
    raise TargetError(str(error)) from error


def resolve_targets(
    paths: Sequence[str],
    *,
    excludes: Sequence[str] = (),
    cwd: Path | None = None,
) -> list[Path]:
    """Devolve os arquivos a formatar, ordenados e sem duplicatas.

    `excludes` só se aplica a arquivos descobertos dentro de diretórios; um path
    explícito nunca é excluído. Padrões são comparados com o path POSIX relativo ao
    `cwd` (e também com `<padrão>/**`, para excluir um diretório inteiro).
    """
    if not paths:
        raise TargetError("fmt requires at least one path (or --stdin)")

    base = (cwd or Path.cwd()).resolve()
    selected: dict[Path, Path] = {}

    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise TargetNotFoundError(raw)
        if path.is_file():
            selected.setdefault(path.resolve(), path)
            continue
        if not path.is_dir():
            raise TargetError(f"not a file or directory: {raw}")

        for root, dirs, files in os.walk(path, followlinks=False, onerror=_walk_error):
            root_path = Path(root)
            dirs[:] = sorted(
                name
                for name in dirs
                if not name.startswith(".")
                and name not in DEFAULT_IGNORED_DIRS
                and not _matches(_relative(root_path / name, base), excludes)
            )
            for name in sorted(files):
                if name.startswith(".") or not name.endswith(".lx"):
                    continue
                candidate = root_path / name
                if not candidate.is_file() or _matches(_relative(candidate, base), excludes):
                    continue
                selected.setdefault(candidate.resolve(), candidate)

    if not selected:
        raise TargetError("no .lx files found")
    return sorted(selected.values(), key=lambda path: path.as_posix())
