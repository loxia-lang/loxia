# SPDX-License-Identifier: MIT OR Apache-2.0
"""Schema do THIR v1: contrato versionado, validação de payloads e cobertura do modelo."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from loxia_core.thir import model
from loxia_core.thir.serialize import to_payload
from tests.test_thir_serialization import GENERIC
from tests.thir_support import module_for_case, module_for_source
from tools.thir_schema import SCHEMA_PATH, build_schema

REPRESENTATIVE_CASES = (
    "tests/cases/generic_class.lx",
    "tests/cases/nested_destructure.lx",
    "tests/cases/result_nil.lx",
    "tests/cases/break_continue.lx",
    "tests/cases/any_field_layout.lx",
    "tests/cases/tuples.lx",
)


def _schema() -> dict[str, object]:
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_checked_in_schema_matches_the_model() -> None:
    current = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert current == build_schema(), (
        "schema/thir-v1.json está desatualizado; rode `make thir-schema`"
    )


def test_schema_defines_every_model_class() -> None:
    definitions = _schema()["$defs"]
    assert isinstance(definitions, dict)
    expected = {
        name
        for name, value in vars(model).items()
        if isinstance(value, type)
        and dataclasses.is_dataclass(value)
        and value.__module__ == model.__name__
    }
    assert expected <= set(definitions), f"fora do schema: {sorted(expected - set(definitions))}"
    assert "Ty" in definitions


@pytest.mark.parametrize("case", REPRESENTATIVE_CASES, ids=lambda case: Path(case).stem)
def test_representative_payloads_validate(case: str) -> None:
    payload = to_payload(module_for_case(case))
    jsonschema.Draft202012Validator(_schema()).validate(payload)


def test_generic_payload_validates() -> None:
    payload = to_payload(module_for_source(GENERIC))
    jsonschema.Draft202012Validator(_schema()).validate(payload)


def test_schema_rejects_unknown_kind_and_extra_fields() -> None:
    schema = _schema()
    validator = jsonschema.Draft202012Validator(schema)

    payload = to_payload(module_for_source("print(1)"))
    statements = payload["statements"]
    assert isinstance(statements, list)
    first = statements[0]
    assert isinstance(first, dict)
    first["k"] = "TBogus"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)

    payload = to_payload(module_for_source("print(1)"))
    statements = payload["statements"]
    assert isinstance(statements, list)
    first = statements[0]
    assert isinstance(first, dict)
    first["bogus"] = True
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)
