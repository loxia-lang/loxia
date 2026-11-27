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
        root: Path,
        current: dict[Path, str],
        module_cache: ModuleCache | None = None,
        **kwargs: object,
    ) -> object:
        builds.append(1)
        return original(root, current, module_cache, **kwargs)  # type: ignore[arg-type]

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


STD_MAIN = """import std.lists as lists

val xs = [1, 2, 3]
val total: Int = lists.sum(xs)
"""

MANIFEST = """[package]
name = "proj"
version = "0.1.0"

[modules]
paths = ["../shared"]
"""


def _std_workspace(tmp_path: Path) -> tuple[dict[Path, str], Path, Token]:
    main = tmp_path / "main.lx"
    main.write_text(STD_MAIN, encoding="utf-8")
    return {main: STD_MAIN}, main, _token_at(STD_MAIN, "sum(xs)")


def _external_workspace(tmp_path: Path) -> tuple[Path, dict[Path, str], Path, Token]:
    """Projeto com `[modules].paths` apontando para um diretório fora do root."""
    project = tmp_path / "proj"
    shared = tmp_path / "shared"
    project.mkdir()
    shared.mkdir()
    (project / "loxia.toml").write_text(MANIFEST, encoding="utf-8")
    (shared / "lib.lx").write_text(LIB, encoding="utf-8")
    main = project / "main.lx"
    main.write_text(MAIN, encoding="utf-8")
    return project, {main: MAIN}, main, _token_at(MAIN, "soma(1")


def test_references_reach_module_outside_the_root(tmp_path: Path) -> None:
    files, main, token = _std_workspace(tmp_path)
    references = rename.semantic_references(tmp_path, files, main, token)

    assert references is not None
    declaration, _offset = references.declaration
    # `std/` vive fora do root do projeto, mas os usos precisam ser resolvidos.
    assert declaration.parent.name == "std" and declaration.name == "lists.lx"
    occurrences = {(path, offset) for path, offset, _name in references.occurrences}
    assert (declaration, references.declaration[1]) in occurrences
    assert any(path == main for path, _offset in occurrences)


def test_rename_refuses_declaration_outside_the_root(tmp_path: Path) -> None:
    files, main, token = _std_workspace(tmp_path)
    result = rename.semantic_rename(tmp_path, files, main, token, "sum2")

    assert isinstance(result, str)
    assert "outside the workspace root" in result


def test_rename_inside_the_root_still_edits_cross_file(tmp_path: Path) -> None:
    # A presença de um módulo externo (std) não pode bloquear o rename de um
    # símbolo que só é usado dentro do root.
    (tmp_path / "lib.lx").write_text(LIB, encoding="utf-8")
    main = tmp_path / "main.lx"
    text = (
        "import std.lists as lists\n"
        "from lib import soma\n"
        "\n"
        "val xs = [1, 2, 3]\n"
        "val total: Int = soma(lists.sum(xs), 1)\n"
    )
    main.write_text(text, encoding="utf-8")
    files = {path: path.read_text(encoding="utf-8") for path in (main, tmp_path / "lib.lx")}

    result = rename.semantic_rename(tmp_path, files, main, _token_at(text, "soma(lists"), "soma2")

    assert isinstance(result, dict)
    changes = cast(dict[str, list[Any]], result["changes"])
    assert {uri.rsplit("/", 1)[-1] for uri in changes} == {"main.lx", "lib.lx"}


def test_workspace_cache_invalidates_external_module_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, files, main, token = _external_workspace(tmp_path)
    shared = project.parent / "shared"
    builds: list[int] = []
    original = rename._build_workspace

    def counting(*args: object, **kwargs: object) -> object:
        builds.append(1)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(rename, "_build_workspace", counting)
    cache = rename.WorkspaceCache()

    first = rename.semantic_references(project, files, main, token, cache=cache)
    assert first is not None
    assert len(builds) == 1

    # A edição acontece no disco e fora do root: o `files` não muda.
    (shared / "lib.lx").write_text(LIB.replace("soma", "soma2"), encoding="utf-8")
    second = rename.semantic_references(project, files, main, token, cache=cache)

    assert len(builds) == 2
    # A importação deixou de resolver: usar o workspace velho devolveria `first`.
    assert second is None


def test_workspace_cache_reanalyzes_only_the_changed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_path = tmp_path / "a.lx"
    second_path = tmp_path / "b.lx"
    main_path = tmp_path / "main.lx"
    first_path.write_text("fn a() -> Int { return 1 }\n", encoding="utf-8")
    second_path.write_text("fn b() -> Int { return 2 }\n", encoding="utf-8")
    main_path.write_text("val x: Int = 1\n", encoding="utf-8")
    files = {
        path: path.read_text(encoding="utf-8") for path in (first_path, second_path, main_path)
    }
    analyzed: list[str] = []
    original = rename._analyze_file

    def counting(
        root: Path,
        path: Path,
        text: str,
        overrides: dict[Path, str],
        module_cache: ModuleCache | None,
    ) -> object:
        analyzed.append(path.name)
        return original(root, path, text, overrides, module_cache)

    monkeypatch.setattr(rename, "_analyze_file", counting)
    cache = rename.WorkspaceCache()

    assert not isinstance(cache.get(tmp_path, files), str)
    assert sorted(analyzed) == ["a.lx", "b.lx", "main.lx"]

    analyzed.clear()
    changed = dict(files)
    changed[main_path] = "val x: Int = 2\n"
    assert not isinstance(cache.get(tmp_path, changed), str)

    # Só o arquivo editado paga check + resolver + checker de novo.
    assert analyzed == ["main.lx"]


def test_workspace_cache_keeps_only_the_current_workspace(tmp_path: Path) -> None:
    cache = rename.WorkspaceCache(max_files=4)
    for name in ("a.lx", "b.lx"):
        path = tmp_path / name
        path.write_text(f"val {name[0]} = 1\n", encoding="utf-8")
        cache.get(tmp_path, {path: path.read_text(encoding="utf-8")})

    # Uma workspace por vez: o arquivo do workspace anterior sai.
    assert [path.name for path in cache._entries] == ["b.lx"]


def test_workspace_above_the_budget_is_not_retained(tmp_path: Path) -> None:
    path = tmp_path / "a.lx"
    path.write_text("val a = 1\n", encoding="utf-8")
    cache = rename.WorkspaceCache(max_files=0)

    workspace = cache.get(tmp_path, {path: path.read_text(encoding="utf-8")})

    # O workspace é servido, mas nada é retido: sem reter metade, não há thrash.
    assert not isinstance(workspace, str)
    assert cache._entries == {} and cache._modules == {}


def test_workspace_cache_shares_module_contributions(tmp_path: Path) -> None:
    first = tmp_path / "a.lx"
    second = tmp_path / "b.lx"
    first.write_text("import std.lists as lists\n\nval v = lists.sum([1, 2])\n", encoding="utf-8")
    second.write_text("import std.lists as lists\n\nval w = lists.sum([3, 4])\n", encoding="utf-8")
    files = {path: path.read_text(encoding="utf-8") for path in (first, second)}
    cache = rename.WorkspaceCache()

    workspace = cache.get(tmp_path, files)

    assert not isinstance(workspace, str)
    # Os dois importadores compartilham a mesma contribuição de `std.lists`:
    # guardar os tokens do closure por arquivo faria o cache crescer com
    # `arquivos * closure`.
    assert list(cache._modules) == [
        (workspace.analyses[first].module_map["std/lists.lx"], "std/lists.lx")
    ]
    assert cache._module_tokens > 0
    assert all(len(entry.modules) == 1 for entry in cache._entries.values())
