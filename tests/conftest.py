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
    Seções `[branch ...]` não contam: `git push -u`/`git branch --track` e o editor as
    escrevem durante o trabalho normal, inclusive no meio de um gate.
    """
    from tests.git_config import stable_config

    config = _repository_config()
    before = stable_config(config.read_text(encoding="utf-8")) if config is not None else None
    yield
    if config is None or before is None:
        return
    after = stable_config(config.read_text(encoding="utf-8")) if config.is_file() else None
    if after != before:
        pytest.fail(
            "the test suite modified the repository's .git/config; "
            "make sure every git subprocess uses loxia_core.loader.gitenv.git_env()."
        )


@pytest.fixture(scope="session")
def regex_build_cache() -> str:
    """Cache persistente do build Rust, o mesmo que o produto usa (ADR-0131).

    O crate leva dezenas de segundos para compilar. Um `tmp_path` por sessão
    obrigava a um build a frio em todo `make check`/`make test-fast`; a chave já
    cobre fontes e toolchain, então reusar o cache do produto não esconde
    regressão e elimina o rebuild entre execuções.
    """
    from loxia_core.native_build import cache_base

    return str(cache_base())
