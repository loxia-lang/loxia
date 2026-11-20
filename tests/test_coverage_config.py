# SPDX-License-Identifier: MIT OR Apache-2.0
"""Guardas da configuração de cobertura Python (`make coverage`)."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _coverage() -> dict[str, object]:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return payload["tool"]["coverage"]  # type: ignore[no-any-return]


def test_coverage_measures_branches_and_subprocesses() -> None:
    config = _coverage()
    run = config["run"]
    assert isinstance(run, dict)
    assert run["branch"] is True
    assert "subprocess" in run["patch"]
    assert run["source"] == ["loxia", "loxia_core"]
    assert run["parallel"] is True


def test_coverage_artifacts_are_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".coverage" in ignored
    assert ".coverage.*" in ignored
    assert "htmlcov/" in ignored


def test_make_target_exists() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "\ncoverage:\n" in makefile
    assert "coverage report" in makefile
