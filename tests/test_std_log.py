"""`std.log`: níveis, filtro e stderr determinístico (sem timestamp)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SOURCE = """
from std.log import Logger, Level

val log = Logger()
log.debug("ignorado")
log.info("oi")
log.warn("cuidado")
val quiet = Logger(Level.Error)
quiet.info("ignorado também")
quiet.error("falhou")
"""


def test_log_escreve_em_stderr_com_filtro(tmp_path: Path) -> None:
    path = tmp_path / "log.lx"
    path.write_text(SOURCE, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "loxia", "run", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        "[INFO] oi",
        "[WARN] cuidado",
        "[ERROR] falhou",
    ]
    assert "20" not in result.stderr


@pytest.mark.backend
def test_log_nativo(tmp_path: Path) -> None:
    path = tmp_path / "log.lx"
    path.write_text(SOURCE, encoding="utf-8")
    binary = tmp_path / "log.bin"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "loxia",
            "build",
            str(path),
            "-o",
            str(binary),
            "--emit=exe",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        "[INFO] oi",
        "[WARN] cuidado",
        "[ERROR] falhou",
    ]
