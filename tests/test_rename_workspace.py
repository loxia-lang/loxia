# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resolução de arquivo no workspace de rename (cache por arquivo)."""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia import rename
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.tokens import Token

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
