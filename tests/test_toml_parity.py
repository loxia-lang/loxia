# SPDX-License-Identifier: MIT OR Apache-2.0
"""Paridade do spike de TOML em Lox contra `tomllib` (ADR-0118, issue #53).

Cada fixture é analisada pelo programa Lox e o texto canônico que ele emite é reparseado
pelo `tomllib`: o dado tem que bater (com `Int`/`Float`/`Bool` distintos), a saída tem que
ser estável e a própria saída tem que ser aceita e reproduzida pelo parser Lox.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
MAIN = ROOT / "tests" / "lox" / "toml" / "main.lx"
CASES = ROOT / "tests" / "lox" / "toml" / "cases"

VALID = (
    "minimal.toml",
    "tables.toml",
    "dotted.toml",
    "arrays.toml",
    "inline.toml",
    "strings.toml",
    "numbers.toml",
    "aot.toml",
    "comments.toml",
    "canon_a.toml",
    "canon_b.toml",
)
INVALID = (
    "bad_duplicate.toml",
    "bad_unterminated.toml",
    "bad_array.toml",
    "bad_table.toml",
    "bad_number.toml",
)
OUTSIDE_SUBSET = ("bad_date.toml", "bad_inf.toml")


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), "run", str(MAIN), "--", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _normalize(value: Any) -> Any:
    """Compara estrutura preservando o tipo numérico (`bool` antes de `int`)."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, list):
        return ("list", tuple(_normalize(item) for item in value))
    if isinstance(value, dict):
        return ("table", tuple(sorted((key, _normalize(item)) for key, item in value.items())))
    raise AssertionError(f"valor inesperado do tomllib: {value!r}")


@pytest.mark.parametrize("name", VALID)
def test_roundtrip_bate_com_tomllib(name: str, tmp_path: Path) -> None:
    source = CASES / name
    expected = tomllib.loads(source.read_text(encoding="utf-8"))

    first = _run(source)

    assert first.returncode == 0, first.stdout + first.stderr
    assert _normalize(tomllib.loads(first.stdout)) == _normalize(expected)

    # Determinismo: duas execuções produzem os mesmos bytes.
    assert _run(source).stdout == first.stdout

    # Forma canônica: o Lox reparseia a própria saída e reproduz os mesmos bytes.
    rendered = tmp_path / "rendered.toml"
    rendered.write_text(first.stdout, encoding="utf-8")
    again = _run(rendered)

    assert again.returncode == 0, again.stdout + again.stderr
    assert again.stdout == first.stdout
    assert _normalize(tomllib.loads(again.stdout)) == _normalize(expected)


@pytest.mark.parametrize("name", INVALID)
def test_texto_invalido_falha_nos_dois(name: str) -> None:
    source = CASES / name
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(source.read_text(encoding="utf-8"))

    result = _run(source)

    assert result.returncode == 65
    assert re.match(r"ERR \d+:\d+: ", result.stdout), result.stdout


@pytest.mark.parametrize("name", OUTSIDE_SUBSET)
def test_fora_do_subconjunto_falha_com_posicao(name: str) -> None:
    source = CASES / name
    tomllib.loads(source.read_text(encoding="utf-8"))  # é TOML válido

    result = _run(source)

    assert result.returncode == 65
    assert re.match(r"ERR \d+:\d+: ", result.stdout), result.stdout
    assert "subset" in result.stdout


def test_crlf_e_aceito_e_produz_a_mesma_saida(tmp_path: Path) -> None:
    lf = CASES / "minimal.toml"
    crlf = tmp_path / "crlf.toml"
    crlf.write_bytes(lf.read_bytes().replace(b"\n", b"\r\n"))

    unix = _run(lf)
    windows = _run(crlf)

    assert windows.returncode == 0, windows.stdout + windows.stderr
    assert windows.stdout == unix.stdout


def test_forma_canonica_ignora_ordem_e_comentarios() -> None:
    first = _run(CASES / "canon_a.toml")
    second = _run(CASES / "canon_b.toml")

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert first.stdout == second.stdout
