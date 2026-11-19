# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from loxia import __version__
from loxia.cli_args import COMMANDS, _build_subcommand_parser, parse_heap_size
from loxia.cli_commands import HANDLERS

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_version_matches_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == __version__


def test_cli_version() -> None:
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == f"loxia {__version__}"


def test_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "loxia", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == f"loxia {__version__}"


def test_dump_ast_prints_and_does_not_execute(tmp_path: Path) -> None:
    script = tmp_path / "programa.lx"
    script.write_text(
        """print(1 + 2);
""",
        encoding="utf-8",
    )

    result = run_cli("--dump-ast", str(script))

    assert result.returncode == 0
    assert result.stdout.strip() == "(expr (call print (+ 1 2)))"


def test_dump_ast_syntax_error_exits_65(tmp_path: Path) -> None:
    script = tmp_path / "quebrado.lx"
    script.write_text(
        """print(1 + );
""",
        encoding="utf-8",
    )

    result = run_cli("--dump-ast", str(script))

    assert result.returncode == 65


def test_dump_ast_requires_script() -> None:
    result = run_cli("--dump-ast")

    assert result.returncode == 2


def test_check_annotated_program_does_not_execute(tmp_path: Path) -> None:
    script = tmp_path / "tipado.lx"
    script.write_text(
        """fn f(a: Int) -> Int { return a; }
print(f(1));
""",
        encoding="utf-8",
    )

    result = run_cli("--check", str(script))

    assert result.returncode == 0
    assert result.stdout == ""


def test_check_type_error_exits_65_without_executing(tmp_path: Path) -> None:
    script = tmp_path / "tipado.lx"
    script.write_text(
        """val x: Int = "a";
print("não devia imprimir");
""",
        encoding="utf-8",
    )

    result = run_cli("--check", str(script))

    assert result.returncode == 65
    assert result.stdout == ""
    assert "Expected Int, found String." in result.stderr


def test_check_requires_script() -> None:
    result = run_cli("--check")

    assert result.returncode == 2


def test_check_mostra_label_da_declaracao_anterior(tmp_path: Path) -> None:
    script = tmp_path / "dup.lx"
    script.write_text("fn f() {\n  val a = 1\n  val a = 2\n}\n", encoding="utf-8")

    result = run_cli("--check", str(script))

    assert result.returncode == 65
    assert "error[E2001]" in result.stderr
    assert "2 |   val a = 1\n" in result.stderr
    assert "  |       - first declared here\n" in result.stderr


def test_check_sugere_nome_proximo(tmp_path: Path) -> None:
    script = tmp_path / "sug.lx"
    script.write_text("val nome = 1\nprint(nom)\n", encoding="utf-8")

    result = run_cli("--check", str(script))

    assert result.returncode == 65
    assert "error[E3003]: Undefined variable 'nom'." in result.stderr
    assert "help: did you mean 'nome'?\n" in result.stderr


def test_check_conflicts_with_dump_ast(tmp_path: Path) -> None:
    script = tmp_path / "x.lx"
    script.write_text(
        """print(1);
""",
        encoding="utf-8",
    )

    result = run_cli("--check", "--dump-ast", str(script))

    assert result.returncode == 2


def test_debug_flag_checks_overflow(tmp_path: Path) -> None:
    script = tmp_path / "overflow.lx"
    script.write_text(
        """print(9223372036854775807 + 1);
""",
        encoding="utf-8",
    )

    debug = run_cli("--debug", str(script))
    release = run_cli(str(script))

    assert debug.returncode == 70
    assert "Integer overflow." in debug.stderr
    assert release.returncode == 0
    assert release.stdout.strip() == "-9223372036854775808"


# -- diagnósticos estruturados (ADR-0075) ---------------------------------


def test_error_format_short_is_one_line_per_diagnostic(tmp_path: Path) -> None:
    script = tmp_path / "erro.lx"
    script.write_text(
        """print(1 + );
""",
        encoding="utf-8",
    )

    result = run_cli("--error-format=short", str(script))

    assert result.returncode == 65
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1
    assert lines[0] == "erro.lx:1:11: error[E1001]: Expect expression."


