# SPDX-License-Identifier: MIT OR Apache-2.0
"""O repositório inteiro precisa estar na forma canônica do formatter (ADR-0136).

Arquivos inválidos de propósito (`tests/cases/errors/` e fixtures de diagnóstico) são
pulados: o formatter devolve `None` neles por contrato.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from loxia.formatter import format_source

ROOT = Path(__file__).resolve().parents[1]


def tracked_lx_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "*.lx"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("git is not available")
    names = result.stdout.decode("utf-8").split("\0")
    return [ROOT / name for name in names if name]


def test_tracked_lx_files_are_canonical() -> None:
    offenders: list[str] = []
    for path in tracked_lx_files():
        source = path.read_text(encoding="utf-8")
        result = format_source(source)
        if result is None:
            continue
        if result.text != source:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == [], "formatter drift; run `loxia fmt` on:\n" + "\n".join(offenders[:20])
