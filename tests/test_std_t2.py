# SPDX-License-Identifier: MIT OR Apache-2.0
"""T2: módulos de ambiente (`std.fs`, `std.io`) e `--check` de toda a stdlib."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
CASES = ROOT / "tests" / "cases"


def _run(arguments: list[str], input: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        input=input,
    )


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "caso.lx"
    path.write_text(source, encoding="utf-8")
    return path


def test_fs_escrita_leitura_listagem(tmp_path: Path) -> None:
    data = tmp_path / "dados"
    data.mkdir()
    alvo = data / "arquivo.txt"
    path = _write(
        tmp_path,
        "import std.fs as fs\n"
        f'val alvo = "{alvo}"\n'
        f'val pasta = "{data}"\n'
        """print(fs.exists(alvo))
"""
        """print(fs.writeText(alvo, "a\\nb\\n"))
"""
        """print(fs.exists(alvo))
"""
        """print(fs.readText(alvo))
"""
        """print(fs.readLines(alvo))
"""
        """print(fs.appendText(alvo, "c\\n"))
"""
        """print(fs.readLines(alvo))
"""
        """print(fs.readText(pasta + "/nao-existe.txt"))
"""
        """print(fs.readLines(pasta + "/nao-existe.txt"))
"""
        """print(fs.listDir(pasta))
"""
        """print(fs.listDir(pasta + "/nao-existe"))
"""
        """print(fs.exists(pasta + "/nao-existe"))
""",
    )

    checked = _run(["--check", str(path)])
    assert checked.returncode == 0, checked.stderr

    result = _run([str(path)])

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "false\n"
        "true\n"
        "true\n"
        "a\nb\n\n"
        '["a", "b"]\n'
        "true\n"
        '["a", "b", "c"]\n'
        "nil\n"
        "nil\n"
        '["arquivo.txt"]\n'
        "nil\n"
        "false\n"
    )


def test_fs_append_cria_arquivo_ausente(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import std.fs as fs\n"
        'val alvo = "novo.txt"\n'
        """print(fs.appendText(alvo, "x"))
"""
        """print(fs.readText(alvo))
""",
    )

    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "true\nx\n"


def test_io_stdin_e_write(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import std.io as io\n"
        """print(io.readLine())
"""
        """print(io.readAll())
"""
        """print(io.prompt("nome? "))
"""
        'io.write("fim")\n',
    )

    checked = _run(["--check", str(path)])
    assert checked.returncode == 0, checked.stderr

    result = _run([str(path)], input="primeira\nresto\n")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "primeira\nresto\n\nnome? nil\nfim"
    assert result.stderr == ""


def test_io_write_err(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        'import std.io as io\nio.write("saida")\nio.writeErr("erro")\n',
    )

    result = _run([str(path)])

    assert result.returncode == 0
    assert result.stdout == "saida"
    assert result.stderr == "erro"


def test_check_limpo_de_cada_caso_std() -> None:
    casos = sorted(CASES.glob("std_*.lx"))
    assert len(casos) >= 7

    for case in casos:
        result = _run(["--check", str(case)])
        assert result.returncode == 0, f"{case.name}: {result.stderr}"
