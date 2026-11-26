# SPDX-License-Identifier: MIT OR Apache-2.0
"""Normalização do `.git/config` usada pela guarda da suíte (`tests/conftest.py`).

A guarda compara o config antes e depois da sessão para pegar vazamento de
`GIT_DIR`/`GIT_WORK_TREE` (um teste que escreve identidade ou remote no repositório
real). Seções `[branch ...]` ficam de fora: `git push -u`, `git branch --track` e o
VS Code escrevem `remote`/`merge`/`vscode-merge-base` ali durante o trabalho normal —
inclusive no meio de um gate — e isso não é vazamento de teste.
"""

from __future__ import annotations


def stable_config(text: str) -> str:
    """Config normalizado, sem as seções `[branch ...]` (e suas chaves)."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            skipping = stripped.startswith("[branch ")
        if stripped and not skipping:
            kept.append(stripped)
    return "\n".join(kept)