def test_error_format_human_includes_source_snippet(tmp_path: Path) -> None:
    script = tmp_path / "erro.lx"
    script.write_text(
        """print(1 + );
""",
        encoding="utf-8",
    )

    result = run_cli(str(script))

    assert result.returncode == 65
    assert "erro.lx:1:11: error[E1001]: Expect expression." in result.stderr
    assert "  |\n" in result.stderr
    assert (
        """1 | print(1 + );
"""
        in result.stderr
    )
    assert "  |           ^\n" in result.stderr


def test_error_format_json_goes_to_stdout_on_check(tmp_path: Path) -> None:
    script = tmp_path / "tipado.lx"
    script.write_text('val x: Int = "a";\n', encoding="utf-8")

    result = run_cli("--check", "--error-format=json", str(script))

    assert result.returncode == 65
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["command"] == "check"
    assert payload["success"] is False
    assert payload["exit_code"] == 65
    assert payload["diagnostics"][0]["code"] == "E3001"
    assert payload["diagnostics"][0]["span"]["file"] == "tipado.lx"


def test_error_format_json_success_envelope_on_check(tmp_path: Path) -> None:
    script = tmp_path / "ok.lx"
    script.write_text(
        """fn f(a: Int) -> Int { return a; }
print(f(1));
""",
        encoding="utf-8",
    )

    result = run_cli("--check", "--error-format=json", str(script))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["diagnostics"] == []


def test_error_format_json_goes_to_stderr_on_run(tmp_path: Path) -> None:
    script = tmp_path / "boom.lx"
    script.write_text(
        """print(1 / 0);
""",
        encoding="utf-8",
    )

    result = run_cli("--error-format=json", str(script))

    assert result.returncode == 70
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["command"] == "run"
    assert payload["diagnostics"][0]["code"] == "R1002"
    assert payload["diagnostics"][0]["message"] == "Division by zero not allowed"


def test_runtime_human_uses_the_same_header_as_compilation(tmp_path: Path) -> None:
    script = tmp_path / "boom.lx"
    script.write_text(
        """print(1 / 0);
""",
        encoding="utf-8",
    )

    result = run_cli(str(script))

    assert result.returncode == 70
    assert result.stderr == ("boom.lx:1:9: error[R1002]: Division by zero not allowed\n")


def test_color_always_emits_ansi_and_never_does_not(tmp_path: Path) -> None:
    script = tmp_path / "erro.lx"
    script.write_text(
        """print(1 + );
""",
        encoding="utf-8",
    )

    colored = run_cli("--color=always", str(script))
    plain = run_cli("--color=never", str(script))

    assert "\x1b[" in colored.stderr
    assert "\x1b[" not in plain.stderr


