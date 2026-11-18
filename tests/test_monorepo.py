# SPDX-License-Identifier: MIT OR Apache-2.0
"""Monorepo real em `examples/monorepo`: `path` + lock, nos dois motores (ADR-0100/0104)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
MONOREPO = ROOT / "examples" / "monorepo"
ENTRY = MONOREPO / "app" / "main.lx"


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_monorepo_exemplo_roda_frozen_e_lock_esta_em_dia() -> None:
    checked = _run("lock", "--check", cwd=MONOREPO)
    frozen = _run("run", "--frozen", str(ENTRY))

    assert checked.returncode == 0, checked.stderr
    assert frozen.returncode == 0, frozen.stderr
    assert frozen.stdout == "42\n"


def test_monorepo_exemplo_passa_no_check_com_frozen() -> None:
    result = _run("check", "--frozen", str(ENTRY))

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
