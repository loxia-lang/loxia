# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ambiente limpo para os `git` que o Loxia dispara (produto e testes).

`git` exporta `GIT_DIR`/`GIT_WORK_TREE`/... para os hooks. Quando a suíte roda dentro do
hook do pre-commit (ou `loxia lock` roda num hook), um `git config`/`git clone` cru herda
esse ambiente e escreve no repositório **real** em vez do temporário — foi assim que
`user.email = test@example.com` e `core.bare = true` vazaram para o `.git/config` do
projeto.

`git_env()` devolve uma cópia do ambiente sem as variáveis que redirecionam o repositório,
com `GIT_TERMINAL_PROMPT=0` (nenhum comando pede credencial) e sem mutar `os.environ`.
"""

from __future__ import annotations

import os

# Variáveis que apontam o git para outro repositório/índice/config. Herdá-las faz o
# comando operar no repositório errado.
_DROPPED = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_CEILING_DIRECTORIES",
    }
)
_DROPPED_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Ambiente para subprocessos `git`: sem redirecionamento de repositório."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _DROPPED and not key.startswith(_DROPPED_PREFIXES)
    }
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra:
        env.update(extra)
    return env
