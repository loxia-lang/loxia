# SPDX-License-Identifier: MIT OR Apache-2.0
"""Conventional Commits and DCO helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import check_commit_msg, check_pr_title
from tools.check_dco import has_signoff
from tools.conventional import first_line, validate


@pytest.mark.parametrize(
    "message",
    [
        "feat(backend): lower enum payloads",
        "fix: decode stdin as strict UTF-8",
        "docs(adr): record the dual license",
        "chore(deps): bump llvmlite to 0.51",
        "feat(backend)!: change the ABI",
        "revert: feat(backend): lower enums",
        "Merge branch 'main'",
        "fixup! feat(backend): lower enums",
    ],
)
def test_valid_headers(message: str) -> None:
    assert validate(message) is None


@pytest.mark.parametrize(
    ("message", "needle"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("add a feature", "expected"),
        ("Feat(backend): lower enums", "expected"),
        ("feat(Backend): lower enums", "expected"),
        ("feat(backend): lower enums.", "period"),
        ("feat:    ", "expected"),
        ("wat: something", "unknown type"),
    ],
)
def test_invalid_headers(message: str, needle: str) -> None:
    error = validate(message)
    assert error is not None
    assert needle in error


def test_first_line_skips_comments() -> None:
    assert first_line("# comment\n\nfix(cli): keep stdout\nbody") == "fix(cli): keep stdout"


def test_commit_msg_hook(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "good"
    good.write_text("# comment\nfeat(cli): add a flag\n", encoding="utf-8")
    assert check_commit_msg.main(["check_commit_msg.py", str(good)]) == 0

    bad = tmp_path / "bad"
    bad.write_text("add a flag\n", encoding="utf-8")
    assert check_commit_msg.main(["check_commit_msg.py", str(bad)]) == 1
    assert "commit-msg" in capsys.readouterr().err


def test_pr_title_check(monkeypatch: pytest.MonkeyPatch) -> None:
    assert check_pr_title.main(["check_pr_title.py", "docs: rewrite the README"]) == 0
    assert check_pr_title.main(["check_pr_title.py", "rewrite the README"]) == 1

    monkeypatch.setenv("PR_TITLE", "ci(deps): bump actions")
    assert check_pr_title.main(["check_pr_title.py"]) == 0


def test_signoff() -> None:
    assert has_signoff("fix: x\n\nSigned-off-by: Ada <ada@example.com>")
    assert has_signoff("fix: x\n\nsigned-off-by: Ada <ada@example.com>")
    assert not has_signoff("fix: x")
    assert not has_signoff("fix: x\n\nSigned-off-by: ")
