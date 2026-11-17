# SPDX-License-Identifier: MIT OR Apache-2.0
"""GitHub Actions supply-chain hygiene: pinned actions and explicit permissions."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+@[0-9a-f]{40}$")


def test_actions_are_pinned_to_a_commit() -> None:
    unpinned: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith(("- uses:", "uses:")):
                continue
            target = stripped.split("uses:", 1)[1].split("#", 1)[0].strip()
            if target.startswith("./"):
                continue
            if not PINNED.match(target):
                unpinned.append(f"{path.name}:{number}: {target}")

    assert unpinned == [], "actions sem SHA: " + ", ".join(unpinned)


def test_workflows_declare_permissions() -> None:
    missing = [
        path.name
        for path in sorted(WORKFLOWS.glob("*.yml"))
        if "permissions:" not in path.read_text(encoding="utf-8")
    ]
    assert missing == [], "workflows sem permissions: " + ", ".join(missing)
