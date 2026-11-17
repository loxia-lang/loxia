# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Site sources use site-relative links (`docs/i18n`, `docs/versions`); the Starlight
# build and its link checker validate those, not the repository-file link test.
SITE_SOURCES = (ROOT / "docs" / "i18n", ROOT / "docs" / "versions")
DOCS = [
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / "SECURITY.md",
    *sorted(
        path
        for path in (ROOT / "docs").rglob("*.md")
        if not any(path.is_relative_to(prefix) for prefix in SITE_SOURCES)
    ),
]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def relative_targets(text: str) -> list[str]:
    targets: list[str] = []

    # Links dentro de código (assinaturas com `[T]`, exemplos) não são links.
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)

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
