# SPDX-License-Identifier: MIT OR Apache-2.0
"""Testes do subcomando `loxia test` (ADR-0096)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PASS = """
import std.test as t
val suite = t.Suite()
suite.it("passa", fn() { t.expect(1 + 1).toBe(2) })
suite.done()
"""

FAIL = """
import std.test as t
val suite = t.Suite()
suite.it("falha", fn() { t.expect(1).toBe(2) })
suite.done()
"""


def run_test(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loxia", "test", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def project(tmp_path: Path) -> Path:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "pass_test.lx").write_text(PASS, encoding="utf-8")
    (tests / "fail_test.lx").write_text(FAIL, encoding="utf-8")
    (tests / "helper.lx").write_text("print(1)\n", encoding="utf-8")
    return tests


def test_descobre_agrega_e_sai_um(tmp_path: Path) -> None:
    result = run_test(str(project(tmp_path)))
    assert result.returncode == 1
    assert "not ok 1 - falha" in result.stdout
    assert "ok 2 - passa" in result.stdout
    assert "# tests 2" in result.stdout
    assert "# files 2" in result.stdout
    assert "helper" not in result.stdout


def test_json_tem_envelope_estavel(tmp_path: Path) -> None:
    result = run_test(str(project(tmp_path)), "--json")
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["summary"] == {
        "files": 2,
        "tests": 2,
        "pass": 1,
        "fail": 1,
        "skip": 0,
    }
    statuses = {item["name"]: item["status"] for item in payload["tests"]}
    assert statuses == {"passa": "pass", "falha": "fail"}


def test_isolamento_de_exit_e_timeout(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "ok_test.lx").write_text(PASS, encoding="utf-8")
    (tests / "sai_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("antes", fn() { t.expect(1).toBe(1) })\n'
        "os.exit(7)\n",
        encoding="utf-8",
    )
    result = run_test(str(tests))
    assert result.returncode == 1
    assert "ok 1 - passa" in result.stdout
    assert "exit 7" in result.stdout
    slow = tests / "lento_test.lx"
    slow.write_text(
        "import std.test as t\nval suite = t.Suite()\n"
        'suite.it("dorme", fn() { time.sleep(5000) })\nsuite.done()\n',
        encoding="utf-8",
    )
    slow_result = run_test(str(slow), "--timeout", "250")
    assert slow_result.returncode == 1
    assert "timeout" in slow_result.stdout


def test_filtro_e_jobs(tmp_path: Path) -> None:
    tests = project(tmp_path)
    filtered = run_test(str(tests), "--filter", "passa", "--jobs", "2")
    assert filtered.returncode == 0
    assert "ok 1 - passa" in filtered.stdout
    assert "# fail 0" in filtered.stdout


def test_sem_arquivos_sai_dois(tmp_path: Path) -> None:
    empty = tmp_path / "vazio"
    empty.mkdir()
    result = run_test(str(empty))
    assert result.returncode == 2
    assert "nenhum arquivo" in result.stderr


EXIT_SOURCE = """
import std.test as t
val suite = t.Suite()
suite.it("estoura", fn() { os.exit(7) })
suite.it("sobrevive", fn() { t.expect(1 + 1).toBe(2) })
suite.done()
"""


def test_isolamento_por_teste_sobrevive_a_exit(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "a_test.lx").write_text(EXIT_SOURCE, encoding="utf-8")
    result = run_test(str(tests), "--isolate", "test", "--jobs", "2")
    assert result.returncode == 1
    assert "not ok 1 - estoura" in result.stdout
    assert "ok 2 - sobrevive" in result.stdout


def test_isolamento_por_teste_em_json(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "a_test.lx").write_text(EXIT_SOURCE, encoding="utf-8")
    result = run_test(str(tests), "--isolate", "test", "--json")
    payload = json.loads(result.stdout)
    statuses = {item["name"]: item["status"] for item in payload["tests"]}
    assert statuses == {"estoura": "fail", "sobrevive": "pass"}


@pytest.mark.backend
def test_isolamento_por_teste_nativo(tmp_path: Path) -> None:
    pytest.importorskip("llvmlite")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "a_test.lx").write_text(PASS, encoding="utf-8")
    result = run_test(str(tests), "--native", "--isolate", "test")
    assert result.returncode == 0, result.stderr
    assert "ok 1 - passa" in result.stdout
