# SPDX-License-Identifier: MIT OR Apache-2.0
"""Contrato do relatório `loxia test --json` (schema v1).

Não valida com uma biblioteca de JSON Schema: o schema é um artefato de contrato e o
teste garante que o payload real tem os campos obrigatórios, os tipos e os enums que o
schema publica. Isso pega drift sem adicionar dependência.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "test-report-v1.json"

SOURCE = """
import std.test as t
val suite = t.Suite()
suite.it("passa", fn() { t.expect(1).toBe(1) })
suite.it("falha", fn() { print("antes"); t.expect(1).toBe(2) })
suite.done()
"""


def _report(tmp_path: Path, *args: str) -> dict[str, Any]:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "report_test.lx").write_text(SOURCE, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "loxia", "test", str(tests), "--json", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    return cast(dict[str, Any], json.loads(result.stdout))


def test_payload_has_every_required_schema_field(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    payload = _report(tmp_path, "--capture")

    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["properties"]["schema_version"]["const"] == 1
    assert set(schema["required"]) == set(payload)
    assert payload["schema_version"] == 1
    assert payload["command"] == "test"
    assert payload["success"] is False
    assert payload["exit_code"] == 1

    item = cast(dict[str, Any], payload["tests"][0])
    assert set(schema["$defs"]["test"]["required"]) == set(item)
    assert item["status"] in schema["$defs"]["test"]["properties"]["status"]["enum"]
    assert item["kind"] in schema["$defs"]["test"]["properties"]["kind"]["enum"]
    assert isinstance(item["file"], str)
    assert isinstance(item["name"], str)
    assert isinstance(item["message"], str)
    assert item["location"] is None
    assert item["output"] is None

    failed = cast(dict[str, Any], payload["tests"][1])
    assert failed["status"] == "fail"
    assert failed["output"] == "antes"
    assert failed["location"] is not None
    assert failed["location"]["file"].endswith("report_test.lx")

    summary = cast(dict[str, Any], payload["summary"])
    assert set(schema["$defs"]["summary"]["required"]) == set(summary)
    assert summary["tests"] == summary["pass"] + summary["fail"] + summary["skip"]


def test_capture_off_deixa_output_nulo(tmp_path: Path) -> None:
    payload = _report(tmp_path)
    assert payload["tests"][0]["output"] is None


def test_schema_version_so_muda_em_breaking_change(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    payload = _report(tmp_path)
    assert schema["properties"]["schema_version"]["const"] == payload["schema_version"]