def test_no_color_is_respected_in_auto_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "erro.lx"
    script.write_text(
        """print(1 + );
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NO_COLOR", "1")

    result = run_cli(str(script))

    assert "\x1b[" not in result.stderr


def test_max_errors_limits_and_reports_suppressed(tmp_path: Path) -> None:
    script = tmp_path / "muitos.lx"
    script.write_text(
        "{ var a = 1; var a = 2; var a = 3; var a = 4; }\n",
        encoding="utf-8",
    )

    result = run_cli("--check", "--max-errors=1", "--error-format=json", str(script))

    assert result.returncode == 65
    payload = json.loads(result.stdout)
    assert len(payload["diagnostics"]) == 1
    assert payload["summary"]["suppressed"] == 2


def test_diagnostics_use_basename_for_files_outside_cwd(tmp_path: Path) -> None:
    script = tmp_path / "fora.lx"
    script.write_text(
        """print(1 + );
""",
        encoding="utf-8",
    )

    result = run_cli("--error-format=short", str(script))

    assert str(tmp_path) not in result.stderr
    assert result.stderr.startswith("fora.lx:1:11: ")


def test_max_heap_requires_emit_exe(tmp_path: Path) -> None:
    script = tmp_path / "ok.lx"
    script.write_text("print(1);\n", encoding="utf-8")

    result = run_cli("--max-heap=128M", str(script))

    assert result.returncode == 2
    assert "--max-heap requires --emit=exe" in result.stderr


def test_parse_heap_size_accepts_units_and_bytes() -> None:
    assert parse_heap_size("512M") == 512 * 1024**2
    assert parse_heap_size("2g") == 2 * 1024**3
    assert parse_heap_size(str(64 * 1024**2)) == 64 * 1024**2


def test_parse_heap_size_rejects_invalid_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_heap_size("16M")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_heap_size("9G")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_heap_size("muito")


# -- subcomandos, agent-friendly e warnings (ADR-0093) --------------------


def test_subcommand_run_executes(tmp_path: Path) -> None:
    script = tmp_path / "run.lx"
    script.write_text("print(1 + 2)\n", encoding="utf-8")

    result = run_cli("run", str(script))

    assert result.returncode == 0
    assert result.stdout.strip() == "3"


def test_subcommand_check_matches_legacy(tmp_path: Path) -> None:
    script = tmp_path / "check.lx"
    script.write_text('val x: Int = "a"\n', encoding="utf-8")

    subcommand = run_cli("check", str(script))
    legacy = run_cli("--check", str(script))

    assert subcommand.returncode == legacy.returncode == 65
    assert subcommand.stderr == legacy.stderr


def test_subcommand_ast_matches_dump_ast(tmp_path: Path) -> None:
    script = tmp_path / "ast.lx"
    script.write_text("print(1 + 2)\n", encoding="utf-8")

    subcommand = run_cli("ast", str(script))
    legacy = run_cli("--dump-ast", str(script))

    assert subcommand.returncode == legacy.returncode == 0
    assert subcommand.stdout == legacy.stdout


def test_subcommand_build_emits_ir(tmp_path: Path) -> None:
    script = tmp_path / "build.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    result = run_cli("build", str(script), "--emit=ll")

    assert result.returncode == 0
    assert "ModuleID" in result.stdout


def test_json_is_alias_of_error_format_json(tmp_path: Path) -> None:
    script = tmp_path / "json.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    result = run_cli("check", str(script), "--json")

    assert result.returncode == 0
    assert json.loads(result.stdout)["success"] is True


def test_capabilities_json_is_deterministic() -> None:
    first = run_cli("capabilities", "--json")
    second = run_cli("capabilities", "--json")

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["schema_version"] == 1
    assert payload["program"] == "loxia"
    assert {"C0001", "W1001"} <= {item["code"] for item in payload["codes"]}
    assert payload["warnings"] == {"codes": ["W1001"], "werror": True}
    assert payload["fixes"]["implemented"] is True


def test_explain_known_and_unknown_code() -> None:
    known = run_cli("explain", "E2001")
    warning = run_cli("explain", "W1001")
    unknown = run_cli("explain", "NOPE")

    assert known.returncode == warning.returncode == 0
    assert "E2001" in known.stdout
    assert "warning" in warning.stdout or "W1001" in warning.stdout
    assert unknown.returncode == 2


def test_stdin_run_and_check_use_file_name(tmp_path: Path) -> None:
    run_result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "run", "--stdin"],
        cwd=ROOT,
        input="print(40 + 2)\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    check_result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "check", "--stdin", "--file-name", "entrada.lx"],
        cwd=ROOT,
        input="print(1 + )\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert run_result.returncode == 0
    assert run_result.stdout.strip() == "42"
    assert check_result.returncode == 65
    assert "entrada.lx:1:11" in check_result.stderr


def test_stdin_run_passes_script_args_after_double_dash() -> None:
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "run", "--stdin", "--", "alpha", "beta"],
        cwd=ROOT,
        input="print(args())\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == '["alpha", "beta"]'


def test_stdin_run_keeps_file_name_and_args_together() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "run",
            "--stdin",
            "--file-name",
            "demo.lx",
            "--",
            "--flag",
            "value",
        ],
        cwd=ROOT,
        input="print(args())\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == '["--flag", "value"]'


def test_stdin_check_still_rejects_a_script_positional() -> None:
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "check", "--stdin", "--", "a"],
        cwd=ROOT,
        input="print(1)\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 2
    assert "--stdin cannot be combined with a script" in result.stderr


def test_legacy_stdin_run_passes_script_args() -> None:
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--stdin", "--", "alpha", "beta"],
        cwd=ROOT,
        input="print(args())\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == '["alpha", "beta"]'


def _run_sandbox(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), "run", "--stdin", "--sandbox"],
        cwd=ROOT,
        input=source,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_sandbox_allows_pure_programs() -> None:
    result = _run_sandbox("print(1 + 2)\n")

    assert result.returncode == 0
    assert result.stdout.strip() == "3"


def test_sandbox_denies_filesystem_and_process_primitives() -> None:
    cases = {
        'io.writeFile("x", "y")\n': "io.writeFile() is not available in sandbox mode.",
        'io.readFile("README.md")\n': "io.readFile() is not available in sandbox mode.",
        'fs.exists("README.md")\n': "fs.exists() is not available in sandbox mode.",
        'process.spawn(["true"])\n': "process.spawn() is not available in sandbox mode.",
    }
    for source, message in cases.items():
        result = _run_sandbox(source)
        assert result.returncode == 70, source
        assert message in result.stderr, (source, result.stderr)


def test_json_lines_check_has_start_diagnostic_summary(tmp_path: Path) -> None:
    script = tmp_path / "linhas.lx"
    script.write_text("print(1 + )\n", encoding="utf-8")

    result = run_cli("check", str(script), "--json-lines")

    assert result.returncode == 65
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [event["event"] for event in events] == [
        "start",
        "diagnostic",
        "summary",
    ]
    assert events[1]["code"] == "E1001"
    assert events[2]["revision"] == 0


def test_json_lines_conflicts_with_error_format(tmp_path: Path) -> None:
    script = tmp_path / "linhas.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    result = run_cli("check", str(script), "--json-lines", "--error-format=short")

    assert result.returncode == 2


def test_timeout_exits_124_with_c0001(tmp_path: Path) -> None:
    script = tmp_path / "loop.lx"
    script.write_text("while (true) {\n}\n", encoding="utf-8")

    result = run_cli("run", str(script), "--timeout=50", "--json")

    assert result.returncode == 124
    payload = json.loads(result.stderr)
    assert payload["exit_code"] == 124
    assert payload["diagnostics"][0]["code"] == "C0001"


def test_timeout_json_lines_emits_c0001(tmp_path: Path) -> None:
    script = tmp_path / "loop.lx"
    script.write_text("while (true) {\n}\n", encoding="utf-8")

    result = run_cli("run", str(script), "--timeout=50", "--json-lines")

    assert result.returncode == 124
    events = [json.loads(line) for line in result.stderr.splitlines()]
    assert [event["event"] for event in events] == [
        "start",
        "diagnostic",
        "summary",
    ]
    assert events[1]["code"] == "C0001"


def test_watch_is_restricted_to_check(tmp_path: Path) -> None:
    script = tmp_path / "w.lx"
    script.write_text("print(1)\n", encoding="utf-8")

    with_timeout = run_cli("check", str(script), "--watch", "--timeout=10")
    run_watch = run_cli("run", str(script), "--watch")

    assert with_timeout.returncode == 2
    assert run_watch.returncode == 2


def test_unused_local_warns_but_does_not_fail(tmp_path: Path) -> None:
    script = tmp_path / "warn.lx"
    script.write_text(
        "fn f() -> Int {\n  val x = 1\n  return 2\n}\nprint(f())\n",
        encoding="utf-8",
    )

    result = run_cli("check", str(script))

    assert result.returncode == 0
    assert "warning[W1001]" in result.stderr


def test_werror_turns_warning_into_error(tmp_path: Path) -> None:
    script = tmp_path / "warn.lx"
    script.write_text(
        "fn f() -> Int {\n  val x = 1\n  return 2\n}\nprint(f())\n",
        encoding="utf-8",
    )

    result = run_cli("check", str(script), "-Werror")

    assert result.returncode == 65
    assert "error[W1001]" in result.stderr


def test_run_never_emits_warnings(tmp_path: Path) -> None:
    script = tmp_path / "warn.lx"
    script.write_text(
        "fn f() -> Int {\n  val x = 1\n  return 2\n}\nprint(f())\n",
        encoding="utf-8",
    )

    result = run_cli("run", str(script))

    assert result.returncode == 0
    assert "W1001" not in result.stderr


def test_watch_emits_initial_snapshot_and_can_be_stopped(tmp_path: Path) -> None:
    script = tmp_path / "watch.lx"
    script.write_text("print(1 + )\n", encoding="utf-8")

    process = subprocess.Popen(
        [
            sys.executable,
            str(ENTRYPOINT),
            "check",
            str(script),
            "--watch",
            "--json-lines",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        events = [json.loads(process.stdout.readline()) for _ in range(3)]
    finally:
        process.terminate()
        process.wait(timeout=5)

    assert [event["event"] for event in events] == [
        "start",
        "diagnostic",
        "summary",
    ]
    assert events[1]["code"] == "E1001"
    assert events[2]["revision"] == 0


# -- doc comments e lox doc (ADR-0091) ------------------------------------


def test_doc_json_from_stdin_has_signature_and_docs() -> None:
    source = """/// Adds two ints.
fn add(a: Int, b: Int) -> Int {
  return a + b
}

/// A point.
class Point {
  /// x coordinate.
  val x: Int
}
"""
    result = subprocess.run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "doc",
            "--stdin",
            "--file-name",
            "api.lx",
            "--json",
        ],
        cwd=ROOT,
        input=source,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["source"] == "api.lx"
    symbols = {item["name"]: item for item in payload["symbols"]}
    assert symbols["add"]["signature"] == "fn add(a: Int, b: Int) -> Int"
    assert symbols["add"]["doc"] == "Adds two ints."
    assert symbols["Point"]["doc"] == "A point."
    assert symbols["x"]["doc"] == "x coordinate."
    assert symbols["x"]["container"] == "Point"


def test_doc_does_not_execute_or_include_imported_modules(tmp_path: Path) -> None:
    script = tmp_path / "api.lx"
    script.write_text("/// Main.\nfn main() {\n  print(1)\n}\n", encoding="utf-8")

    result = run_cli("doc", str(script))

    assert result.returncode == 0
    assert "fn main()" in result.stdout
    assert "1\n" not in result.stdout


def test_doc_syntax_error_exits_65(tmp_path: Path) -> None:
    script = tmp_path / "quebrado.lx"
    script.write_text("/// quebrado\nfn (\n", encoding="utf-8")

    result = run_cli("doc", str(script))

    assert result.returncode == 65


def test_doc_requires_script_or_stdin() -> None:
    result = run_cli("doc")

    assert result.returncode == 2


def test_doc_comment_blank_line_breaks_attachment(tmp_path: Path) -> None:
    from loxia_core.diagnostics.error_reporter import ErrorReporter
    from loxia_core.frontend.parser import Parser
    from loxia_core.frontend.scanner import Scanner
    from loxia_core.frontend.stmt import Function

    source = """/// orphan

fn f() -> Int {
  return 1
}
"""
    reporter = ErrorReporter()
    tokens = Scanner(source, reporter).scan_tokens()
    statements = Parser(tokens, reporter=reporter).parse()

    assert statements is not None
    assert len(statements) == 1
    assert isinstance(statements[0], Function)
    assert statements[0].doc is None


def test_doc_covers_interface_enum_type_alias_and_method() -> None:
    source = """/// A shape.
interface Shape {
  /// Area.
  fn area() -> Float
}

/// Colors.
enum Cor {
  /// Yellow.
  AMARELO
}

/// A name.
type Nome = String

/// A box.
class Box {
  /// The value.
  var value: Int
}
"""
    result = subprocess.run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "doc",
            "--stdin",
            "--file-name",
            "api.lx",
            "--json",
        ],
        cwd=ROOT,
        input=source,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    symbols = {item["name"]: item for item in payload["symbols"]}
    assert symbols["Shape"]["doc"] == "A shape."
    assert symbols["area"]["doc"] == "Area."
    assert symbols["area"]["container"] == "Shape"
    assert symbols["Cor"]["doc"] == "Colors."
    assert symbols["AMARELO"]["doc"] == "Yellow."
    assert symbols["Nome"]["kind"] == "type"
    assert symbols["value"]["container"] == "Box"


def _run_repl(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), "repl", *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_repl_subcommand_runs_piped_program_without_banner() -> None:
    result = _run_repl("print(1 + 1)\n")

    assert result.returncode == 0
    assert result.stdout == "2\n"
    assert "REPL" not in result.stdout
    assert "Saindo" not in result.stdout


def test_repl_subcommand_keeps_session_after_syntax_error() -> None:
    result = _run_repl("print(\nprint(2)\n")

    assert result.returncode == 0
    assert result.stdout == "2\n"
    assert "error[E1001]" in result.stderr


def test_repl_subcommand_accepts_common_flags_and_rejects_a_script() -> None:
    result = _run_repl("print(1)\n", "--error-format", "short")
    assert result.returncode == 0
    assert result.stdout == "1\n"

    rejected = run_cli("repl", str(ROOT / "examples" / "fib.lx"))
    assert rejected.returncode == 2
    assert "unrecognized arguments" in rejected.stderr


def test_bare_loxia_with_piped_stdin_is_silent_like_loxia_repl() -> None:
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT)],
        cwd=ROOT,
        input="print(3)\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "3\n"


def test_capabilities_lists_the_repl_subcommand() -> None:
    payload = json.loads(run_cli("capabilities", "--json").stdout)

    commands = {item["name"] for item in payload["commands"]}
    assert "repl" in commands


def test_help_do_topo_lista_comandos_sem_as_flags_do_modo_compativel() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    assert "loxia <comando> [opções]" in result.stdout
    assert "loxia <comando> --help" in result.stdout
    for command in COMMANDS:
        assert command in result.stdout

    before_compat = result.stdout.split("modo compatível:", 1)[0]
    for flag in ("--dump-ast", "--check", "--emit", "--max-heap", "--stdin", "--watch"):
        assert flag not in before_compat


def test_help_do_topo_resume_o_modo_compativel() -> None:
    compat = run_cli("--help").stdout.split("modo compatível:", 1)[1]

    assert "--dump-ast" in compat
    assert "--emit" in compat
    assert "--watch" in compat


def test_help_de_cada_comando_mostra_so_as_suas_flags() -> None:
    run_help = run_cli("run", "--help")

    assert run_help.returncode == 0
    assert "executa um script Loxia" in run_help.stdout
    assert "módulos e dependências" in run_help.stdout
    assert "exemplos:" in run_help.stdout
    assert "--watch" not in run_help.stdout

    check_help = run_cli("check", "--help").stdout
    assert "--watch" in check_help
    assert "--emit" not in check_help

    fmt_help = run_cli("fmt", "--help").stdout
    assert "--timeout" not in fmt_help
    assert "options:" not in fmt_help


def test_todo_comando_tem_handler_e_parser() -> None:
    assert set(HANDLERS) == set(COMMANDS)
    for command in COMMANDS:
        assert _build_subcommand_parser(command).prog == f"loxia {command}"
