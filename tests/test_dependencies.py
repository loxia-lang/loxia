# SPDX-License-Identifier: MIT OR Apache-2.0
"""Lock, hash e modo `--frozen` das dependências `path` (ADR-0104)."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def _cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _run(script: Path, *flags: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return _cli(*flags, str(script), cwd=cwd)


def _project(tmp_path: Path) -> tuple[Path, Path]:
    app = tmp_path / "app"
    dep = tmp_path / "acme"
    app.mkdir()
    dep.mkdir()
    (app / "loxia.toml").write_text(
        '[package]\nname = "app"\n\n[dependencies]\nacme = { path = "../acme" }\n',
        encoding="utf-8",
    )
    (dep / "loxia.toml").write_text(
        '[package]\nname = "acme"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (dep / "base.lx").write_text(
        "fn dobro(n: Int) -> Int { return n * 2 }\n",
        encoding="utf-8",
    )
    (app / "main.lx").write_text(
        "import acme.base as base\nprint(base.dobro(21))\n",
        encoding="utf-8",
    )
    return app, dep


def _lock(app: Path) -> dict[str, object]:
    return tomllib.loads((app / "loxia.lock").read_text(encoding="utf-8"))


def test_lock_grava_identidade_versao_e_hash(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)

    result = _cli("lock", cwd=app)

    assert result.returncode == 0, result.stderr
    lock = _lock(app)
    assert lock["version"] == 1
    packages = lock["package"]
    assert isinstance(packages, list)
    (package,) = packages
    assert package["name"] == "acme"
    assert package["path"] == "../acme"
    assert package["version"] == "0.1.0"
    assert len(package["sha256"]) == 64
    assert str(tmp_path) not in (app / "loxia.lock").read_text(encoding="utf-8")


def test_lock_e_deterministico_entre_execucoes(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)

    _cli("lock", cwd=app)
    first = (app / "loxia.lock").read_bytes()
    _cli("lock", cwd=app)

    assert (app / "loxia.lock").read_bytes() == first


def test_lock_ordena_dependencias_por_nome(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)
    other = tmp_path / "zeta"
    other.mkdir()
    (other / "z.lx").write_text("fn z() -> Int { return 1 }\n", encoding="utf-8")
    (app / "loxia.toml").write_text(
        '[package]\nname = "app"\n\n'
        '[dependencies]\nzeta = { path = "../zeta" }\nacme = { path = "../acme" }\n',
        encoding="utf-8",
    )

    _cli("lock", cwd=app)
    text = (app / "loxia.lock").read_text(encoding="utf-8")

    assert text.index('name = "acme"') < text.index('name = "zeta"')


def test_frozen_resolve_pelo_lock(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)
    _cli("lock", cwd=app)

    result = _run(app / "main.lx", "run", "--frozen", cwd=app)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "42\n"


def test_frozen_detecta_conteudo_alterado(tmp_path: Path) -> None:
    app, dep = _project(tmp_path)
    _cli("lock", cwd=app)
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n * 3 }\n", encoding="utf-8")

    frozen = _run(app / "main.lx", "run", "--frozen", cwd=app)
    live = _run(app / "main.lx", "run", cwd=app)

    assert frozen.returncode == 65
    assert "changed since loxia.lock" in frozen.stderr
    assert "error[C0002]" in frozen.stderr
    assert live.returncode == 0
    assert live.stdout == "63\n"


def test_frozen_sem_lock_falha(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)

    result = _run(app / "main.lx", "run", "--frozen", cwd=app)

    assert result.returncode == 65
    assert "loxia.lock is missing" in result.stderr


def test_frozen_rejeita_pacote_removido_do_manifest(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)
    _cli("lock", cwd=app)
    (app / "loxia.toml").write_text('[package]\nname = "app"\n', encoding="utf-8")
    (app / "main.lx").write_text('print("ok")\n', encoding="utf-8")

    result = _run(app / "main.lx", "run", "--frozen", cwd=app)

    assert result.returncode == 65
    assert "which is not in loxia.toml" in result.stderr


def test_frozen_rejeita_lock_com_chave_desconhecida(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)
    _cli("lock", cwd=app)
    lock = app / "loxia.lock"
    lock.write_text(lock.read_text(encoding="utf-8") + "\n[[package.extra]]\n", encoding="utf-8")

    result = _run(app / "main.lx", "run", "--frozen", cwd=app)

    assert result.returncode == 65
    assert "Unknown" in result.stderr or "Invalid TOML" in result.stderr


def test_lock_check_exit_1_quando_desatualizado(tmp_path: Path) -> None:
    app, dep = _project(tmp_path)
    _cli("lock", cwd=app)
    fresh = _cli("lock", "--check", cwd=app)
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n * 4 }\n", encoding="utf-8")
    stale = _cli("lock", "--check", cwd=app)

    assert fresh.returncode == 0
    assert fresh.stderr == ""
    assert stale.returncode == 1
    assert "out of date" in stale.stderr


def test_fetch_verifica_o_hash_do_lock(tmp_path: Path) -> None:
    app, dep = _project(tmp_path)
    _cli("lock", cwd=app)
    ok = _cli("fetch", cwd=app)
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n + 1 }\n", encoding="utf-8")
    stale = _cli("fetch", cwd=app)

    assert ok.returncode == 0, ok.stderr
    assert stale.returncode == 65
    assert "changed since loxia.lock" in stale.stderr


def test_fetch_sem_lock_falha(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)

    result = _cli("fetch", cwd=app)

    assert result.returncode == 65
    assert "loxia.lock is missing" in result.stderr


def test_lock_sem_manifest_falha(tmp_path: Path) -> None:
    result = _cli("lock", cwd=tmp_path)

    assert result.returncode == 65
    assert "No loxia.toml found." in result.stderr


def test_lock_descobre_o_manifest_no_ancestral(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)
    nested = app / "src"
    nested.mkdir()
    (nested / "main.lx").write_text("print(1)\n", encoding="utf-8")

    result = _cli("lock", cwd=nested)

    assert result.returncode == 0, result.stderr
    assert (app / "loxia.lock").is_file()


def test_version_invalida_no_manifest_e_erro_de_manifest(tmp_path: Path) -> None:
    app, dep = _project(tmp_path)
    (dep / "loxia.toml").write_text(
        '[package]\nname = "acme"\nversion = "1.2"\n',
        encoding="utf-8",
    )

    result = _cli("lock", cwd=app)

    assert result.returncode == 65
    assert "X.Y.Z" in result.stderr


def test_run_aceita_offline_e_cache_dir(tmp_path: Path) -> None:
    app, _dep = _project(tmp_path)
    _cli("lock", cwd=app)

    result = _run(
        app / "main.lx",
        "run",
        "--offline",
        "--cache-dir",
        str(tmp_path / "cache"),
        cwd=app,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "42\n"


def test_erro_de_dependencia_em_json_tem_codigo_e_fase(tmp_path: Path) -> None:
    app, dep = _project(tmp_path)
    _cli("lock", cwd=app)
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n }\n", encoding="utf-8")

    result = _run(app / "main.lx", "run", "--frozen", "--json", cwd=app)

    assert result.returncode == 65
    payload = json.loads(result.stderr)
    assert payload["diagnostics"][0]["code"] == "C0002"
    assert payload["diagnostics"][0]["phase"] == "cli"
