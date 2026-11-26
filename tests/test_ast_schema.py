# SPDX-License-Identifier: MIT OR Apache-2.0
"""AST JSON v2: schema por kind, validação do corpus e overlay tipado."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import jsonschema  # type: ignore[import-untyped]
import pytest

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.ast_json import program_payload
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from tools.ast_schema import SCHEMA_PATH, render_schema

ROOT = Path(__file__).resolve().parents[1]


def _check(value: object, schema: dict[str, object], root: dict[str, object]) -> None:
    """Validador mínimo (subconjunto do JSON Schema) para o corpus inteiro.

    `jsonschema` é a referência para os casos de contrato; para 313 arquivos a
    implementação pura é lenta demais porque `$.$defs.node` tem 50+ alternativas.
    O subconjunto abaixo cobre os recursos usados pelo schema gerado.
    """
    reference = schema.get("$ref")
    if isinstance(reference, str):
        assert reference.startswith("#/$defs/")
        target = root["$defs"]
        assert isinstance(target, dict)
        _check(value, target[reference.rsplit("/", 1)[-1]], root)
        return

    alternatives = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(alternatives, list):
        if isinstance(value, dict) and isinstance(value.get("kind"), str):
            kind = value["kind"]
            definitions = root["$defs"]
            assert isinstance(definitions, dict)
            assert kind in definitions, kind
            target = definitions[kind]
            assert isinstance(target, dict)
            _check(value, target, root)
            return
        matches = 0
        for alternative in alternatives:
            assert isinstance(alternative, dict)
            try:
                _check(value, alternative, root)
            except AssertionError:
                continue
            matches += 1
        assert matches >= 1 if "anyOf" in schema else matches == 1
        return

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        assert any(_is_type(value, item) for item in types), (value, expected)
    if "const" in schema:
        assert value == schema["const"]
    if "enum" in schema:
        enum = schema["enum"]
        assert isinstance(enum, list)
        assert value in enum
    if "minimum" in schema:
        minimum = schema["minimum"]
        assert isinstance(minimum, int)
        assert isinstance(value, int) and value >= minimum

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                assert key in value, key
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, item in value.items():
                if key in properties:
                    assert isinstance(properties[key], dict)
                    _check(item, properties[key], root)
                elif schema.get("additionalProperties") is False:
                    raise AssertionError(f"unexpected property {key}")
    elif isinstance(value, list):
        prefix = schema.get("prefixItems")
        if isinstance(prefix, list):
            assert len(value) <= len(prefix) or "items" in schema
            for index, item in enumerate(value[: len(prefix)]):
                assert isinstance(prefix[index], dict)
                _check(item, prefix[index], root)
        items = schema.get("items")
        if isinstance(items, dict):
            for item in value:
                _check(item, items, root)


def _is_type(value: object, expected: object) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _schema() -> dict[str, object]:
    return cast(dict[str, object], json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _statements(payload: dict[str, object]) -> list[dict[str, Any]]:
    syntax = payload["syntax"]
    assert isinstance(syntax, dict)
    statements = syntax["statements"]
    assert isinstance(statements, list)
    return cast(list[dict[str, Any]], statements)


def _payload(source: str) -> dict[str, object]:
    reporter = ErrorReporter()
    reporter.file = "schema.lx"
    scanner = Scanner(source, reporter)
    tokens = scanner.scan_tokens()
    statements = Parser(tokens, reporter=reporter).parse()
    assert statements is not None
    return program_payload(statements, tokens, "schema.lx", trivia=scanner.trivia)


def test_schema_is_generated_from_the_dataclasses() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema()


def test_schema_defines_every_node_kind() -> None:
    schema = _schema()
    defs = schema["$defs"]
    assert isinstance(defs, dict)
    node = defs["node"]
    assert isinstance(node, dict)
    refs = node["anyOf"]
    assert isinstance(refs, list)
    assert len(refs) > 40
    for ref in refs:
        name = ref["$ref"].rsplit("/", 1)[-1]
        assert name in defs


def test_schema_validates_the_parseable_corpus() -> None:
    schema = _schema()
    paths = sorted(
        {
            *ROOT.glob("std/**/*.lx"),
            *ROOT.glob("tests/cases/**/*.lx"),
            *ROOT.glob("examples/**/*.lx"),
        }
    )
    validated = 0
    for path in paths:
        source = path.read_text(encoding="utf-8")
        reporter = ErrorReporter()
        reporter.file = str(path)
        tokens = Scanner(source, reporter).scan_tokens()
        statements = Parser(tokens, reporter=reporter).parse()
        if reporter.had_error or statements is None:
            continue
        payload = program_payload(statements, tokens, str(path))
        _check(payload, schema, schema)
        validated += 1
    assert validated == 356


def test_schema_rejects_unknown_fields_and_wrong_version() -> None:
    payload = _payload("val x = 1\n")
    validator = jsonschema.Draft202012Validator(_schema())

    statements = _statements(payload)
    statement = statements[0]
    assert isinstance(statement, dict)
    statement["bogus"] = True
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)

    payload = _payload("val x = 1\n")
    payload["schema_version"] = 1
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)


def test_typed_overlay_is_valid_and_deterministic() -> None:
    command = [
        sys.executable,
        str(ROOT / "main.py"),
        "ast",
        "--file-only",
        "--format=json",
        "--typed",
        "--stdin",
    ]
    source = "val x: Int = 1\nprint(x + 2)\n"
    first = subprocess.run(
        command, cwd=ROOT, input=source, capture_output=True, text=True, check=False
    )
    second = subprocess.run(
        command, cwd=ROOT, input=source, capture_output=True, text=True, check=False
    )

    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    jsonschema.Draft202012Validator(_schema()).validate(payload)
    assert payload["typed"]["expressions"]


def test_syntax_trivia_is_in_the_contract() -> None:
    payload = _payload("val x = 1  # comentário\n")
    jsonschema.Draft202012Validator(_schema()).validate(payload)
    syntax = payload["syntax"]
    assert isinstance(syntax, dict)
    trivia = syntax["trivia"]
    assert isinstance(trivia, list)
    assert any(item["kind"] == "line_comment" for item in trivia)


def test_schema_rejects_nested_node_and_type_span_fields() -> None:
    validator = jsonschema.Draft202012Validator(_schema())

    payload = _payload("val x = 1 + 2\n")
    statements = _statements(payload)
    initializer = statements[0]["initializer"]
    assert isinstance(initializer, dict)
    initializer["bogus"] = True
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)

    payload = _payload("val x = 1 + 2\n")
    statements = _statements(payload)
    initializer = statements[0]["initializer"]
    assert isinstance(initializer, dict)
    initializer["left"] = 42
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)

    payload = _payload("val x: Int = 1\n")
    statements = _statements(payload)
    type_span = statements[0]["type_span"]
    assert isinstance(type_span, dict)
    type_span["bogus"] = 1
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)
