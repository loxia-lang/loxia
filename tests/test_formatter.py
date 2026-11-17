# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loxia.formatter import format_source

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def run_cli(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_fmt_normalizes_indentation_and_semicolon() -> None:
    source = "fn f() -> Int {\n    return 1;\n}\n"

    result = format_source(source)

    assert result is not None
    assert result.text == "fn f() -> Int {\n  return 1\n}\n"
    assert result.changed is True


def test_fmt_is_idempotent() -> None:
    source = "class C {\n      val x: Int;\n}\n"

    first = format_source(source)
    assert first is not None
    second = format_source(first.text)

    assert second is not None
    assert second.text == first.text
    assert second.changed is False


def test_fmt_preserves_doc_comment_and_multiline_string() -> None:
    source = '''/// Doc da classe.
class C {
    /// Doc do campo.
    val x: Int
    val text = """linha
  preservada
  
"""
}
'''

    result = format_source(source)

    assert result is not None
    assert "  /// Doc do campo." in result.text
    assert '"""linha\n  preservada\n  \n"""' in result.text


def test_fmt_preserves_continuation_indent_inside_parens() -> None:
    source = "fn f(\n    a: Int,\n    b: Int\n) -> Int {\n    return a + b;\n}\n"

    result = format_source(source)

    assert result is not None
    assert "    a: Int," in result.text
    assert "    b: Int" in result.text
    assert "  return a + b\n" in result.text


def test_fmt_check_exit_codes(tmp_path: Path) -> None:
    script = tmp_path / "fmt.lx"
    script.write_text("fn f() -> Int {\n    return 1;\n}\n", encoding="utf-8")

    dirty = run_cli("fmt", "--check", str(script))
    written = run_cli("fmt", str(script))
    clean = run_cli("fmt", "--check", str(script))

    assert dirty.returncode == 1
    assert written.returncode == 0
    assert clean.returncode == 0
    assert script.read_text(encoding="utf-8") == "fn f() -> Int {\n  return 1\n}\n"


def test_fmt_stdin_writes_formatted_output() -> None:
    result = run_cli("fmt", "--stdin", input_text="fn f() -> Int {\n    return 1;\n}\n")

    assert result.returncode == 0
    assert result.stdout == "fn f() -> Int {\n  return 1\n}\n"


def test_fmt_parse_error_exits_65() -> None:
    result = run_cli("fmt", "--stdin", input_text="fn (\n")

    assert result.returncode == 65


def test_fmt_insere_fn_canonico_em_metodo() -> None:
    source = "class C {\n  m() -> Int {\n    return 1\n  }\n}\n"

    result = format_source(source)

    assert result is not None
    assert "  fn m() -> Int {" in result.text
    again = format_source(result.text)
    assert again is not None
    assert again.text == result.text
    assert again.changed is False


def test_fmt_trailing_comma_multiline() -> None:
    source = "fn f(\n  a: Int,\n  b: Int\n) -> Int {\n  return g(\n    a,\n    b\n  )\n}\n"

    result = format_source(source)

    assert result is not None
    assert "  b: Int,\n)" in result.text
    assert "    b,\n  )" in result.text
    again = format_source(result.text)
    assert again is not None
    assert again.text == result.text


def test_fmt_trailing_comma_em_lista_mapa_tupla() -> None:
    source = (
        'val xs = [\n  1,\n  2\n]\nval m = {\n  "a": 1,\n  "b": 2\n}\nval t = (\n  1,\n  2\n)\n'
    )

    result = format_source(source)

    assert result is not None
    assert "  2,\n]" in result.text
    assert '  "b": 2,\n}' in result.text
    assert "  2,\n)" in result.text


def test_fmt_nao_coloca_virgula_em_grouping_ou_linha_unica() -> None:
    source = "val x = (\n  1 + 2\n)\nval y = f(1, 2)\n"

    result = format_source(source)

    assert result is not None
    assert "  1 + 2\n)" in result.text
    assert "f(1, 2)" in result.text
