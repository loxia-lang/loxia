# SPDX-License-Identifier: MIT OR Apache-2.0
"""The README code sample must keep running and printing the documented output."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SAMPLE = re.compile(r"<!-- readme-sample -->\s*```lox\n(.*?)```", re.S)


def test_readme_sample_runs(tmp_path: Path) -> None:
    match = SAMPLE.search(README.read_text(encoding="utf-8"))
    assert match is not None, "README is missing the <!-- readme-sample --> fenced block"

    source = tmp_path / "readme_sample.lx"
    source.write_text(match.group(1), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--interpret", str(source)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "area = 12.56636\narea = 6.0\n"
