from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def relative_targets(text: str) -> list[str]:
    targets: list[str] = []

    for raw in LINK.findall(text):
        target = raw.strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue

        target = target.split("#", 1)[0]
        if target:
            targets.append(target)

    return targets


def test_docs_links_point_to_existing_files() -> None:
    broken: list[str] = []

    for doc in DOCS:
        for target in relative_targets(doc.read_text(encoding="utf-8")):
            if not (doc.parent / target).resolve().exists():
                broken.append(f"{doc.relative_to(ROOT)} -> {target}")

    assert broken == [], "links quebrados:\n" + "\n".join(broken)
