"""Kernel 13.2: ambiente, I/O e exit code no interpretador."""

from __future__ import annotations

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
    path = tmp_path / "args.lox"
    path.write_text(
        'print args()\nprint os.getenv("LOX_KERNEL_TEST")\n',
        encoding="utf-8",
    )
    env = {"LOX_KERNEL_TEST": "ok", "PATH": "/usr/bin:/bin"}
    result = _run(str(path), "a", "b", env=env)

    assert result.returncode == 0, result.stderr
    assert result.stdout == '["a", "b"]\nok\n'


def test_os_exit(tmp_path: Path) -> None:
    path = tmp_path / "exit.lox"
    path.write_text('print "antes"\nos.exit(7)\nprint "depois"\n', encoding="utf-8")

    result = _run(str(path))

    assert result.returncode == 7
    assert result.stdout == "antes\n"


def test_leitura_e_escrita_de_arquivo(tmp_path: Path) -> None:
    target = tmp_path / "dados.txt"
    path = tmp_path / "arquivo.lox"
    path.write_text(
        f'io.writeFile("{target}", "linha\\n")\n'
        f'print io.readFile("{target}")\n'
        f'print io.readFile("{tmp_path}/nao-existe.txt")\n',
        encoding="utf-8",
    )

    result = _run(str(path))

    assert result.returncode == 0, result.stderr
    assert result.stdout == "linha\n\nnil\n"
