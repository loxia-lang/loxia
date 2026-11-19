# SPDX-License-Identifier: MIT OR Apache-2.0
"""Editor escopado de `loxia.toml` (ADR-0118): comentários, ordem e CRLF preservados."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from loxia.manifest_edit import (
    DependencySpec,
    ManifestEditError,
    add_dependency,
    read_manifest_text,
    remove_dependency,
    unified_diff,
    validate_dependency_name,
    write_manifest_text,
)
from loxia_core.loader.manifest import ManifestError, parse_manifest

GIT = "https://github.com/acme/acme"
REV = "v1.2.3"


def _manifest(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "app"
    root.mkdir(exist_ok=True)
    path = root / "loxia.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _git(name: str = "beta") -> DependencySpec:
    return DependencySpec(git=GIT, rev=REV)


def _dep(tmp_path: Path) -> Path:
    directory = tmp_path / "acme"
    directory.mkdir(exist_ok=True)
    return directory


def test_add_cria_tabela_quando_ausente(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[package]\nname = "app"\nversion = "0.1.0"\n')

    result = add_dependency(path, path.read_text(encoding="utf-8"), "beta", _git())

    assert result.changed
    assert result.text == (
        '[package]\nname = "app"\nversion = "0.1.0"\n\n'
        f'[dependencies]\nbeta = {{ git = "{GIT}", rev = "{REV}" }}\n'
    )
    assert parse_manifest(path, result.text).dependencies["beta"].git == GIT


def test_add_preserva_comentarios_e_ordem(tmp_path: Path) -> None:
    _dep(tmp_path)
    path = _manifest(
        tmp_path,
        '[package]\nname = "app"\n\n'
        "[dependencies]\n"
        "# vendorizado; não remover\n"
        'acme = { path = "../acme" }\n'
        "\n"
        "[modules]\n"
        'paths = ["vendor"]\n',
    )
    (path.parent / "vendor").mkdir()

    result = add_dependency(
        path, path.read_text(encoding="utf-8"), "beta", DependencySpec(git=GIT, rev=REV)
    )

    assert result.text == (
        '[package]\nname = "app"\n\n'
        "[dependencies]\n"
        "# vendorizado; não remover\n"
        'acme = { path = "../acme" }\n'
        f'beta = {{ git = "{GIT}", rev = "{REV}" }}\n'
        "\n"
        "[modules]\n"
        'paths = ["vendor"]\n'
    )


def test_add_mesma_spec_e_noop(tmp_path: Path) -> None:
    _dep(tmp_path)
    path = _manifest(tmp_path, '[dependencies]\nacme = { path = "../acme" }\n')
    text = path.read_text(encoding="utf-8")

    result = add_dependency(path, text, "acme", DependencySpec(path=".././acme"))

    assert not result.changed
    assert result.text == text


def test_add_spec_diferente_falha_sem_mudar(tmp_path: Path) -> None:
    _dep(tmp_path)
    path = _manifest(tmp_path, '[dependencies]\nacme = { path = "../acme" }\n')
    text = path.read_text(encoding="utf-8")

    with pytest.raises(ManifestEditError, match="already declared"):
        add_dependency(path, text, "acme", _git("acme"))

    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize(
    "text",
    [
        '[dependencies.acme]\npath = "../acme"\n',
        '[dependencies]\nacme.path = "../acme"\n',
        '[dependencies]\n"acme" = { path = "../acme" }\n',
    ],
)
def test_add_recusa_forma_nao_editavel(tmp_path: Path, text: str) -> None:
    path = _manifest(tmp_path, text)

    with pytest.raises(ManifestEditError):
        add_dependency(path, text, "beta", _git())

    assert path.read_text(encoding="utf-8") == text


def test_remove_apaga_apenas_a_linha(tmp_path: Path) -> None:
    _dep(tmp_path)
    path = _manifest(
        tmp_path,
        '[package]\nname = "app"\n\n'
        "[dependencies]\n# manter\n"
        'acme = { path = "../acme" }\n'
        f'beta = {{ git = "{GIT}", rev = "{REV}" }}\n'
        "\n[modules]\n",
    )
    (path.parent / "vendor").mkdir()
    text = path.read_text(encoding="utf-8")

    result = remove_dependency(path, text, "acme")

    assert result.changed
    assert 'acme = { path = "../acme" }' not in result.text
    assert "# manter" in result.text
    assert result.text.startswith('[package]\nname = "app"\n\n[dependencies]\n# manter\n')
    parse_manifest(path, result.text)


def test_remove_ausente_falha(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[dependencies]\nbeta = { path = "." }\n')

    with pytest.raises(ManifestEditError, match="not declared"):
        remove_dependency(path, path.read_text(encoding="utf-8"), "acme")


def test_remove_ultima_dependencia_mantem_tabela(tmp_path: Path) -> None:
    _dep(tmp_path)
    path = _manifest(tmp_path, '[dependencies]\nacme = { path = "../acme" }\n')

    result = remove_dependency(path, path.read_text(encoding="utf-8"), "acme")

    assert result.text == "[dependencies]\n"
    parse_manifest(path, result.text)


def test_crlf_e_preservado(tmp_path: Path) -> None:
    _dep(tmp_path)
    path = _manifest(tmp_path, '[package]\r\nname = "app"\r\n')
    text = path.read_text(encoding="utf-8", newline="")

    added = add_dependency(path, text, "acme", DependencySpec(path="../acme"))

    assert "\r\n" in added.text
    assert added.text.count("\n") == added.text.count("\r\n")
    assert read_manifest_text(path) == text


def test_arquivo_sem_newline_final(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[package]\nname = "app"')

    result = add_dependency(path, path.read_text(encoding="utf-8"), "beta", _git())

    assert result.text.endswith("\n")
    assert result.text.startswith('[package]\nname = "app"\n\n[dependencies]\n')
    parse_manifest(path, result.text)


def test_path_inexistente_falha_na_validacao(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[package]\nname = "app"\n')

    with pytest.raises(ManifestError, match="does not exist"):
        add_dependency(
            path, path.read_text(encoding="utf-8"), "beta", DependencySpec(path="../nope")
        )


def test_diff_sem_timestamp_e_relativo(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[package]\nname = "app"\n')
    old = path.read_text(encoding="utf-8")
    new = add_dependency(path, old, "beta", _git()).text

    diff = unified_diff(old, new, "loxia.toml")

    assert diff.startswith("--- loxia.toml\n+++ loxia.toml\n")
    assert str(tmp_path) not in diff
    assert "2026" not in diff
    assert "+beta = " in diff


def test_escrita_atomica_preserva_permissao(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[package]\nname = "app"\n')
    path.chmod(0o600)

    write_manifest_text(path, path.read_text(encoding="utf-8") + "\n")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob(".*.tmp"))


def test_nome_de_dependencia(tmp_path: Path) -> None:
    assert validate_dependency_name("acme_2") == "acme_2"
    for name in ("9lives", "a-b", "std", ""):
        with pytest.raises(ManifestEditError):
            validate_dependency_name(name)


def test_escapa_string_toml(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[package]\nname = "app"\n')
    weird = path.parent / 'dep"quoted'
    weird.mkdir()

    result = add_dependency(
        path, path.read_text(encoding="utf-8"), "odd", DependencySpec(path=weird.name)
    )

    assert 'dep\\"quoted' in result.text
    assert parse_manifest(path, result.text).dependencies["odd"].path == weird.resolve()


def test_read_manifest_text_nao_traduz_crlf(tmp_path: Path) -> None:
    path = _manifest(tmp_path, '[package]\r\nname = "app"\r\n')

    assert "\r\n" in read_manifest_text(path)
