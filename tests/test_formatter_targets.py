# SPDX-License-Identifier: MIT OR Apache-2.0
"""`fmt` com múltiplos paths e diretórios (resolver + CLI)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loxia.formatter.targets import (
    TargetError,
    TargetNotFoundError,
    resolve_targets,
)

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def run_cli(
    *args: str,
    cwd: Path = ROOT,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def make_tree(root: Path) -> None:
    (root / "a.lx").write_text("val a=1\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.lx").write_text("val b=2\n", encoding="utf-8")
    (root / "sub" / "not_lox.txt").write_text("x\n", encoding="utf-8")
    (root / "skip").mkdir()
    (root / "skip" / "c.lx").write_text("val c=3\n", encoding="utf-8")
    (root / "errors").mkdir()
    (root / "errors" / "bad.lx").write_text("val =\n", encoding="utf-8")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "d.lx").write_text("val d=4\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "e.lx").write_text("val e=5\n", encoding="utf-8")


def test_resolve_orders_deduplicates_and_skips_defaults(tmp_path: Path) -> None:
    make_tree(tmp_path)

    resolved = resolve_targets([str(tmp_path), str(tmp_path / "a.lx")], cwd=tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in resolved] == [
        "a.lx",
        "errors/bad.lx",
        "skip/c.lx",
        "sub/b.lx",
    ]


def test_resolve_excludes_discovered_but_not_explicit(tmp_path: Path) -> None:
    make_tree(tmp_path)

    resolved = resolve_targets([str(tmp_path)], excludes=["errors/**", "skip/**"], cwd=tmp_path)
    assert [path.relative_to(tmp_path).as_posix() for path in resolved] == [
        "a.lx",
        "sub/b.lx",
    ]

    explicit = resolve_targets(
        [str(tmp_path / "errors" / "bad.lx")], excludes=["errors/**"], cwd=tmp_path
    )
    assert explicit == [tmp_path / "errors" / "bad.lx"]


def test_resolve_reports_missing_and_empty(tmp_path: Path) -> None:
    with pytest.raises(TargetNotFoundError):
        resolve_targets([str(tmp_path / "missing.lx")], cwd=tmp_path)

    (tmp_path / "empty").mkdir()
    with pytest.raises(TargetError, match=r"no \.lx files found"):
        resolve_targets([str(tmp_path / "empty")], cwd=tmp_path)


def test_cli_check_multi_is_silent_and_does_not_write(tmp_path: Path) -> None:
    make_tree(tmp_path)

    result = run_cli("fmt", "--check", ".", "--exclude", "**/errors/**", cwd=tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == ""
    assert (tmp_path / "a.lx").read_text(encoding="utf-8") == "val a=1\n"


def test_cli_write_is_all_or_nothing_on_parse_error(tmp_path: Path) -> None:
    make_tree(tmp_path)

    result = run_cli("fmt", ".", cwd=tmp_path)

    assert result.returncode == 65
    assert "bad.lx:1:" in result.stderr
    assert "E1001" in result.stderr
    assert (tmp_path / "a.lx").read_text(encoding="utf-8") == "val a=1\n"
    assert (tmp_path / "skip" / "c.lx").read_text(encoding="utf-8") == "val c=3\n"


def test_cli_write_formats_valid_targets(tmp_path: Path) -> None:
    make_tree(tmp_path)

    result = run_cli(
        "fmt", ".", "--exclude", "**/errors/**", "--exclude", "**/skip/**", cwd=tmp_path
    )

    assert result.returncode == 0
    assert (tmp_path / "a.lx").read_text(encoding="utf-8") == "val a = 1\n"
    assert (tmp_path / "sub" / "b.lx").read_text(encoding="utf-8") == "val b = 2\n"
    assert (tmp_path / "skip" / "c.lx").read_text(encoding="utf-8") == "val c=3\n"


def test_cli_diff_multi_has_one_header_per_file(tmp_path: Path) -> None:
    make_tree(tmp_path)

    result = run_cli(
        "fmt", "--diff", ".", "--exclude", "**/errors/**", "--exclude", "**/skip/**", cwd=tmp_path
    )

    assert result.returncode == 1
    assert "--- a/a.lx" in result.stdout
    assert "--- a/sub/b.lx" in result.stdout
    assert result.stdout.index("--- a/a.lx") < result.stdout.index("--- a/sub/b.lx")
    assert (tmp_path / "a.lx").read_text(encoding="utf-8") == "val a=1\n"


def test_cli_exclude_removes_invalid_fixture_from_check(tmp_path: Path) -> None:
    make_tree(tmp_path)

    result = run_cli("fmt", "--check", ".", "--exclude", "errors/**", cwd=tmp_path)

    assert result.returncode == 1
    assert "bad.lx" not in result.stderr


def test_cli_parse_error_names_the_file(tmp_path: Path) -> None:
    make_tree(tmp_path)

    result = run_cli("fmt", "--check", "errors/bad.lx", cwd=tmp_path)

    assert result.returncode == 65
    assert "bad.lx:1:" in result.stderr


def test_cli_edits_requires_exactly_one_file(tmp_path: Path) -> None:
    make_tree(tmp_path)

    result = run_cli(
        "fmt", "--check", "--edits=json", ".", "--exclude", "**/errors/**", cwd=tmp_path
    )

    assert result.returncode == 2
    assert "requires exactly one file" in result.stderr


def test_cli_edits_accepts_one_discovered_file(tmp_path: Path) -> None:
    (tmp_path / "only.lx").write_text("val x=1\n", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("x\n", encoding="utf-8")

    result = run_cli("fmt", "--check", "--edits=json", ".", cwd=tmp_path)

    assert result.returncode == 1
    assert '"file": "only.lx"' in result.stdout


def test_cli_rejects_stdin_with_paths_and_empty_directory(tmp_path: Path) -> None:
    result = run_cli("fmt", "--stdin", "a.lx", cwd=tmp_path, input_text="val x = 1\n")
    assert result.returncode == 2
    assert "--stdin cannot be combined with paths" in result.stderr

    (tmp_path / "empty").mkdir()
    result = run_cli("fmt", "--check", "empty", cwd=tmp_path)
    assert result.returncode == 2
    assert "no .lx files found" in result.stderr


def test_cli_json_multi_is_one_document(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "bad.lx").write_text("val =\n", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "bad.lx").write_text("val =\n", encoding="utf-8")

    result = run_cli("fmt", "--check", "--json", ".", cwd=tmp_path)

    assert result.returncode == 65
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert {item["span"]["file"] for item in payload["diagnostics"]} == {
        "a/bad.lx",
        "b/bad.lx",
    }


def test_cli_json_lines_multi_has_one_summary(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "bad.lx").write_text("val =\n", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "bad.lx").write_text("val =\n", encoding="utf-8")

    result = run_cli("fmt", "--check", "--json-lines", ".", cwd=tmp_path)

    assert result.returncode == 65
    events = [json.loads(line) for line in result.stderr.splitlines() if line.strip()]
    assert [event["event"] for event in events] == [
        "start",
        "diagnostic",
        "diagnostic",
        "summary",
    ]
    assert events[-1]["errors"] == 2
    assert {event["span"]["file"] for event in events if event["event"] == "diagnostic"} == {
        "a/bad.lx",
        "b/bad.lx",
    }


def test_cli_diff_disambiguates_same_basename_outside_cwd(tmp_path: Path) -> None:
    first = tmp_path / "one" / "same.lx"
    second = tmp_path / "two" / "same.lx"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("val a=1\n", encoding="utf-8")
    second.write_text("val b=2\n", encoding="utf-8")

    result = run_cli("fmt", "--diff", str(first), str(second))

    assert result.returncode == 1
    headers = [line for line in result.stdout.splitlines() if line.startswith("--- a/")]
    assert len(headers) == 2
    assert len(set(headers)) == 2
    assert all("one/same.lx" in header or "two/same.lx" in header for header in headers)
