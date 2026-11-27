# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cache nativo: chave por closure, memo da toolchain, store atômico e prune.

Não precisa do backend instalado: aqui o objeto é o módulo, não o binário. O
`run` AOT de verdade vive em `tests/test_run_native.py` (processo real).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from loxia import native_cache
from loxia.cli_args import _build_subcommand_parser
from tests.inprocess import run_cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "cache"
    monkeypatch.setenv("LOX_BUILD_CACHE", str(directory))
    return directory


def _request(entry: Path, *flags: str) -> native_cache.BuildRequest:
    return native_cache.BuildRequest(
        entry=entry,
        flags=flags,
        stamp="stamp-de-teste",
    )


# -- tamanho ---------------------------------------------------------------


def test_parse_size_unidades() -> None:
    assert native_cache.parse_size("512M") == 512 * 1024**2
    assert native_cache.parse_size("2g") == 2 * 1024**3
    assert native_cache.parse_size("1048576") == 1024**2


@pytest.mark.parametrize("text", ["", "abc", "1T", "-1M", "0"])
def test_parse_size_rejeita_invalido(text: str) -> None:
    with pytest.raises(ValueError):
        native_cache.parse_size(text)


# -- chave -----------------------------------------------------------------


def test_chave_deterministica_e_sensivel_a_fonte_e_flags(tmp_path: Path) -> None:
    entry = tmp_path / "main.lx"
    texts = {"main.lx": "print(1)\n"}

    first = native_cache.build_key(_request(entry), texts)
    second = native_cache.build_key(_request(entry), dict(reversed(list(texts.items()))))
    assert first == second

    changed = native_cache.build_key(_request(entry), {"main.lx": "print(2)\n"})
    assert changed != first

    flagged = native_cache.build_key(_request(entry, "heap=128M"), texts)
    assert flagged != first


def test_chave_inclui_manifesto_e_lock(tmp_path: Path) -> None:
    entry = tmp_path / "main.lx"
    manifest = tmp_path / "loxia.toml"
    manifest.write_text("[dependencies]\n", encoding="utf-8")
    texts = {"main.lx": "print(1)\n"}

    before = native_cache.build_key(_request(entry), texts, watched=[manifest])
    manifest.write_text('[dependencies]\nacme = { path = "acme" }\n', encoding="utf-8")
    after = native_cache.build_key(_request(entry), texts, watched=[manifest])

    assert before != after


def test_entry_name_estavel(tmp_path: Path) -> None:
    entry = tmp_path / "main.lx"

    assert native_cache.entry_name(entry) == native_cache.entry_name(entry)
    assert native_cache.entry_name(entry).endswith("-main")
    assert native_cache.entry_name(tmp_path / "outro.lx") != native_cache.entry_name(entry)


# -- memo da toolchain -----------------------------------------------------


