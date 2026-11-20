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


def test_make_targets_exist() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "\ncoverage:\n" in makefile
    assert "coverage report" in makefile
    assert "\ncoverage-ratchet: coverage\n" in makefile
    assert "coverage_ratchet.py --check" in makefile


def test_ratchet_baseline_covers_existing_modules() -> None:
    from tools.coverage_ratchet import BASELINE, load_baseline

    baseline = load_baseline()
    assert BASELINE.is_file()
    assert baseline
    for path, floor in baseline.items():
        assert (ROOT / path).is_file(), path
        assert isinstance(floor, int)
        assert 0 <= floor <= 100


def test_ratchet_compare_reports_regressions() -> None:
    from tools.coverage_ratchet import compare

    actual = {
        "a.py": 95.9,
        "b.py": 80.0,
    }
    assert compare(actual, {"a.py": 95, "b.py": 80}) == []
    problems = compare(actual, {"a.py": 96, "b.py": 81, "c.py": 50})
    assert any("a.py" in problem for problem in problems)
    assert any("b.py" in problem for problem in problems)
    assert any("c.py" in problem for problem in problems)


def test_backend_ratchet_has_its_own_baseline() -> None:
    from tools.coverage_ratchet import load_baseline

    baseline = load_baseline(ROOT / "coverage-baseline-backend.toml")
    assert baseline
    for path, floor in baseline.items():
        assert path.startswith("loxia_core/backend/"), path
        assert (ROOT / path).is_file(), path
        assert 0 <= floor <= 100


def test_makefile_has_backend_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "\ncoverage-backend:\n" in makefile
    assert "\ncoverage-ratchet-backend: coverage-backend\n" in makefile
    assert "coverage-baseline-backend.toml" in makefile
