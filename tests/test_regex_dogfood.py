# SPDX-License-Identifier: MIT OR Apache-2.0
"""Dogfood: o check de título de PR em Loxia (ADR-0131)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from loxia_core.native_build import cargo_binary

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
TOOL = ROOT / "tools" / "check_pr_title.lx"

pytestmark = pytest.mark.skipif(
    cargo_binary() is None, reason="Rust toolchain (cargo) is not available"
)


def _run(
    title: str | None, cache: str, *, extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["LOX_BUILD_CACHE"] = cache
    environment.update(extra or {})
    arguments = [sys.executable, str(ENTRYPOINT), str(TOOL)]
    if title is not None:
        arguments.append(title)
    return subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=environment,
    )


def test_accepts_a_conventional_title(regex_build_cache: str) -> None:
    result = _run("feat(regex): add the rust engine", regex_build_cache)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_rejects_a_non_conventional_title(regex_build_cache: str) -> None:
    result = _run("nope", regex_build_cache)

    assert result.returncode == 1
    assert "expected '<type>(<scope>): <subject>'" in result.stderr


def test_reads_the_title_from_the_environment(regex_build_cache: str) -> None:
    result = _run(None, regex_build_cache, extra={"PR_TITLE": "docs: update"})

    assert result.returncode == 0, result.stderr


def test_rejects_an_unknown_type(regex_build_cache: str) -> None:
    result = _run("foo: bar", regex_build_cache)

    assert result.returncode == 1
    assert (
        "unknown type 'foo'; allowed: build, chore, ci, docs, feat, fix, perf, "
        "refactor, revert, style, test" in result.stderr
    )


def test_trims_the_subject_before_the_period_rule(regex_build_cache: str) -> None:
    result = _run("docs: update. ", regex_build_cache)

    assert result.returncode == 1
    assert "subject must not end with a period" in result.stderr
