# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resolução de arquivo no workspace de rename (cache por arquivo)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from loxia import rename
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.tokens import Token
from loxia_core.loader.module_cache import ModuleCache

LIB = """fn soma(a: Int, b: Int) -> Int {
  return a + b
}

fn dobro(x: Int) -> Int {
  return soma(x, x)
}
"""

MAIN = """from lib import soma

val total: Int = soma(1, 2)
"""


def _workspace_files(tmp_path: Path) -> dict[Path, str]:
    (tmp_path / "lib.lx").write_text(LIB, encoding="utf-8")
    (tmp_path / "main.lx").write_text(MAIN, encoding="utf-8")
    return {path: path.read_text(encoding="utf-8") for path in sorted(tmp_path.glob("*.lx"))}


def _token_at(text: str, needle: str) -> Token:
    offset = text.index(needle)
    tokens = Scanner(text, ErrorReporter(max_errors=0)).scan_tokens()
    return next(token for token in tokens if token.offset == offset)


def test_workspace_resolves_each_file_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = _workspace_files(tmp_path)
    calls: list[tuple[str, str]] = []
    original = rename._token_file

    def counting(token: Token, root: Path, fallback: Path) -> Path:
        calls.append((token.file, str(fallback)))
        return original(token, root, fallback)

    monkeypatch.setattr(rename, "_token_file", counting)
    token = _token_at(MAIN, "soma(1")
    references = rename.semantic_references(tmp_path, files, tmp_path / "main.lx", token)

    assert references is not None
    assert len(references.occurrences) >= 2
    # Dois arquivos, dois fallbacks: o cache evita uma resolução por token.
    assert len(calls) <= 6


def test_workspace_cache_reuses_until_text_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _workspace_files(tmp_path)
    builds: list[int] = []
    original = rename._build_workspace

    def counting(
        root: Path, current: dict[Path, str], module_cache: ModuleCache | None = None
    ) -> object:
        builds.append(1)
        return original(root, current, module_cache)

    monkeypatch.setattr(rename, "_build_workspace", counting)
    cache = rename.WorkspaceCache()
    token = _token_at(MAIN, "soma(1")
    main = tmp_path / "main.lx"

    first = rename.semantic_references(tmp_path, files, main, token, cache=cache)
    second = rename.semantic_references(tmp_path, files, main, token, cache=cache)

    assert first is not None and second is not None
    assert first.occurrences == second.occurrences
    assert len(builds) == 1

    changed = dict(files)
    changed[main] = MAIN + "\nprint(total)\n"
    third = rename.semantic_references(tmp_path, changed, main, token, cache=cache)

    assert third is not None
    assert len(builds) == 2


def test_rename_uses_unsaved_import_text(tmp_path: Path) -> None:
    files = _workspace_files(tmp_path)
    lib = tmp_path / "lib.lx"
    files[lib] = "# edit\n" + LIB
    token = _token_at(MAIN, "soma(1")

    result = rename.semantic_rename(tmp_path, files, tmp_path / "main.lx", token, "soma2")

    assert isinstance(result, dict)
    changes = cast(dict[str, list[dict[str, Any]]], result["changes"])
    lib_edits = next(edits for uri, edits in changes.items() if uri.endswith("/lib.lx"))
    lines = {cast(dict[str, dict[str, int]], edit["range"])["start"]["line"] for edit in lib_edits}
    # O buffer prefixa uma linha; usar o disco deslocaria as edições para a linha 0.
    assert lines <= {1, 6}
    assert 0 not in lines


def test_workspace_cache_shares_the_module_cache(tmp_path: Path) -> None:
    files = _workspace_files(tmp_path)
    token = _token_at(MAIN, "soma(1")
    module_cache = ModuleCache()

    references = rename.semantic_references(
        tmp_path,
        files,
        tmp_path / "main.lx",
        token,
        cache=rename.WorkspaceCache(),
        module_cache=module_cache,
    )

    assert references is not None
    # Com `WorkspaceCache` o loader continua precisando do cache de módulos; sem
    # repassá-lo, o rename reparseia `lib.lx` a cada workspace reconstruído.
    assert len(module_cache) == 1
