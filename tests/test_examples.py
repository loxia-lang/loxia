# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

from pathlib import Path

from tests.inprocess import run_cli

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_examples_run_without_errors() -> None:
    paths = sorted(EXAMPLES.glob("*.lx"))

    assert len(paths) >= 5

    for path in paths:
        result = run_cli(str(path))

        assert result.returncode == 0, f"{path.name} falhou: {result.stderr}"
        assert result.stdout.strip(), f"{path.name} não imprimiu nada"
