# SPDX-License-Identifier: MIT OR Apache-2.0
"""Snapshot do THIR: cobertura do manifesto e forma dos hashes.

O hash de cada caso é conferido no teste de corpus (`tests/test_thir.py`), que já constrói
o módulo; aqui só se garante que o manifesto cobre exatamente o corpus declarado.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.corpus_manifest import LEVELS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "thir" / "manifest.json"


def _cases() -> dict[str, object]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    cases = payload["cases"]
    assert isinstance(cases, dict)
    return cases


def test_manifest_covers_the_declared_corpus() -> None:
    declared = {case for level in LEVELS.values() for case in level}
    assert set(_cases()) == declared, (
        "snapshot do THIR fora de sincronia com LEVELS; rode `make thir-snapshot`"
    )


def test_every_hash_is_a_sha256() -> None:
    for case, digest in _cases().items():
        assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), case
