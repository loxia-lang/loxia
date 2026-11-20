# SPDX-License-Identifier: MIT OR Apache-2.0
"""Kernel de processos (ADR-0095/0119): `std.proc` no oráculo.

Os testes usam o próprio `sys.executable` como filho — nada de `cat`/shell — para
funcionar em qualquer POSIX com o Python do ambiente.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="proc.* é POSIX (posix_spawn/poll)")

PREAMBLE = "import std.proc as p\nimport std.results as results\n"


def _run_source(tmp_path: Path, source: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "caso.lx"
    path.write_text(source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _run_lox(code: str, stdin: str = "", timeout_ms: int = 0) -> str:
    return (
        PREAMBLE
        + f"val py = {json.dumps(sys.executable)}\n"
        f'val out = p.run([py, "-c", {json.dumps(code)}], '
        f"{json.dumps(stdin)}, {timeout_ms})\n"
        "val done = results.toOptional(out)\n"
        "if (done == nil) {\n"
        "  val failure = results.errorOf(out)\n"
        '  print(failure?.kind ?? "io")\n'
        "} else {\n"
        "  print(done.code)\n"
        "  print(repr(done.stdout))\n"
        "  print(repr(done.stderr))\n"
        "}\n"
    )


def test_run_captura_stdout_e_codigo(tmp_path: Path) -> None:
    result = _run_source(
        tmp_path, _run_lox("import sys; sys.stdout.write(sys.stdin.read())", "ola\n")
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == '0\n"ola\\n"\n""\n'


def test_run_captura_stderr_e_codigo(tmp_path: Path) -> None:
    result = _run_source(tmp_path, _run_lox('import sys; sys.stderr.write("erro"); sys.exit(3)'))

    assert result.returncode == 0, result.stderr
    assert result.stdout == '3\n""\n"erro"\n'


def test_run_utf8_acima_do_chunk(tmp_path: Path) -> None:
    result = _run_source(tmp_path, _run_lox("import sys; sys.stdout.write(chr(231)*3000)"))

    assert result.returncode == 0, result.stderr
    assert result.stdout == '0\n"' + "ç" * 3000 + '"\n""\n'


def test_run_timeout_vira_erro_de_kind_timeout(tmp_path: Path) -> None:
    started = time.monotonic()
    result = _run_source(tmp_path, _run_lox("import time; time.sleep(10)", timeout_ms=200))
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert result.stdout == "timeout\n"
    assert elapsed < 5.0


def test_spawn_poll_wait_e_streams(tmp_path: Path) -> None:
    source = (
        PREAMBLE
        + f"val py = {json.dumps(sys.executable)}\n"
        'val spawned = p.spawn([py, "-c", '
        + json.dumps("import sys; sys.stdout.write('eco')")
        + "])\n"
        "val child = results.toOptional(spawned)\n"
        "if (child == nil) {\n"
        '  print("nil")\n'
        "} else {\n"
        "  val ready = process.poll([child.id, child.stdout.id], 5000)\n"
        "  print(len(ready) >= 1)\n"
        "  val chunk = child.stdout.read(64)\n"
        "  val text = results.toOptional(chunk)\n"
        '  print(text ?? "nil")\n'
        "  val waited = child.wait()\n"
        "  print(results.unwrapOr(waited, -1))\n"
        "  child.close()\n"
        "}\n"
    )

    result = _run_source(tmp_path, source)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "true\neco\n0\n"


def test_handle_de_tipo_errado_aponta_chamada(tmp_path: Path) -> None:
    source = (
        PREAMBLE
        + f"val py = {json.dumps(sys.executable)}\n"
        'val spawned = p.spawn([py, "-c", "pass"])\n'
        "val child = results.toOptional(spawned)\n"
        "if (child != nil) {\n"
        "  print(process.read(child.id, 4))\n"
        "}\n"
    )

    result = _run_source(tmp_path, source)

    assert result.returncode == 70
    assert "error[R1000]: process.read() expects a stream handle." in result.stderr
    assert re.search(r"caso\.lx:\d+:", result.stderr)
    assert "Traceback" not in result.stderr
