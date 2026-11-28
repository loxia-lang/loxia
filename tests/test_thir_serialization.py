# SPDX-License-Identifier: MIT OR Apache-2.0
"""Serialização do THIR: contrato JSON v1, round-trip e determinismo (I3)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loxia_core.thir import TModule
from loxia_core.thir.serialize import (
    ThirFormatError,
    canonical,
    dumps,
    from_payload,
    loads,
    to_payload,
)
from tests.inprocess import run_cli
from tests.thir_support import ROOT, analyze_case, module_for, module_for_source

GENERIC = """
class Box[T] {
  var value: T
  fn init(value: T) { this.value = value }
  fn get() -> T { return this.value }
}
fn identidade[T](x: T) -> T { return x }
val caixa = Box(1)
print(identidade(caixa.get()))
"""


def test_payload_has_version_and_kind() -> None:
    payload = to_payload(module_for_source("print(1)"))
    assert payload["k"] == "TModule"
    assert payload["schema_version"] == 1
    assert isinstance(payload["decls"], list)
    assert payload["entry"] is None


def test_dumps_is_deterministic_for_a_module() -> None:
    module = module_for_source(GENERIC)
    assert dumps(module) == dumps(module)
    assert canonical(module) == canonical(module)
    assert dumps(module).endswith("\n")
    json.loads(dumps(module))


def test_roundtrip_keeps_the_module() -> None:
    module = module_for_source(GENERIC)
    assert loads(dumps(module)) == module
    assert from_payload(to_payload(module)) == module


def test_roundtrip_is_byte_stable() -> None:
    module = module_for_source(GENERIC)
    assert dumps(loads(dumps(module))) == dumps(module)


def test_types_are_structured_not_display_strings() -> None:
    payload = to_payload(module_for_source("val xs: List[Int?] = [1, nil]\nprint(xs)"))
    text = json.dumps(payload)
    assert '"k": "list"' in text or '"k":"list"' in text
    assert "List[Int?]" not in text, "o motor não deve precisar parsear display()"


def test_non_finite_float_survives_the_roundtrip() -> None:
    module = module_for_source("val x = 1e999\nprint(x)")
    text = dumps(module)
    assert "non_finite_float" in text
    assert loads(text) == module


def test_unknown_schema_version_is_rejected() -> None:
    payload = to_payload(module_for_source("print(1)"))
    payload["schema_version"] = 99
    with pytest.raises(ThirFormatError):
        from_payload(payload)


def test_wrong_kind_is_rejected() -> None:
    with pytest.raises(ThirFormatError):
        from_payload({"k": "TStmt", "span": None})


def test_canonical_text_does_not_leak_absolute_paths() -> None:
    statements, checker = analyze_case("tests/cases/generic_class.lx")
    module = module_for(statements, checker, source_path="tests/cases/generic_class.lx")
    text = canonical(module)
    assert str(ROOT) not in text
    assert 'source_path":"tests/cases/generic_class.lx' in text


def test_canonical_is_stable_across_processes() -> None:
    script = (
        "from tests.thir_support import module_for_case\n"
        "from loxia_core.thir.serialize import canonical\n"
        "import hashlib\n"
        "text = canonical(module_for_case('tests/cases/generic_class.lx'))\n"
        "print(hashlib.sha256(text.encode()).hexdigest())\n"
    )
    digests = []
    for seed in ("0", "1"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 0, result.stderr
        digests.append(result.stdout.strip())
    assert digests[0] == digests[1], f"THIR muda com PYTHONHASHSEED: {digests}"


def test_cli_build_emit_thir_writes_json(tmp_path: Path) -> None:
    target = tmp_path / "prog.thir.json"
    result = run_cli("build", "tests/cases/generic_class.lx", "--emit=thir", "-o", str(target))
    assert result.returncode == 0, result.stderr
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["k"] == "TModule"
    assert payload["schema_version"] == 1
    assert payload["source_path"] == "tests/cases/generic_class.lx"


def test_cli_emit_thir_to_stdout_is_stable() -> None:
    first = run_cli("build", "tests/cases/generic_class.lx", "--emit=thir")
    second = run_cli("build", "tests/cases/generic_class.lx", "--emit=thir")
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert TModule is not None
