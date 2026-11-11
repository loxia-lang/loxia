from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from lox import __version__

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_version_matches_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == __version__


def test_cli_version() -> None:
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == f"pylox {__version__}"


def test_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "lox", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == f"pylox {__version__}"


def test_dump_ast_prints_and_does_not_execute(tmp_path: Path) -> None:
    script = tmp_path / "programa.lox"
    script.write_text("print 1 + 2;\n", encoding="utf-8")

    result = run_cli("--dump-ast", str(script))

    assert result.returncode == 0
    assert result.stdout.strip() == "(print (+ 1 2))"


def test_dump_ast_syntax_error_exits_65(tmp_path: Path) -> None:
    script = tmp_path / "quebrado.lox"
    script.write_text("print 1 + ;\n", encoding="utf-8")

    result = run_cli("--dump-ast", str(script))

    assert result.returncode == 65


def test_dump_ast_requires_script() -> None:
    result = run_cli("--dump-ast")

    assert result.returncode == 2
