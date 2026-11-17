# SPDX-License-Identifier: MIT OR Apache-2.0
"""Licença dual MIT/Apache-2.0 (ADR-0101)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]


def _project() -> dict[str, Any]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return cast(dict[str, Any], data["project"])


def test_license_files_exist() -> None:
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "NOTICE"):
        path = ROOT / name
        assert path.is_file(), f"{name} missing"
        assert path.read_text(encoding="utf-8").strip(), f"{name} empty"

    assert not (ROOT / "LICENSE").exists(), (
        "root LICENSE would contradict the dual offer; use LICENSE-MIT/LICENSE-APACHE"
    )


def test_apache_text_is_the_real_license() -> None:
    text = (ROOT / "LICENSE-APACHE").read_text(encoding="utf-8")
    assert text.strip().startswith("Apache License")
    assert "Version 2.0, January 2004" in text
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in text


def test_pyproject_declares_spdx_expression() -> None:
    project = _project()
    assert project["license"] == "MIT OR Apache-2.0"
    assert set(project["license-files"]) == {"LICENSE-MIT", "LICENSE-APACHE"}


def test_sdist_ships_license_and_notice() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = set(data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "NOTICE"):
        assert name in include, f"{name} missing from sdist"


def test_readme_documents_the_choice() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "MIT OR Apache-2.0" in readme
    assert "LICENSE-MIT" in readme
    assert "LICENSE-APACHE" in readme
    assert "at your option" in readme
