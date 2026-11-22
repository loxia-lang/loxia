# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repository_config() -> Path | None:
    """`.git/config` do repositório real (comum entre worktrees), se existir."""
    from loxia_core.loader.gitenv import git_env

    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=git_env(),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = ROOT / common
    config = common / "config"
    return config if config.is_file() else None


@pytest.fixture(scope="session", autouse=True)
def _repository_config_guard() -> Iterator[None]:
    """Falha a suíte se um teste escrever no `.git/config` do projeto.

    O vetor é `git` herdar `GIT_DIR`/`GIT_WORK_TREE` do hook do pre-commit; os helpers
    usam `git_env()` para descartar essas variáveis, e esta guarda pega uma regressão.
    """
    config = _repository_config()
    before = config.read_bytes() if config is not None else None
    yield
    if config is None or before is None:
        return
    after = config.read_bytes() if config.is_file() else None
    if after != before:
        pytest.fail(
            "the test suite modified the repository's .git/config; "
            "make sure every git subprocess uses loxia_core.loader.gitenv.git_env()."
        )


@pytest.fixture(scope="session")
def regex_build_cache(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Cache do build Rust compartilhado entre testes (a chave é o conteúdo).

    O crate leva ~14 s para compilar; sem isso cada teste com regex pagaria o build
    de novo. O cache é content-addressed, então compartilhar não esconde regressão.
    """
    return str(tmp_path_factory.mktemp("regex-build-cache"))
