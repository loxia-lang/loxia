# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run the complete `lox` snippets marked with `<!-- run -->` in Learn and Cookbook."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEARN = ROOT / "docs" / "i18n" / "en" / "learn"
COOKBOOK = ROOT / "docs" / "i18n" / "en" / "cookbook"
RUNNABLE = re.compile(r"<!-- run -->\s*```lox\n(.*?)```", re.S)


def test_learn_snippets_run(tmp_path: Path) -> None:
    snippets: list[tuple[Path, str]] = []
    for root in (LEARN, COOKBOOK):
        for page in sorted(root.glob("*.md")):
            text = page.read_text(encoding="utf-8")
            snippets.extend((page, match.group(1)) for match in RUNNABLE.finditer(text))

    assert snippets, "no <!-- run --> lox snippets found in docs/i18n/en/{learn,cookbook}"

    for index, (page, source) in enumerate(snippets):
        path = tmp_path / f"learn_{index}.lx"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{page.name}: {result.stderr}\n{source}"
