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


MODULE = """fn used() -> Int {
  return 1
}
fn unused() -> Int {
  return 2
}
"""


def test_w1002_remove_unused_import(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text(MODULE, encoding="utf-8")
    entry = tmp_path / "main.lx"
    entry.write_text("from mod import unused;\nprint(1)\n", encoding="utf-8")
    before = run_program(entry)
    assert before.returncode == 0
    check = subprocess.run(
        [sys.executable, "-m", "loxia", "check", "--json", str(entry)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert '"W1002"' in check.stdout
    assert '"applicability": "safe"' in check.stdout
    result = run_fix(entry, "--apply")
    assert result.returncode == 0, result.stderr
    assert "from mod import" not in entry.read_text(encoding="utf-8")
    after = run_program(entry)
    assert after.stdout == before.stdout


def test_w1002_nao_marca_uso_em_tipo(tmp_path: Path) -> None:
    module = tmp_path / "types.lx"
    module.write_text(
        "class Thing {\n  val value: Int\n  init(value: Int) { this.value = value }\n}\n",
        encoding="utf-8",
    )
    entry = tmp_path / "main.lx"
    entry.write_text(
        "from types import Thing\nval thing: Thing = Thing(1)\nprint(thing.value)\n",
        encoding="utf-8",
    )
    check = subprocess.run(
        [sys.executable, "-m", "loxia", "check", "--json", str(entry)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout
    assert '"W1002"' not in check.stdout


def test_run_nao_emite_w1002(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text(MODULE, encoding="utf-8")
    entry = tmp_path / "main.lx"
    entry.write_text("from mod import unused;\nprint(1)\n", encoding="utf-8")
    result = run_program(entry)
    assert result.returncode == 0
    assert result.stderr == ""


def test_e2002_e_e2009_nao_sao_aplicados(tmp_path: Path) -> None:
    local = tmp_path / "local.lx"
    local.write_text(
        "fn f() -> Int {\n  val x = 1\n  x = 2\n  return x\n}\n",
        encoding="utf-8",
    )
    field = tmp_path / "field.lx"
    field.write_text(
        "class C {\n  val value: Int\n  init() { this.value = 1 }\n"
        "  fn bump() -> Nil { this.value = 2 }\n}\n",
        encoding="utf-8",
    )
    for path in (local, field):
        result = run_fix(path, "--apply")
        assert result.returncode == 1
        assert "unsafe" in result.stderr
        assert "val " in path.read_text(encoding="utf-8")