def test_memo_da_toolchain_evita_o_subprocesso_do_cc(
    cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = native_cache._compiler_version

    def counting(compiler: str) -> str:
        calls.append(compiler)
        return original(compiler)

    monkeypatch.setattr(native_cache, "_compiler_version", counting)
    first = native_cache.toolchain_stamp()
    second = native_cache.toolchain_stamp()

    assert first == second
    assert len(calls) == 1, "o hit do memo não pode rodar `cc --version` de novo"
    assert (cache / "toolchain.json").is_file()


def test_stamp_inclui_cpath_e_library_path(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # O `cc` lê CPATH/LIBRARY_PATH; mudá-los muda o binário e tem que invalidar.
    base = native_cache.toolchain_stamp()

    monkeypatch.setenv("CPATH", "/opt/loxia-test/include")
    with_cpath = native_cache.toolchain_stamp()
    assert with_cpath != base and "opt/loxia-test/include" in with_cpath

    monkeypatch.setenv("LIBRARY_PATH", "/opt/loxia-test/lib")
    with_library = native_cache.toolchain_stamp()
    assert with_library != with_cpath and "opt/loxia-test/lib" in with_library


def test_memo_e_reescrito_quando_a_versao_muda(
    cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native_cache.toolchain_stamp()
    data = json.loads((cache / "toolchain.json").read_text(encoding="utf-8"))
    data["version"] = "0.0.0-outra"
    (cache / "toolchain.json").write_text(json.dumps(data), encoding="utf-8")

    calls: list[str] = []
    original = native_cache._compiler_version

    def counting(compiler: str) -> str:
        calls.append(compiler)
        return original(compiler)

    monkeypatch.setattr(native_cache, "_compiler_version", counting)

    native_cache.toolchain_stamp()

    assert calls, "versão diferente precisa recomputar a identidade"


# -- store / locate --------------------------------------------------------


def test_store_publica_binario_executavel_e_reusa(cache: Path, tmp_path: Path) -> None:
    directory = native_cache.directory("run")
    assert directory is not None
    builds: list[Path] = []

    def build(target: Path) -> str | None:
        builds.append(target)
        target.write_bytes(b"binario")
        return None

    built, error = native_cache.store(
        directory, "k1", "prog", build, fallback=tmp_path / "fallback"
    )
    assert error is None and built is not None
    assert os.access(built, os.X_OK)
    assert native_cache.locate(directory, "k1", "prog") == Path(built)

    again, _ = native_cache.store(directory, "k1", "prog", build, fallback=tmp_path / "fallback")
    assert again == built
    assert len(builds) == 1


def test_store_nao_publica_binario_de_build_que_falhou(cache: Path, tmp_path: Path) -> None:
    directory = native_cache.directory("run")
    assert directory is not None

    def build(target: Path) -> str | None:
        target.write_bytes(b"parcial")
        return "falhou"

    built, error = native_cache.store(
        directory, "k2", "prog", build, fallback=tmp_path / "fallback"
    )

    assert built is None
    assert error == "falhou"
    assert native_cache.locate(directory, "k2", "prog") is None
    assert not list(directory.glob("k2/*"))


# -- prune -----------------------------------------------------------------


def _fake_binary(path: Path, size: int, mtime: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


def test_prune_remove_os_mais_antigos(cache: Path) -> None:
    old = _fake_binary(cache / "run" / "k1" / "velho", 2 * 1024**2, 1_000_000)
    new = _fake_binary(cache / "run" / "k2" / "novo", 2 * 1024**2, 2_000_000)

    result = native_cache.prune(max_bytes=3 * 1024**2)

    assert result.removed == 1
    assert not old.exists()
    assert new.exists()


def test_prune_dry_run_nao_apaga(cache: Path) -> None:
    path = _fake_binary(cache / "run" / "k1" / "bin", 2 * 1024**2, 1_000_000)

    result = native_cache.prune(max_bytes=1024**2, dry_run=True)

    assert result.removed == 1
    assert path.exists()


def test_prune_protege_o_binario_recem_gerado(cache: Path) -> None:
    old = _fake_binary(cache / "run" / "k1" / "velho", 2 * 1024**2, 1_000_000)
    fresh = _fake_binary(cache / "run" / "k2" / "novo", 2 * 1024**2, 2_000_000)

    native_cache.prune(max_bytes=2 * 1024**2, protect=[fresh])

    assert not old.exists()
    assert fresh.exists()


def test_cache_size_soma_os_binarios(cache: Path) -> None:
    _fake_binary(cache / "run" / "k1" / "a", 1024, 1_000_000)
    _fake_binary(cache / "tests" / "k2" / "b", 2048, 1_000_000)

    assert native_cache.cache_size() == 3072


# -- comando ---------------------------------------------------------------


def test_cache_path_respeita_a_variavel(cache: Path) -> None:
    result = run_cli("cache", "path", "--json", env={"LOX_BUILD_CACHE": str(cache)})

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["path"] == str(cache)


def test_cache_prune_json(cache: Path) -> None:
    _fake_binary(cache / "run" / "k1" / "bin", 2 * 1024**2, 1_000_000)

    result = run_cli(
        "cache", "prune", "--max-size", "1M", "--json", env={"LOX_BUILD_CACHE": str(cache)}
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["removed"] == 1
    assert payload["freed"] == 2 * 1024**2


def test_cache_prune_dry_run_por_cli(cache: Path) -> None:
    path = _fake_binary(cache / "run" / "k1" / "bin", 2 * 1024**2, 1_000_000)

    result = run_cli(
        "cache", "prune", "--max-size", "1M", "--dry-run", env={"LOX_BUILD_CACHE": str(cache)}
    )

    assert result.returncode == 0, result.stderr
    assert "would remove" in result.stdout
    assert path.exists()


def test_cache_no_help_do_topo() -> None:
    parser = _build_subcommand_parser("cache")
    help_text = parser.format_help()

    assert "--max-size" in help_text
    assert "--dry-run" in help_text
