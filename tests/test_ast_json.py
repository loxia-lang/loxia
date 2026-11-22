# SPDX-License-Identifier: MIT OR Apache-2.0
"""Contrato do JSON da AST (ADR-0129): spans, tokens, determinismo e CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.ast_json import SCHEMA_VERSION, canonical, dumps, program_payload
from loxia_core.frontend.expr import Literal
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.spans import span_of_token_exact
from loxia_core.frontend.stmt import Expression
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token

ROOT = Path(__file__).resolve().parents[1]


def _program(source: str, file: str = "case.lx") -> dict[str, object]:
    reporter = ErrorReporter()
    reporter.file = file
    tokens = Scanner(source, reporter).scan_tokens()
    statements = Parser(tokens, reporter=reporter).parse()
    assert statements is not None
    return program_payload(statements, tokens, file)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "main.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_program_envelope_and_token_spans() -> None:
    payload = _program("val x = 1\n")

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "program"
    assert payload["file"] == "case.lx"
    tokens = payload["tokens"]
    assert isinstance(tokens, list)
    assert [token["type"] for token in tokens] == [
        "VAL",
        "IDENTIFIER",
        "EQUAL",
        "NUMBER",
        "EOF",
    ]
    assert tokens[0]["lexeme"] == "val"
    assert tokens[0]["span"] == {
        "start": {"line": 1, "column": 1, "offset": 0},
        "end": {"line": 1, "column": 4, "offset": 3},
    }

    statements = payload["statements"]
    assert isinstance(statements, list)
    declaration = statements[0]
    assert declaration["kind"] == "var"
    assert declaration["span"] == {
        "start": {"line": 1, "column": 1, "offset": 0},
        "end": {"line": 1, "column": 10, "offset": 9},
    }
    assert declaration["name"]["lexeme"] == "x"
    assert declaration["initializer"]["value"] == 1


def test_multiline_token_end_is_exact() -> None:
    payload = _program('val s = """a\nb"""\n')
    tokens = payload["tokens"]
    assert isinstance(tokens, list)
    string = next(token for token in tokens if token["type"] == "STRING")

    assert string["span"] == {
        "start": {"line": 1, "column": 9, "offset": 8},
        "end": {"line": 2, "column": 5, "offset": 17},
    }


def test_utf8_offsets_are_bytes_not_code_points() -> None:
    payload = _program('print("é")\n')
    tokens = payload["tokens"]
    assert isinstance(tokens, list)
    string = next(token for token in tokens if token["type"] == "STRING")

    # `print(` = 6 bytes; `"é"` = 4 bytes (2 quotes + 2 bytes of é).
    assert string["span"]["start"]["offset"] == 6
    assert string["span"]["end"]["offset"] == 10
    assert string["span"]["start"]["column"] == 7
    assert string["span"]["end"]["column"] == 10


def test_span_of_token_exact_handles_synthetic_token() -> None:
    token = Token(type=TokenType.NUMBER, lexeme="", literal=None, line=1)
    span = span_of_token_exact(token)

    assert span.start.line == 1
    assert span.end.line == 1
    assert span.end.offset == 0


def test_node_span_covers_children() -> None:
    payload = _program("print(1 + 2)\n")
    statements = payload["statements"]
    assert isinstance(statements, list)
    expression = statements[0]["expression"]

    assert expression["kind"] == "call"
    assert expression["span"] == {
        "start": {"line": 1, "column": 1, "offset": 0},
        "end": {"line": 1, "column": 13, "offset": 12},
    }
    assert expression["arguments"][0]["kind"] == "binary"


def test_construct_spans_include_keywords_and_delimiters() -> None:
    cases = {
        "if (true) { print(1) }\n": ("if", 23, 22),
        "class A {}\n": ("class", 11, 10),
        "{}\n": ("block", 3, 2),
        "type Alias = Int\n": ("type_alias", 17, 16),
        "var x: Int\n": ("var", 11, 10),
        "enum E { A }\n": ("enum_decl", 13, 12),
    }
    for source, (kind, end_column, end_offset) in cases.items():
        payload = _program(source)
        statements = payload["statements"]
        assert isinstance(statements, list)
        node = statements[0]

        assert node["kind"] == kind
        assert node["span"]["start"] == {"line": 1, "column": 1, "offset": 0}
        assert node["span"]["end"] == {
            "line": 1,
            "column": end_column,
            "offset": end_offset,
        }


def test_type_annotation_is_canonical_text() -> None:
    payload = _program("val xs: List[Int] = [1]\n")
    statements = payload["statements"]
    assert isinstance(statements, list)

    assert statements[0]["type_annotation"] == "List[Int]"


def test_interpolated_literal_serializes_embedded_tokens() -> None:
    payload = _program('print("a${1}b")\n')
    tokens = payload["tokens"]
    assert isinstance(tokens, list)
    string = next(token for token in tokens if token["type"] == "INTERPOLATED_STRING")

    assert isinstance(string["literal"], list)
    assert string["literal"][0] == "a"
    assert isinstance(string["literal"][1], list)
    assert string["literal"][1][0]["type"] == "NUMBER"
    assert string["literal"][2] == "b"


def test_embedded_tokens_are_compact_and_top_level_is_full() -> None:
    payload = _program("val x = 1\n")
    tokens = payload["tokens"]
    assert isinstance(tokens, list)
    assert "literal" in tokens[1]
    assert "doc" in tokens[1]

    statements = payload["statements"]
    assert isinstance(statements, list)
    embedded = statements[0]["name"]
    assert "type" in embedded
    assert "lexeme" in embedded
    assert "span" in embedded
    assert "literal" not in embedded
    assert "doc" not in embedded


def test_non_finite_float_is_marked_not_string() -> None:
    payload = _program("print(1e999)\n")
    statements = payload["statements"]
    assert isinstance(statements, list)
    argument = statements[0]["expression"]["arguments"][0]

    assert argument["value"] == {"non_finite_float": "inf"}


def test_synthetic_line_zero_is_rejected() -> None:
    token = Token(type=TokenType.NUMBER, lexeme="1", literal=1, line=0)
    statement = Expression(Literal(1, token))

    with pytest.raises(ValueError, match="synthetic line 0"):
        program_payload([statement], [token], "<repl>")


def test_crlf_offsets_follow_the_normalized_source() -> None:
    payload = _program("val x = 1\r\nprint(x)\r\n")
    tokens = payload["tokens"]
    assert isinstance(tokens, list)
    second_line = next(token for token in tokens if token["lexeme"] == "print")

    assert second_line["span"]["start"] == {"line": 2, "column": 1, "offset": 11}


def test_wildcard_pattern_is_serialized() -> None:
    payload = _program("match y { _ => 1 }\n")
    text = dumps(payload)

    assert '"kind": "wildcard_pattern"' in text


def test_empty_program_is_serialized() -> None:
    payload = _program("")
    tokens = payload["tokens"]
    assert isinstance(tokens, list)

    assert payload["statements"] == []
    assert [token["type"] for token in tokens] == ["EOF"]


def test_file_name_is_never_absolute(tmp_path: Path) -> None:
    script = tmp_path / "stdin.lx"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "main.py"),
            "ast",
            "--file-only",
            "--format=json",
            "--stdin",
            "--file-name",
            "/tmp/proj/main.lx",
        ],
        cwd=ROOT,
        input="print(1)\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["file"] == "main.lx"
    assert str(script) not in result.stdout


def test_file_only_ignores_a_nearby_manifest(tmp_path: Path) -> None:
    (tmp_path / "loxia.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    script = tmp_path / "main.lx"
    script.write_text("import no.such.module\nprint(1)\n", encoding="utf-8")

    result = _run("ast", "--file-only", str(script))

    assert result.returncode == 0, result.stderr
    assert "(import no.such.module)" in result.stdout


def test_json_is_deterministic() -> None:
    first = _program("class A { val x: Int; fn init() { this.x = 1 } }\n")
    second = _program("class A { val x: Int; fn init() { this.x = 1 } }\n")

    assert canonical(first) == canonical(second)
    assert dumps(first) == dumps(second)


def test_file_only_json_does_not_load_imports(tmp_path: Path) -> None:
    script = tmp_path / "imports.lx"
    script.write_text('import std.strings\nprint(trim(" x "))\n', encoding="utf-8")

    result = _run("ast", "--file-only", "--format=json", str(script))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["statements"][0]["kind"] == "import"
    assert "std$" not in result.stdout
    assert str(tmp_path) not in result.stdout


def test_json_requires_file_only(tmp_path: Path) -> None:
    script = tmp_path / "one.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    result = _run("ast", "--format=json", str(script))

    assert result.returncode == 2
    assert "--format=json requires --file-only" in result.stderr


def test_json_syntax_error_exits_65_without_ast(tmp_path: Path) -> None:
    script = tmp_path / "bad.lx"
    script.write_text("print(\n", encoding="utf-8")

    result = _run("ast", "--file-only", "--format=json", str(script))

    assert result.returncode == 65
    assert result.stdout == ""
    assert "Expect expression" in result.stderr


def test_flags_are_only_accepted_by_ast(tmp_path: Path) -> None:
    script = tmp_path / "one.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    commands = [
        ("--file-only", str(script)),
        ("--format=json", str(script)),
        ("run", "--file-only", str(script)),
        ("check", "--format=json", str(script)),
        ("fmt", "--file-only", str(script)),
    ]
    for arguments in commands:
        result = _run(*arguments)
        assert result.returncode == 2, (arguments, result.stdout, result.stderr)
        assert result.stdout == ""


def test_default_ast_still_loads_modules(tmp_path: Path) -> None:
    script = tmp_path / "imports.lx"
    script.write_text('import std.strings\nprint(trim(" x "))\n', encoding="utf-8")

    default = _run("ast", str(script))
    file_only = _run("ast", "--file-only", str(script))

    assert default.returncode == 0, default.stderr
    assert "std$strings$trim" in default.stdout
    assert "std$" not in file_only.stdout


def test_legacy_dump_ast_supports_file_only(tmp_path: Path) -> None:
    script = tmp_path / "one.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    sexp = _run("--dump-ast", "--file-only", str(script))
    json_result = _run("--dump-ast", "--file-only", "--format=json", str(script))

    assert sexp.returncode == 0
    assert sexp.stdout == "(expr (call print 1))\n"
    assert json_result.returncode == 0
    assert json.loads(json_result.stdout)["kind"] == "program"
