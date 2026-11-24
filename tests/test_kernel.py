# SPDX-License-Identifier: MIT OR Apache-2.0
"""Kernel 13.2: ambiente, I/O e exit code no interpretador."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def _run(*arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_args_e_getenv(tmp_path: Path) -> None:
    path = tmp_path / "args.lx"
    path.write_text(
        """print(args())
print(os.getenv("LOX_KERNEL_TEST"))
""",
        encoding="utf-8",
    )
    env = {"LOX_KERNEL_TEST": "ok", "PATH": "/usr/bin:/bin"}
    result = _run(str(path), "a", "b", env=env)

    assert result.returncode == 0, result.stderr
    assert result.stdout == '["a", "b"]\nok\n'


def test_os_exit(tmp_path: Path) -> None:
    path = tmp_path / "exit.lx"
    path.write_text(
        """print("antes")
os.exit(7)
print("depois")
""",
        encoding="utf-8",
    )

    result = _run(str(path))

    assert result.returncode == 7
    assert result.stdout == "antes\n"


def test_leitura_e_escrita_de_arquivo(tmp_path: Path) -> None:
    target = tmp_path / "dados.txt"
    path = tmp_path / "arquivo.lx"
    path.write_text(
        f'io.writeFile("{target}", "linha\\n")\n'
        f'print(io.readFile("{target}"))\n'
        f'print(io.readFile("{tmp_path}/nao-existe.txt"))\n',
        encoding="utf-8",
    )

    result = _run(str(path))

    assert result.returncode == 0, result.stderr
    assert result.stdout == "linha\n\nnil\n"


def _c_locale_env() -> dict[str, str]:
    # O locale C faz `sys.stdin` usar surrogateescape; o teste força o caso em que
    # a leitura em texto ecoaria bytes inválidos em vez de falhar.
    return {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0"}


def test_read_all_rejeita_stdin_nao_utf8(tmp_path: Path) -> None:
    path = tmp_path / "readall.lx"
    path.write_text(
        """import std.io as io
print(io.readAll())
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(path)],
        cwd=ROOT,
        input=b"\xff\xfe",
        capture_output=True,
        check=False,
        env=_c_locale_env(),
    )

    assert result.returncode == 70
    assert b"expects UTF-8 input" in result.stderr
    assert b"Traceback" not in result.stderr


def test_read_line_rejeita_stdin_nao_utf8(tmp_path: Path) -> None:
    path = tmp_path / "readline.lx"
    path.write_text(
        """import std.io as io
print(io.readLine())
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(path)],
        cwd=ROOT,
        input=b"\xff\n",
        capture_output=True,
        check=False,
        env=_c_locale_env(),
    )

    assert result.returncode == 70
    assert b"expects UTF-8 input" in result.stderr
    assert b"Traceback" not in result.stderr


def test_read_file_preserva_crlf(tmp_path: Path) -> None:
    target = tmp_path / "crlf.txt"
    target.write_bytes(b"a\r\nb\r\n")
    path = tmp_path / "ler.lx"
    path.write_text(
        f'val t = io.readFile("{target}")\nprint(len(t as String))\nprint(repr(t))\n',
        encoding="utf-8",
    )

    result = _run(str(path))

    assert result.returncode == 0, result.stderr
    assert result.stdout == '6\n"a\\r\\nb\\r\\n"\n'


def _run_bytes(path: Path, data: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(path)],
        cwd=ROOT,
        input=data,
        capture_output=True,
        check=False,
    )


def test_read_utf8_le_exatamente_n_bytes(tmp_path: Path) -> None:
    path = tmp_path / "utf8.lx"
    path.write_text(
        "print(io.readUtf8(3))\n"
        "print(io.readUtf8(0))\n"
        "print(io.readUtf8(3))\n"
        "print(io.readUtf8(1))\n",
        encoding="utf-8",
    )

    result = _run_bytes(path, b"abcdef")

    assert result.returncode == 0, result.stderr
    assert result.stdout == b"abc\n\ndef\nnil\n"


def test_read_utf8_decodifica_multibyte(tmp_path: Path) -> None:
    path = tmp_path / "utf8.lx"
    path.write_text("print(io.readUtf8(6))\n", encoding="utf-8")

    result = _run_bytes(path, "ação".encode())

    assert result.returncode == 0, result.stderr
    assert result.stdout == "ação\n".encode()


def test_read_utf8_rejeita_truncado(tmp_path: Path) -> None:
    path = tmp_path / "utf8.lx"
    path.write_text("print(io.readUtf8(5))\n", encoding="utf-8")

    result = _run_bytes(path, b"abc")

    assert result.returncode == 70
    assert b"error[R1000]: io.readUtf8() expects exactly 5 bytes." in result.stderr
    assert b"Traceback" not in result.stderr


def test_read_utf8_rejeita_bytes_invalidos(tmp_path: Path) -> None:
    path = tmp_path / "utf8.lx"
    path.write_text("print(io.readUtf8(1))\n", encoding="utf-8")

    result = _run_bytes(path, b"\xff")

    assert result.returncode == 70
    assert b"error[R1000]: io.readUtf8() expects UTF-8 input." in result.stderr
    assert b"Traceback" not in result.stderr
