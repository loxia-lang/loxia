# SPDX-License-Identifier: MIT OR Apache-2.0
"""Diretiva `# requires:` do runner golden (ADR-0131)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import runner


def _case(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "caso.lx"
    path.write_text(body, encoding="utf-8")
    return path


def test_requires_directive_is_parsed(tmp_path: Path) -> None:
    assert runner.requirements("# requires: rust\nprint(1)\n") == {"rust"}
    assert runner.requirements("#requires:rust\n") == {"rust"}
    assert runner.requirements("print(1)\n") == set()


def test_missing_requirements_skips_without_cargo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("loxia_core.native_build.cargo_binary", lambda: None)

    assert runner.missing_requirements(_case(tmp_path, "# requires: rust\n")) == {"rust"}


def test_missing_requirements_runs_with_cargo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("loxia_core.native_build.cargo_binary", lambda: "/usr/bin/cargo")

    assert runner.missing_requirements(_case(tmp_path, "# requires: rust\n")) == set()


def test_timeout_follows_the_requirement() -> None:
    assert runner.timeout_for("# requires: rust\nprint(1)\n") == 180
    assert runner.timeout_for("print(1)\n") == 20


def test_malformed_requirement_fails_loudly() -> None:
    with pytest.raises(ValueError, match="malformed"):
        runner.requirements("# Requires: rust\n")


def test_requirement_must_be_in_the_header_block() -> None:
    # Diretiva no fim de uma linha de código não conta (o bloco é o do topo).
    assert runner.requirements("print(1) # requires: rust\n") == set()


def test_unknown_requirement_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="gpu"):
        runner.missing_requirements(_case(tmp_path, "# requires: gpu\n"))
