# SPDX-License-Identifier: MIT OR Apache-2.0
"""Testes da seleção `--changed`/`--shard` (sem subprocesso do runner)."""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia.test_selection import parse_shard, select_changed, shard_files


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    monkeypatch.chdir(tmp_path)
    tests = tmp_path / "tests"
    lib = tests / "lib"
    tests.mkdir()
    lib.mkdir()
    (lib / "util.lx").write_text("fn base() -> Int { return 2 }\n", encoding="utf-8")
    (lib / "math.lx").write_text(
        "import lib.util as u\nfn double(x: Int) -> Int { return u.base() * x }\n",
        encoding="utf-8",
    )
    test = tests / "uses_test.lx"
    test.write_text(
        "import lib.math as m\nval suite = 0\nsuite\n",
        encoding="utf-8",
    )
    return test, lib / "math.lx", lib / "util.lx"


def test_changed_segue_imports_transitivos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test, _, util = _project(tmp_path, monkeypatch)

    assert select_changed([test], [util]) == [test]
    assert select_changed([test], [test]) == [test]
    assert select_changed([test], []) == []


def test_changed_nao_lox_ou_ausente_roda_tudo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test, _, _ = _project(tmp_path, monkeypatch)
    readme = tmp_path / "README.md"
    readme.write_text("x\n", encoding="utf-8")

    assert select_changed([test], [readme]) == [test]
    assert select_changed([test], [tmp_path / "missing.lx"]) == [test]


def test_parse_shard_valido_e_invalido() -> None:
    assert parse_shard("1/3") == (1, 3)
    assert parse_shard("3/3") == (3, 3)
    for value in ("0/3", "4/3", "1/0", "1", "a/b", "1/2/3"):
        with pytest.raises(ValueError):
            parse_shard(value)


def test_shard_files_round_robin() -> None:
    files = [Path(f"{index}.lx") for index in range(5)]

    assert shard_files(files, "1/2") == [files[0], files[2], files[4]]
    assert shard_files(files, "2/2") == [files[1], files[3]]


def test_changed_respeita_manifest_e_modules_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O loader resolve imports na raiz do manifest, não no diretório do teste."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "loxia.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n\n[modules]\npaths = ["src"]\n',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    lib = src / "lib.lx"
    lib.write_text("fn value() -> Int { return 1 }\n", encoding="utf-8")
    tests = tmp_path / "tests" / "sub"
    tests.mkdir(parents=True)
    test = tests / "uses_test.lx"
    test.write_text("import lib\nval value = 1\n", encoding="utf-8")

    assert select_changed([test], [lib]) == [test]


def test_helpers_de_selecao_cobrem_bordas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from loxia.test_selection import (
        SelectionError,
        _closure,
        _imports,
        _project_roots,
        _resolve_import,
        changed_paths,
    )

    monkeypatch.chdir(tmp_path)
    (tmp_path / "loxia.toml").write_text("[package\n", encoding="utf-8")
    test = tmp_path / "tests" / "borda_test.lx"
    test.parent.mkdir()
    test.write_text("import std\nimport nao_existe\n", encoding="utf-8")

    assert _project_roots(test) == (test.parent,)
    assert _resolve_import("std", (tmp_path,)) is None
    assert _resolve_import("nao_existe", (tmp_path,)) is None
    assert _imports(tmp_path / "ausente.lx", (tmp_path,)) == set()
    assert _closure(test.resolve(), {}, set()) == {test.resolve()}
    assert _closure(test.resolve(), {test.resolve(): {test.resolve()}}, set()) == {test.resolve()}

    outside = tmp_path.parent / "fora.lx"
    outside.write_text("print(1)\n", encoding="utf-8")
    assert select_changed([test], [outside]) == [test]

    with pytest.raises(SelectionError):
        changed_paths("--help")
