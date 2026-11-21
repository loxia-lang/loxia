# SPDX-License-Identifier: MIT OR Apache-2.0
"""Testes de oráculo do `std.test`: TAP, filtros, skip e falhas (ADR-0096)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_script(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loxia", "run", str(path), "--", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "caso_test.lx"
    path.write_text(source, encoding="utf-8")
    return path


PASS_SOURCE = """
import std.test as t

val suite = t.Suite()

suite.describe("soma", fn() {
  suite.it("inteiros", fn() { t.expect(1 + 1).toBe(2) })
  suite.it("pula", fn() { suite.skip("sem rede") })
})
suite.done()
"""


def test_suite_que_passa_imprime_tap_e_sai_zero(tmp_path: Path) -> None:
    result = run_script(write(tmp_path, PASS_SOURCE))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "ok 1 - soma / inteiros",
        "ok 2 - soma / pula # SKIP sem rede",
        "1..2",
        "# tests 2",
        "# pass 1",
        "# fail 0",
        "# skip 1",
    ]


def test_falha_imprime_diagnostico_e_sai_um(tmp_path: Path) -> None:
    source = """
import std.test as t

val suite = t.Suite()
suite.it("falha", fn() { t.expect(1 + 1).toBe(3) })
suite.done()
"""
    result = run_script(write(tmp_path, source))
    assert result.returncode == 1
    assert "not ok 1 - falha" in result.stdout
    assert "  # expected 3, got 2" in result.stdout
    assert "# fail 1" in result.stdout


def test_erro_de_runtime_vira_falha_do_teste(tmp_path: Path) -> None:
    source = """
import std.test as t

val suite = t.Suite()
suite.it("estoura", fn() { raise RuntimeError("boom") })
suite.it("seguinte", fn() { t.expect(1).toBe(1) })
suite.done()
"""
    result = run_script(write(tmp_path, source))
    assert result.returncode == 1
    assert "not ok 1 - estoura" in result.stdout
    assert "  # boom" in result.stdout
    assert "ok 2 - seguinte" in result.stdout


def test_expect_raise_sem_excecao_falha(tmp_path: Path) -> None:
    source = """
import std.test as t

val suite = t.Suite()
suite.it("sem raise", fn() { t.expectRaise(fn() { print("nada") }) })
suite.done()
"""
    result = run_script(write(tmp_path, source))
    assert result.returncode == 1
    assert "expected an exception, none was raised" in result.stdout


def test_filtro_e_only(tmp_path: Path) -> None:
    source = """
import std.test as t

val suite = t.Suite()
suite.it("um", fn() { t.expect(1).toBe(1) })
suite.it("dois", fn() { t.expect(2).toBe(2) })
suite.done()
"""
    path = write(tmp_path, source)
    filtered = run_script(path, "--filter=dois")
    assert filtered.returncode == 0
    assert "ok 1 - dois" in filtered.stdout
    assert "um" not in filtered.stdout
    only = run_script(path, "--only=um")
    assert only.returncode == 0
    assert only.stdout.splitlines()[:1] == ["ok 1 - um"]


def test_site_da_falha_aponta_para_a_linha_do_teste(tmp_path: Path) -> None:
    source = """
import std.test as t

val suite = t.Suite()
suite.it("falha", fn() {
  t.expect(1 + 1).toBe(3)
})
suite.done()
"""
    result = run_script(write(tmp_path, source))
    assert result.returncode == 1
    assert "caso_test.lx:" in result.stdout
    assert "std/test.lx" not in result.stdout
    assert "  # at " in result.stdout
