# SPDX-License-Identifier: MIT OR Apache-2.0
"""Congela o oráculo do front-end (ADR-0129).

Três superfícies sobre o corpus (`std/`, `tests/cases/`, `examples/`):

- AST JSON em arquivo único (hash canônico);
- bytes do `format_source` (formatter Python é a referência);
- diagnósticos estruturados dos casos de erro (fase/código/severidade/span).

Atualizar o manifesto é uma decisão: `make oracle-update`. Um diff inesperado aqui é
mudança de oráculo, não flake.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tools.oracle_snapshot import (
    MANIFEST,
    _diagnostics,
    build_manifest,
    corpus_files,
    error_cases,
    load_manifest,
)


@pytest.fixture(scope="module")
def manifest() -> dict[str, object]:
    return build_manifest()


def _expected() -> dict[str, object]:
    assert MANIFEST.exists(), "missing tests/oracle/frontend.json; run `make oracle-update`"
    return load_manifest()


def _section(manifest: dict[str, object], name: str) -> object:
    expected = _expected()
    actual = manifest[name]
    assert actual == expected[name], (
        f"oracle section {name!r} is stale; run `make oracle-update` and review the diff"
    )
    return actual


def test_schema_version(manifest: dict[str, object]) -> None:
    assert _section(manifest, "schema_version") == 1


def test_ast_snapshot(manifest: dict[str, object]) -> None:
    ast = cast(dict[str, str], _section(manifest, "ast"))
    assert ast, "AST snapshot is empty"
    assert all(len(digest) == 64 for digest in ast.values())


def test_formatter_snapshot(manifest: dict[str, object]) -> None:
    fmt = cast(dict[str, str], _section(manifest, "fmt"))
    assert fmt, "formatter snapshot is empty"
    assert all(len(digest) == 64 for digest in fmt.values())


def test_diagnostics_snapshot(manifest: dict[str, object]) -> None:
    diagnostics = cast(dict[str, list[dict[str, object]]], _section(manifest, "diagnostics"))
    parse_errors = cast(list[str], manifest["parse_errors"])
    expected = {path.relative_to(MANIFEST.parents[2]).as_posix() for path in error_cases()}
    expected.update(parse_errors)
    assert set(diagnostics) == expected
    for path, items in diagnostics.items():
        assert items, f"{path}: empty diagnostic snapshot"
        for item in items:
            assert item["code"]
            assert item["phase"]
            assert item["severity"] == "error"
            assert item["span"] is not None


def test_parse_error_set_is_declared(manifest: dict[str, object]) -> None:
    parse_errors = cast(list[str], _section(manifest, "parse_errors"))
    ast = cast(dict[str, str], manifest["ast"])
    fmt = cast(dict[str, str], manifest["fmt"])
    files = {path.relative_to(MANIFEST.parents[2]).as_posix() for path in corpus_files()}

    assert set(ast) == set(fmt)
    assert set(ast) | set(parse_errors) == files
    assert set(ast) & set(parse_errors) == set()


def test_diagnostics_are_cwd_independent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    path = MANIFEST.parents[2] / "tests" / "cases" / "errors" / "division_by_zero.lx"

    items = _diagnostics(path)
    span = cast(dict[str, object], items[0]["span"])

    assert span["file"] == "tests/cases/errors/division_by_zero.lx"


def test_manifest_is_canonical_json() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    parsed = json.loads(text)

    assert text.endswith("\n")
    assert json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + "\n" == text
