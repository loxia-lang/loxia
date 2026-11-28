# SPDX-License-Identifier: MIT OR Apache-2.0
"""Gate da migração THIR: o `.ll` do lowering não pode mudar um byte.

A fatia 3 da F2 troca a árvore que o lowering consome (AST → THIR). O contrato é que isso
é **só** troca de fronteira: mesmo programa, mesmo `.ll`. O manifesto
`tests/ll/manifest.json` foi congelado antes da migração; qualquer byte diferente aqui é
mudança de codegen disfarçada de refactor.

Atualizar o manifesto é decisão consciente e de outra fatia (não desta): o diff de hash
é a revisão.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from tests.corpus_manifest import LEVELS
from tests.inprocess import run_cli

pytestmark = [pytest.mark.backend]
if importlib.util.find_spec("llvmlite") is None:
    pytestmark.append(
        pytest.mark.skip(reason="llvmlite não instalado; rode `uv sync --extra llvm`")
    )

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "ll" / "manifest.json"


def _cases() -> dict[str, str]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    cases = payload["cases"]
    assert isinstance(cases, dict)
    return {str(case): str(digest) for case, digest in cases.items()}


def _corpus() -> list[str]:
    return sorted({case for level in LEVELS.values() for case in level})


def test_manifest_covers_the_declared_corpus() -> None:
    assert set(_cases()) == set(_corpus()), (
        "manifesto do lowering fora de sincronia com LEVELS; rode `make ll-snapshot`"
    )


@pytest.mark.parametrize("case", _corpus(), ids=lambda case: Path(case).stem)
def test_ll_bytes_are_unchanged(case: str) -> None:
    expected = _cases()[case]
    result = run_cli("build", case, "--emit=ll")
    assert result.returncode == 0, result.stderr
    digest = hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()
    assert digest == expected, (
        f"{case}: o `.ll` mudou. A migração para o THIR não pode alterar codegen; "
        "se a mudança é intencional (outra fatia), rode `make ll-snapshot` e revise o diff"
    )
