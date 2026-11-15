from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "exemplos"
ENTRYPOINT = ROOT / "main.py"


def test_examples_run_without_errors() -> None:
    paths = sorted(EXAMPLES.glob("*.lx"))

    assert len(paths) >= 5

    for path in paths:
        result = subprocess.run(
            [sys.executable, str(ENTRYPOINT), str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

        assert result.returncode == 0, f"{path.name} falhou: {result.stderr}"
        assert result.stdout.strip(), f"{path.name} não imprimiu nada"
