# SPDX-License-Identifier: MIT OR Apache-2.0
"""`loxia new`/`loxia init`: scaffold mínimo, nome, git e erros (ADR-0106)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

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


def _manifest(project: Path) -> dict[str, object]:
    return tomllib.loads((project / "loxia.toml").read_text(encoding="utf-8"))


def test_new_cria_template_minimo_e_roda(tmp_path: Path) -> None:
    created = _cli("new", "app", cwd=tmp_path)
    project = tmp_path / "app"

    assert created.returncode == 0, created.stderr
    assert created.stdout == "Created project 'app' at 'app'.\n"
    assert (project / "loxia.toml").is_file()
    assert (project / "loxia.lock").is_file()
    assert (project / ".gitignore").read_text(encoding="utf-8") == ".loxia/\ndist/\n"
    assert (project / "src" / "main.lx").read_text(encoding="utf-8") == 'print("hello from app")\n'
    package = _manifest(project)["package"]
    assert isinstance(package, dict)
    assert package == {"name": "app", "version": "0.1.0"}
    assert tomllib.loads((project / "loxia.lock").read_text(encoding="utf-8"))["version"] == 1

    run = _cli("run", str(project / "src" / "main.lx"), cwd=tmp_path)
    check = _cli("check", "--frozen", str(project / "src" / "main.lx"), cwd=tmp_path)
    lock = _cli("lock", "--check", cwd=project)

    assert run.returncode == 0, run.stderr
    assert run.stdout == "hello from app\n"
    assert check.returncode == 0, check.stderr
    assert lock.returncode == 0, lock.stderr


def test_new_nao_sobrescreve_diretorio_existente(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()

    result = _cli("new", "app", cwd=tmp_path)

    assert result.returncode == 65
    assert "error[C0003]" in result.stderr
    assert "Destination already exists" in result.stderr


def test_new_normaliza_o_nome_do_diretorio(tmp_path: Path) -> None:
    created = _cli("new", "my-app", cwd=tmp_path)

    assert created.returncode == 0, created.stderr
    assert created.stdout == "Created project 'my_app' at 'my-app'.\n"
    package = _manifest(tmp_path / "my-app")["package"]
    assert isinstance(package, dict)
    assert package["name"] == "my_app"
    assert 'print("hello from my_app")' in (tmp_path / "my-app" / "src" / "main.lx").read_text()


def test_new_aceita_name_e_recusa_name_invalido(tmp_path: Path) -> None:
    created = _cli("new", "app", "--name", "core", cwd=tmp_path)
    assert created.returncode == 0, created.stderr
    package = _manifest(tmp_path / "app")["package"]
    assert isinstance(package, dict)
    assert package["name"] == "core"

    invalid = _cli("new", "outro", "--name", "1x", cwd=tmp_path)
    assert invalid.returncode == 2
    assert "Invalid project name" in invalid.stderr
    assert not (tmp_path / "outro").exists()


def test_new_cria_diretorios_intermediarios(tmp_path: Path) -> None:
    created = _cli("new", "tools/app", cwd=tmp_path)

    assert created.returncode == 0, created.stderr
    assert (tmp_path / "tools" / "app" / "loxia.toml").is_file()


def test_new_em_json(tmp_path: Path) -> None:
    created = _cli("new", "app", "--json", cwd=tmp_path)

    assert created.returncode == 0, created.stderr
    payload = json.loads(created.stdout)
    assert payload["path"] == "app"
    assert payload["name"] == "app"
    assert payload["files"] == ["loxia.toml", "src/main.lx", ".gitignore", "loxia.lock"]
    assert payload["git"] is (tmp_path / "app" / ".git").exists()


@_GIT_REQUIRED
def test_new_inicializa_git_por_padrao(tmp_path: Path) -> None:
    assert _cli("new", "app", cwd=tmp_path).returncode == 0

    assert (tmp_path / "app" / ".git").exists()


@_GIT_REQUIRED
def test_new_com_no_git_nao_inicializa_repositorio(tmp_path: Path) -> None:
    created = _cli("new", "app", "--no-git", cwd=tmp_path)

    assert created.returncode == 0, created.stderr
    assert not (tmp_path / "app" / ".git").exists()


def test_init_em_diretorio_existente_preserva_arquivos(tmp_path: Path) -> None:
    project = tmp_path / "existing"
    project.mkdir()
    (project / "notes.txt").write_text("keep me\n", encoding="utf-8")

    created = _cli("init", cwd=project)

    assert created.returncode == 0, created.stderr
    assert created.stdout == "Initialized project 'existing' at '.'.\n"
    assert (project / "notes.txt").read_text(encoding="utf-8") == "keep me\n"
    assert (project / "src" / "main.lx").is_file()
    assert (project / "loxia.lock").is_file()


def test_init_recusa_projeto_existente(tmp_path: Path) -> None:
    project = tmp_path / "existing"
    project.mkdir()
    (project / "loxia.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")

    result = _cli("init", cwd=project)

    assert result.returncode == 65
    assert "already contains 'loxia.toml'" in result.stderr


@_GIT_REQUIRED
def test_init_nao_cria_repositorio_aninhado(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=60, env=git_env())
    project = tmp_path / "sub"
    project.mkdir()

    created = _cli("init", cwd=project)

    assert created.returncode == 0, created.stderr
    assert not (project / ".git").exists()


def test_new_falha_sem_git_quando_nao_pediu_no_git(tmp_path: Path) -> None:
    result = _cli("new", "app", cwd=tmp_path, env={"PATH": ""})

    assert result.returncode == 65
    assert "git was not found" in result.stderr
    assert not (tmp_path / "app").exists()


def test_new_e_deterministico(tmp_path: Path) -> None:
    first = tmp_path / "um" / "app"
    second = tmp_path / "dois" / "app"
    assert _cli("new", str(first), "--name", "app", cwd=tmp_path).returncode == 0
    assert _cli("new", str(second), "--name", "app", cwd=tmp_path).returncode == 0

    for relative in ("loxia.toml", "src/main.lx", ".gitignore", "loxia.lock"):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_erro_de_scaffold_em_json(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()

    result = _cli("new", "app", "--json", cwd=tmp_path)

    assert result.returncode == 65
    payload = json.loads(result.stderr)
    assert payload["diagnostics"][0]["code"] == "C0003"
    assert payload["diagnostics"][0]["phase"] == "cli"
