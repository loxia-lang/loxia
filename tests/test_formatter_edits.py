# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from loxia.formatter import format_source
from loxia.formatter.edits import (
    EditPosition,
    TextEdit,
    apply_edits,
    build_edits,
    unified_diff,
)

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def run_cli(
    *args: str,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=env,
    )


def formatted(source: str) -> str:
    result = format_source(source)
    assert result is not None
    return result.text


def edits_from_payload(payload: dict[str, Any]) -> tuple[TextEdit, ...]:
    raw = cast(list[dict[str, Any]], payload["edits"])
    return tuple(
        TextEdit(
            start=EditPosition(**cast(dict[str, int], item["start"])),
            end=EditPosition(**cast(dict[str, int], item["end"])),
            new_text=cast(str, item["newText"]),
        )
        for item in raw
    )


def test_canonical_source_has_no_edits() -> None:
    source = "fn f() {\n  return 1\n}\n"

    assert formatted(source) == source
    assert build_edits(source, source) == ()


def test_edits_apply_to_formatted_text() -> None:
    cases = [
        "fn f( a:Int,b:Int )->Int{return a+b;}\n",
        'print( "😀" );\n',
        "class C {\n  val x: Int\n  fn m() { return this.x }\n}\n",
        "val xs = [\n  1,\n  2\n]\n",
        "# comment\nfn f() {\n    return 1 # trailing\n}\n",
        "",
    ]

    for source in cases:
        target = formatted(source)
        edits = build_edits(source, target)
        assert apply_edits(source, edits) == target


def test_edit_positions_are_byte_offsets_and_code_point_columns() -> None:
    source = 'print( "José😀" );\n'
    target = formatted(source)
    edits = build_edits(source, target)
    assert edits

    for edit in edits:
        start_prefix = source.encode("utf-8")[: edit.start.offset].decode("utf-8")
        end_prefix = source.encode("utf-8")[: edit.end.offset].decode("utf-8")
        assert edit.start.line == start_prefix.count("\n") + 1
        assert edit.start.column == len(start_prefix.rsplit("\n", 1)[-1]) + 1
        assert edit.end.line == end_prefix.count("\n") + 1
        assert edit.end.column == len(end_prefix.rsplit("\n", 1)[-1]) + 1


def test_crlf_source_is_rewritten_to_lf() -> None:
    source = "fn f() {\r\n    return 1;\r\n}\r\n"
    target = formatted(source)

    assert "\r" not in target
    assert apply_edits(source, build_edits(source, target)) == target


def test_unified_diff_has_no_timestamp_or_absolute_path() -> None:
    source = "fn f( a:Int ){return a;}\n"
    target = formatted(source)
    diff = unified_diff("src/main.lx", source, target)

    assert diff.startswith("--- a/src/main.lx\n+++ b/src/main.lx\n")
    assert "@@ -1" in diff
    assert "2026" not in diff
    assert "/home/" not in diff


def test_build_edits_is_deterministic() -> None:
    source = "val xs = [\n  1,\n  2\n]\n"
    target = formatted(source)

    assert build_edits(source, target) == build_edits(source, target)


def test_cli_edits_json_does_not_write(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    source = "fn f( a:Int )->Int{return a;}\n"
    script.write_text(source, encoding="utf-8")

    result = run_cli("fmt", "--check", "--edits=json", str(script))

    assert result.returncode == 1
    payload = cast(dict[str, Any], json.loads(result.stdout))
    assert payload["changed"] is True
    assert payload["max_width"] == 100
    assert payload["file"] == "a.lx"
    assert apply_edits(source, edits_from_payload(payload)) == formatted(source)
    assert script.read_text(encoding="utf-8") == source


def test_cli_edits_json_canonical_file_has_empty_list(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    source = "fn f() {\n  return 1\n}\n"
    script.write_text(source, encoding="utf-8")

    result = run_cli("fmt", "--check", "--edits=json", str(script))

    assert result.returncode == 0
    payload = cast(dict[str, Any], json.loads(result.stdout))
    assert payload["changed"] is False
    assert payload["edits"] == []


def test_cli_edits_json_requires_check(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    result = run_cli("fmt", "--edits=json", str(script))

    assert result.returncode == 2


def test_cli_diff_prints_unified_diff_and_does_not_write(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    source = "fn f( a:Int ){return a;}\n"
    script.write_text(source, encoding="utf-8")

    result = run_cli("fmt", "--diff", str(script))

    assert result.returncode == 1
    assert result.stdout.startswith("--- a/a.lx\n+++ b/a.lx\n")
    assert str(tmp_path) not in result.stdout
    assert script.read_text(encoding="utf-8") == source


def test_cli_diff_canonical_file_prints_nothing(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    script.write_text("fn f() {\n  return 1\n}\n", encoding="utf-8")

    result = run_cli("fmt", "--diff", str(script))

    assert result.returncode == 0
    assert result.stdout == ""


def test_cli_diff_and_edits_are_mutually_exclusive(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    result = run_cli("fmt", "--check", "--diff", "--edits=json", str(script))

    assert result.returncode == 2


def test_json_positions_use_lf_line_boundaries() -> None:
    for separator in ("\x0c", "\u2028", "\u2029"):
        source = f'val s = "a{separator}b";\n'
        target = formatted(source)
        edits = build_edits(source, target)

        assert edits
        assert edits[0].start.line == 1
        assert apply_edits(source, edits) == target


def test_cli_edits_json_file_name_is_not_absolute() -> None:
    result = run_cli(
        "fmt",
        "--stdin",
        "--file-name",
        "/tmp/abs/thing.lx",
        "--check",
        "--edits=json",
        input_text="val x=1\n",
    )

    assert result.returncode == 1
    payload = cast(dict[str, Any], json.loads(result.stdout))
    assert payload["file"] == "thing.lx"
    assert "/tmp" not in result.stdout


def test_cli_diff_shows_final_newline_change(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    script.write_text("print(1)", encoding="utf-8")

    result = run_cli("fmt", "--diff", str(script))

    assert result.returncode == 1
    assert "No newline at end of file" in result.stdout
    assert "print(1)" in result.stdout
    assert script.read_text(encoding="utf-8") == "print(1)"


def test_cli_diff_stdin_label_is_stable() -> None:
    result = run_cli("fmt", "--stdin", "--diff", input_text="print(1)")

    assert result.returncode == 1
    assert result.stdout.startswith("--- a/<stdin>\n+++ b/<stdin>\n")


def test_cli_output_is_deterministic_across_hash_seeds(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    source = "fn f( a:Int )->Int{return a;}\n"
    script.write_text(source, encoding="utf-8")
    outputs: list[tuple[str, str, int, int]] = []

    for seed in ("0", "11", "23"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        diff = run_cli("fmt", "--diff", str(script), env=env)
        edits = run_cli("fmt", "--check", "--edits=json", str(script), env=env)
        outputs.append((diff.stdout, edits.stdout, diff.returncode, edits.returncode))

    assert len(set(outputs)) == 1
    assert script.read_text(encoding="utf-8") == source
