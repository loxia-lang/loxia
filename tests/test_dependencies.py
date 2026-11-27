# SPDX-License-Identifier: MIT OR Apache-2.0
"""Lock, hash e modo `--frozen` das dependências `path` (ADR-0104)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast

import pytest

from loxia_core.loader.gitenv import git_env

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
_GIT_REQUIRED = pytest.mark.skipif(shutil.which("git") is None, reason="git não está no PATH")


def _cli(
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
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
    digest = package["sha256"]
    assert isinstance(digest, str)
    assert len(digest) == 64
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


# -- git (fase 2, ADR-0105) ----------------------------------------------


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
        env=git_env(),
    ).stdout.strip()


def _git_repository(
    tmp_path: Path,
    *,
    tag: str | None = None,
    version: str | None = "0.1.0",
) -> tuple[Path, str]:
    repo = tmp_path / "remote"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    manifest = '[package]\nname = "acme"\n'
    if version is not None:
        manifest += f'version = "{version}"\n'
    (repo / "loxia.toml").write_text(manifest, encoding="utf-8")
    (repo / "base.lx").write_text(
        "fn dobro(n: Int) -> Int { return n * 2 }\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    if tag is not None:
        _git("tag", tag, cwd=repo)
    return repo, _git("rev-parse", "HEAD", cwd=repo)


def _git_app(tmp_path: Path, repo: Path, rev: str) -> Path:
    app = tmp_path / "app"
    app.mkdir()
    (app / "loxia.toml").write_text(
        '[package]\nname = "app"\n\n'
        f'[dependencies]\nacme = {{ git = "{repo.as_uri()}", rev = "{rev}" }}\n',
        encoding="utf-8",
    )
    (app / "main.lx").write_text(
        "import acme.base as base\nprint(base.dobro(21))\n",
        encoding="utf-8",
    )
    return app


def _git_lock(app: Path) -> dict[str, object]:
    lock = tomllib.loads((app / "loxia.lock").read_text(encoding="utf-8"))
    packages = lock["package"]
    assert isinstance(packages, list)
    (package,) = packages
    return cast("dict[str, object]", package)


@_GIT_REQUIRED
def test_git_com_sha_trava_commit_e_roda(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path)
    app = _git_app(tmp_path, repo, sha)

    locked = _cli("lock", cwd=app)

    assert locked.returncode == 0, locked.stderr
    package = _git_lock(app)
    assert package["git"] == repo.as_uri()
    assert package["rev"] == sha
    assert package["commit"] == sha
    assert package["version"] == "0.1.0"
    digest = package["sha256"]
    assert isinstance(digest, str)
    assert len(digest) == 64

    run = _run(app / "main.lx", "run", cwd=app)
    frozen = _run(app / "main.lx", "run", "--frozen", cwd=app)
    assert run.stdout == "42\n"
    assert frozen.returncode == 0, frozen.stderr
    assert frozen.stdout == "42\n"


@_GIT_REQUIRED
def test_git_com_tag_resolve_para_o_commit(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path, tag="v0.1.0")
    app = _git_app(tmp_path, repo, "v0.1.0")

    assert _cli("lock", cwd=app).returncode == 0
    package = _git_lock(app)

    assert package["rev"] == "v0.1.0"
    assert package["commit"] == sha
    assert _run(app / "main.lx", "run", "--frozen", cwd=app).stdout == "42\n"


@_GIT_REQUIRED
def test_git_sem_checkout_pede_fetch_e_depois_funciona(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path)
    app = _git_app(tmp_path, repo, sha)
    assert _cli("lock", cwd=app).returncode == 0
    shutil.rmtree(app / ".loxia" / "cache" / "src")

    missing = _run(app / "main.lx", "run", cwd=app)
    fetched = _cli("fetch", cwd=app)
    run = _run(app / "main.lx", "run", cwd=app)

    assert missing.returncode == 65
    assert "not available locally" in missing.stderr
    assert fetched.returncode == 0, fetched.stderr
    assert run.stdout == "42\n"


@_GIT_REQUIRED
def test_git_offline_usa_o_cache_mesmo_sem_remoto(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path)
    app = _git_app(tmp_path, repo, sha)
    assert _cli("lock", cwd=app).returncode == 0
    assert _cli("fetch", cwd=app).returncode == 0
    shutil.rmtree(repo)

    offline = _run(app / "main.lx", "run", "--offline", cwd=app)
    frozen = _run(app / "main.lx", "run", "--frozen", cwd=app)
    relocked = _cli("lock", "--offline", cwd=app)
    fetched = _cli("fetch", "--offline", cwd=app)

    assert offline.stdout == "42\n"
    assert frozen.stdout == "42\n"
    assert relocked.returncode == 0, relocked.stderr
    assert fetched.returncode == 0, fetched.stderr


@_GIT_REQUIRED
def test_git_offline_sem_cache_falha(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path)
    app = _git_app(tmp_path, repo, sha)
    assert _cli("lock", cwd=app).returncode == 0
    shutil.rmtree(app / ".loxia")

    result = _cli("fetch", "--offline", cwd=app)

    assert result.returncode == 65
    assert "not in the cache" in result.stderr


@_GIT_REQUIRED
def test_git_frozen_detecta_rev_trocada(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path)
    app = _git_app(tmp_path, repo, sha)
    assert _cli("lock", cwd=app).returncode == 0
    (repo / "base.lx").write_text(
        "fn dobro(n: Int) -> Int { return n * 3 }\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "segundo", cwd=repo)
    second = _git("rev-parse", "HEAD", cwd=repo)
    (app / "loxia.toml").write_text(
        '[package]\nname = "app"\n\n'
        f'[dependencies]\nacme = {{ git = "{repo.as_uri()}", rev = "{second}" }}\n',
        encoding="utf-8",
    )

    result = _run(app / "main.lx", "run", "--frozen", cwd=app)

    assert result.returncode == 65
    assert "changed since loxia.lock" in result.stderr


@_GIT_REQUIRED
def test_git_exige_version_no_manifest_da_dependencia(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path, version=None)
    app = _git_app(tmp_path, repo, sha)

    result = _cli("lock", cwd=app)

    assert result.returncode == 65
    assert "needs [package].version" in result.stderr


@_GIT_REQUIRED
def test_git_rev_inexistente_falha_no_lock(tmp_path: Path) -> None:
    repo, _sha = _git_repository(tmp_path)
    app = _git_app(tmp_path, repo, "0" * 40)

    result = _cli("lock", cwd=app)

    assert result.returncode == 65
    assert "Can't resolve rev" in result.stderr


@_GIT_REQUIRED
def test_git_sem_git_no_path_falha_com_mensagem_clara(tmp_path: Path) -> None:
    repo, sha = _git_repository(tmp_path)
    app = _git_app(tmp_path, repo, sha)

    result = _cli("lock", cwd=app, env={"PATH": ""})

    assert result.returncode == 65
    assert "git was not found" in result.stderr


@pytest.mark.parametrize(
    ("spec", "needle"),
    [
        (
            '{ git = "ext::sh -c true", rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }',
            "URL",
        ),
        ('{ git = "file:///tmp/acme", rev = "-x" }', "full commit SHA or a tag name"),
        ('{ path = ".", git = "file:///tmp/acme", rev = "abc" }', "exactly one"),
        ('{ git = "file:///tmp/acme" }', "needs a 'rev'"),
        ('{ path = ".", rev = "abc" }', "'rev' is only valid"),
        (
            '{ git = "https://example.com/acme", rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", branch = "main" }',
            "Unsupported key",
        ),
    ],
)
def test_git_manifest_invalido(spec: str, needle: str, tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "loxia.toml").write_text(
        f'[package]\nname = "app"\n\n[dependencies]\nacme = {spec}\n',
        encoding="utf-8",
    )
    (app / "main.lx").write_text("print(1)\n", encoding="utf-8")

    result = _cli("lock", cwd=app)

    assert result.returncode == 65
    assert needle in result.stderr


# -- loxia add / remove (ADR-0118) ------------------------------------------


def _app_sem_dependencias(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    app.mkdir()
    (app / "loxia.toml").write_text(
        '# comentário do dono\n[package]\nname = "app"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    return app


def _pacote_acme(tmp_path: Path) -> Path:
    dep = tmp_path / "acme"
    dep.mkdir()
    (dep / "loxia.toml").write_text(
        '[package]\nname = "acme"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n * 2 }\n", encoding="utf-8")
    return dep


def test_add_declara_dependencia_preservando_comentario(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)

    result = _cli("add", "acme", "--path", "../acme", cwd=app)

    assert result.returncode == 0, result.stderr
    text = (app / "loxia.toml").read_text(encoding="utf-8")
    assert "# comentário do dono" in text
    assert 'acme = { path = "../acme" }' in text
    assert _cli("lock", cwd=app).returncode == 0
    script = app / "main.lx"
    script.write_text("import acme.base as base\nprint(base.dobro(21))\n", encoding="utf-8")
    run = _run(script, "run", cwd=app)
    assert run.returncode == 0, run.stderr
    assert run.stdout == "42\n"


def test_add_e_idempotente(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)

    assert _cli("add", "acme", "--path", "../acme", cwd=app).returncode == 0
    first = (app / "loxia.toml").read_bytes()
    second = _cli("add", "acme", "--path", "../acme", cwd=app)

    assert second.returncode == 0, second.stderr
    assert "already declared" in second.stdout
    assert (app / "loxia.toml").read_bytes() == first


def test_add_spec_diferente_falha_sem_escrever(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)
    assert _cli("add", "acme", "--path", "../acme", cwd=app).returncode == 0
    before = (app / "loxia.toml").read_bytes()

    result = _cli(
        "add", "acme", "--git", "https://github.com/acme/acme", "--rev", "v1.2.3", cwd=app
    )

    assert result.returncode == 65
    assert "already declared" in result.stderr
    assert (app / "loxia.toml").read_bytes() == before


def test_add_dry_run_nao_escreve_e_mostra_diff_relativo(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)
    before = (app / "loxia.toml").read_bytes()

    result = _cli("add", "acme", "--path", "../acme", "--dry-run", cwd=app)

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("--- loxia.toml\n+++ loxia.toml\n")
    assert '+acme = { path = "../acme" }' in result.stdout
    assert str(tmp_path) not in result.stdout
    assert (app / "loxia.toml").read_bytes() == before


def test_add_json_reporta_changed(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)

    created = _cli("add", "acme", "--path", "../acme", "--json", cwd=app)
    repeated = _cli("add", "acme", "--path", "../acme", "--json", cwd=app)

    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["changed"] is True
    assert json.loads(repeated.stdout)["changed"] is False


def test_add_git_exige_rev(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)

    missing = _cli("add", "acme", "--git", "https://github.com/acme/acme", cwd=app)
    both = _cli("add", "acme", "--path", "../acme", "--git", "https://x/y", cwd=app)

    assert missing.returncode == 2
    assert both.returncode == 2


def test_add_com_lock_gera_lock(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)

    result = _cli("add", "acme", "--path", "../acme", "--lock", cwd=app)

    assert result.returncode == 0, result.stderr
    packages = _lock(app)["package"]
    assert isinstance(packages, list)
    assert packages[0]["name"] == "acme"


def test_add_recusa_forma_exotica_com_c0004(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)
    (app / "loxia.toml").write_text(
        '[package]\nname = "app"\n\n[dependencies.acme]\npath = "../acme"\n',
        encoding="utf-8",
    )
    before = (app / "loxia.toml").read_bytes()

    result = _cli("add", "beta", "--git", "https://github.com/x/y", "--rev", "v1", cwd=app)

    assert result.returncode == 65
    assert "C0004" in result.stderr
    assert (app / "loxia.toml").read_bytes() == before


def test_add_path_inexistente_falha(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)

    result = _cli("add", "acme", "--path", "../nope", cwd=app)

    assert result.returncode == 65
    assert "does not exist" in result.stderr
    assert "acme" not in (app / "loxia.toml").read_text(encoding="utf-8")


def test_remove_apaga_dependencia_e_relock(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)
    _pacote_acme(tmp_path)
    assert _cli("add", "acme", "--path", "../acme", cwd=app).returncode == 0

    removed = _cli("remove", "acme", cwd=app)

    assert removed.returncode == 0, removed.stderr
    text = (app / "loxia.toml").read_text(encoding="utf-8")
    assert "acme" not in text
    assert "# comentário do dono" in text
    assert _cli("lock", cwd=app).returncode == 0
    assert _lock(app).get("package", []) == []


def test_remove_inexistente_falha(tmp_path: Path) -> None:
    app = _app_sem_dependencias(tmp_path)

    result = _cli("remove", "acme", cwd=app)

    assert result.returncode == 65
    assert "not declared" in result.stderr


def test_watched_files_incluem_manifest_lock_e_modulos(tmp_path: Path) -> None:
    from loxia.engine import Loxia

    app, _dep = _project(tmp_path)
    result = _cli("lock", cwd=app)
    assert result.returncode == 0, result.stderr
    lox = Loxia(error_format="json", color="never", max_errors=0)
    lox.use_file("main.lx", module_root=app)

    lox.check((app / "main.lx").read_text(encoding="utf-8"), emit=False)

    # O rename/LSP usa `watched_files` como insumo de resolução: sem o lock, um
    # checkout trocado deixaria a análise (e o cache) apontando para o antigo.
    watched = {path.name for path in lox.watched_files}
    assert {"loxia.toml", "loxia.lock", "base.lx"} <= watched
