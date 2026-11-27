# SPDX-License-Identifier: MIT OR Apache-2.0
"""Módulo `regex` (bundled): resolução, API e CLI (ADR-0131)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from loxia_core.native_build import cargo_binary

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"

pytestmark = pytest.mark.skipif(
    cargo_binary() is None, reason="Rust toolchain (cargo) is not available"
)


def _run(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(script)],
        cwd=script.parent,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_module_api_through_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, regex_build_cache: str
) -> None:
    monkeypatch.setenv("LOX_BUILD_CACHE", regex_build_cache)
    script = tmp_path / "uso.lx"
    script.write_text(
        r"""
import regex

val words = regex.tryCompile("\\p{L}+")
if (words != nil) {
  for word in words.findAll("café ☕ 123") {
    print(word.text)
  }
  print(words.replaceAll("a1 b2", "<$0>"))
  words.close()
}
val named = regex.tryCompile("(?P<a>[a-z]+)-(?P<b>[0-9]+)")
if (named != nil) {
  print(named.replaceAll("x-1 y-2", "$b/$a"))
  print(named.replace("x-1", "\${b}:\${a}"))
  named.close()
}
print(regex.tryCompile("("))
val bad = regex.compile("(")
print(match bad {
  Result.Ok(_) => "ok"
  Result.Err(error) => error.kind
})
""".lstrip(),
        encoding="utf-8",
    )

    result = _run(script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "café\n<a>1 <b>2\n1/x 2/y\n1:x\nnil\nsyntax\n"


def test_bundled_name_wins_over_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, regex_build_cache: str
) -> None:
    monkeypatch.setenv("LOX_BUILD_CACHE", regex_build_cache)
    (tmp_path / "regex.lx").write_text("fn local() -> Int { return 1 }\n", encoding="utf-8")
    script = tmp_path / "principal.lx"
    script.write_text('import regex\nprint(regex.tryCompile("a") != nil)\n', encoding="utf-8")

    result = _run(script)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "true\n"
