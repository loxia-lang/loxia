# SPDX-License-Identifier: MIT OR Apache-2.0
"""Isolamento dos subprocessos `git` (produto e testes).

Um hook do pre-commit exporta `GIT_DIR`/`GIT_WORK_TREE`; herdá-los faz `git config`
escrever no `.git/config` do projeto em vez do repositório temporário do teste.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from loxia import scaffold
from loxia_core.loader import deps
from loxia_core.loader.gitenv import git_env
from tests.git_config import stable_config

GIT_REQUIRED = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True, check=False).returncode != 0,
    reason="git não está no PATH",
)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=git_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )


def test_git_env_descarta_variaveis_de_redirecionamento(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.setenv(name, "/tmp/alvo")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "user.email")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "x@y")

    env = git_env({"PATH": "/bin"})

    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        assert name not in env
    assert "GIT_CONFIG_COUNT" not in env
    assert "GIT_CONFIG_KEY_0" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["PATH"] == "/bin"
    # Não muta o processo atual.
    assert os.environ["GIT_DIR"] == "/tmp/alvo"


@GIT_REQUIRED
def test_git_config_nao_escapa_para_o_repo_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    _git("init", "-q", ".", cwd=real)
    monkeypatch.setenv("GIT_DIR", str(real / ".git"))

    target = tmp_path / "target"
    target.mkdir()
    _git("init", "-q", ".", cwd=target)
    _git("config", "user.email", "vazou@example.com", cwd=target)

    assert "vazou@example.com" not in (real / ".git" / "config").read_text(encoding="utf-8")
    assert "vazou@example.com" in (target / ".git" / "config").read_text(encoding="utf-8")


def test_stable_config_ignora_secoes_branch() -> None:
    """`git push -u`/`git branch --track` e o editor escrevem aqui no meio do gate."""
    before = (
        '[core]\n\tbare = false\n[branch "dev"]\n\tremote = origin\n'
        "\tvscode-merge-base = origin/main\n"
    )
    after = before + '[branch "chore/x"]\n\tremote = origin\n\tmerge = refs/heads/chore/x\n'
    assert stable_config(before) == stable_config(after)


def test_stable_config_ainda_pega_identidade_remote_e_core() -> None:
    assert stable_config("[core]\n\tbare = false\n") != stable_config("[core]\n\tbare = true\n")
    assert stable_config("[user]\n\temail = a@b\n") != stable_config("[user]\n\temail = c@d\n")
    assert stable_config('[remote "origin"]\n\turl = x\n') != stable_config(
        '[remote "origin"]\n\turl = y\n'
    )


def test_deps_usa_ambiente_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_DIR", "/tmp/alvo")
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(deps, "_require_git", lambda: None)
    monkeypatch.setattr(subprocess, "run", fake_run)

    deps._git_run(["status"])

    env = captured["env"]
    assert isinstance(env, dict)
    assert "GIT_DIR" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_scaffold_git_init_usa_ambiente_limpo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GIT_WORK_TREE", "/tmp/alvo")
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(subprocess, "run", fake_run)

    scaffold._git_init(tmp_path / "app")

    env = captured["env"]
    assert isinstance(env, dict)
    assert "GIT_WORK_TREE" not in env
