# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ponto de entrada `main -> Result` e a borda de exit 70 (ADR-0148).

Os casos golden cobrem o caminho do `run` e o corpus diferencial cobre os três canais
no backend; aqui ficam as bordas que não cabem em um `.lx`: só o arquivo de entrada tem
entry, o REPL nunca tem, e o `--check` valida a assinatura antes de qualquer execução.
"""

from __future__ import annotations

from pathlib import Path

from tests.inprocess import run_cli


def _write(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


def _entry(source: str) -> str:
    return f"fn main() -> Result[Int, String] {{\n{source}\n}}\n"


def test_main_de_modulo_nao_e_entry(tmp_path: Path) -> None:
    """O entry é só o `main` do arquivo executado; módulos nunca são chamados."""
    _write(
        tmp_path / "lib.lx",
        _entry('  print("module")\n  return Result.Err("module")'),
    )
    program = _write(
        tmp_path / "prog.lx",
        'import lib\nprint("top")\n' + _entry('  print("entry")\n  return Result.Ok(0)'),
    )

    result = run_cli("run", "--interpret", str(program), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "top\nentry\n"


def test_main_no_repl_nao_e_entry() -> None:
    """O REPL é sessão interativa: `fn main` é uma função comum, nunca a borda."""
    source = 'fn main() -> Result[Int, String] { print("called"); return Result.Ok(0) }\n1 + 1\n'

    result = run_cli("repl", stdin=source)

    assert result.returncode == 0, result.stderr
    assert "called" not in result.stdout
    assert "2" in result.stdout


def test_check_valida_a_assinatura_do_entry(tmp_path: Path) -> None:
    """`--check` aceita o entry válido e recusa a assinatura quase-Result com E3026."""
    valid = _write(tmp_path / "valid.lx", _entry('  return Result.Err("boom")'))
    checked = run_cli("--check", str(valid))
    assert checked.returncode == 0, checked.stderr

    invalid = _write(
        tmp_path / "invalid.lx", "fn main() -> Result[Int, Int] {\n  return Result.Ok(0)\n}\n"
    )
    rejected = run_cli("--check", str(invalid))

    assert rejected.returncode == 65
    assert "E3026" in rejected.stderr
    assert "Result[T, String]" in rejected.stderr


def test_check_nao_cobra_assinatura_de_main_que_nao_e_entry(tmp_path: Path) -> None:
    """`main -> Nil`/`Int` segue função comum; só `Result` abre o contrato."""
    for source in (
        'fn main() -> Nil { print("x") }\n',
        "fn main() -> Int { return 1 }\n",
    ):
        program = _write(tmp_path / "helper.lx", source)
        checked = run_cli("--check", str(program))
        assert checked.returncode == 0, checked.stderr
