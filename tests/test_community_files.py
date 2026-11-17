# SPDX-License-Identifier: MIT OR Apache-2.0
"""Community health files exist and keep their required promises."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_health_files_exist() -> None:
    for name in ("CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md"):
        path = ROOT / name
        assert path.is_file(), f"{name} missing"
        assert path.read_text(encoding="utf-8").strip(), f"{name} empty"


def test_code_of_conduct_uses_github_only_reporting() -> None:
    text = _text("CODE_OF_CONDUCT.md")
    assert "Contributor Covenant" in text
    assert "Report a vulnerability" in text
    assert "[conduct]" in text
    assert "INSERT CONTACT METHOD" not in text
    assert "@" not in text.split("## Enforcement", 1)[1].split("## Enforcement Guidelines", 1)[0]


def test_contributing_documents_license_and_dco() -> None:
    text = _text("CONTRIBUTING.md")
    assert "MIT OR Apache-2.0" in text
    assert "inbound = outbound" in text
    assert "Signed-off-by" in text
    assert "Conventional Commits" in text


def test_security_documents_private_reporting() -> None:
    text = _text("SECURITY.md")
    assert "Report a vulnerability" in text
    assert "security/advisories/new" in text
    assert "[conduct]" in text
    assert "email" in text.lower()
