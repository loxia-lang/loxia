"""`loxia fix`: só `safe`, dry-run/apply, idempotência e unsafe preservado."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

UNUSED = """fn f() -> Int {
  val unused = 1
  return 41 + 1
}
print(f())
"""

TYPO = """fn f() -> Nil {
  val unused = 1
  prin("x")
}
"""


def run_fix(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loxia", "fix", str(path), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_program(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loxia", "run", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_dry_run_nao_escreve(tmp_path: Path) -> None:
    path = tmp_path / "unused.lx"
    path.write_text(UNUSED, encoding="utf-8")
    result = run_fix(path)
    assert result.returncode == 0, result.stderr
    assert "aplicaria" in result.stdout
    assert path.read_text(encoding="utf-8") == UNUSED


def test_apply_renomeia_e_preserva_comportamento(tmp_path: Path) -> None:
    path = tmp_path / "unused.lx"
    path.write_text(UNUSED, encoding="utf-8")
    before = run_program(path)
    result = run_fix(path, "--apply")
    assert result.returncode == 0, result.stderr
    fixed = path.read_text(encoding="utf-8")
    assert "val _unused_" in fixed
    assert "val unused" not in fixed
    after = run_program(path)
    assert after.stdout == before.stdout
    again = run_fix(path, "--apply", "--json")
    payload = json.loads(again.stdout)
    assert payload["applied"] == 0


def test_unsafe_nao_e_aplicado(tmp_path: Path) -> None:
    path = tmp_path / "typo.lx"
    path.write_text(TYPO, encoding="utf-8")
    result = run_fix(path, "--apply")
    assert result.returncode == 1
    assert "unsafe" in result.stderr
    fixed = path.read_text(encoding="utf-8")
    assert 'prin("x")' in fixed
    assert "val _unused_" in fixed


def test_json_resume(tmp_path: Path) -> None:
    path = tmp_path / "unused.lx"
    path.write_text(UNUSED, encoding="utf-8")
    result = run_fix(path, "--apply", "--json")
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["applied"] == 1
    assert payload["remaining_errors"] == 0
