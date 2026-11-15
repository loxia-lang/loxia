from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from loxia import __version__

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
    script.write_text("""print(1 + 2);
""", encoding="utf-8")

    result = run_cli("--dump-ast", str(script))

    assert result.returncode == 0
    assert result.stdout.strip() == "(expr (call print (+ 1 2)))"


def test_dump_ast_syntax_error_exits_65(tmp_path: Path) -> None:
    script = tmp_path / "quebrado.lx"
    script.write_text("""print(1 + );
""", encoding="utf-8")

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


def test_check_conflicts_with_dump_ast(tmp_path: Path) -> None:
    script = tmp_path / "x.lx"
    script.write_text("""print(1);
""", encoding="utf-8")

    result = run_cli("--check", "--dump-ast", str(script))

    assert result.returncode == 2


def test_debug_flag_checks_overflow(tmp_path: Path) -> None:
    script = tmp_path / "overflow.lx"
    script.write_text("""print(9223372036854775807 + 1);
""", encoding="utf-8")

    debug = run_cli("--debug", str(script))
    release = run_cli(str(script))

    assert debug.returncode == 70
    assert "Integer overflow." in debug.stderr
    assert release.returncode == 0
    assert release.stdout.strip() == "-9223372036854775808"


# -- diagnósticos estruturados (ADR-0075) ---------------------------------


def test_error_format_short_is_one_line_per_diagnostic(tmp_path: Path) -> None:
    script = tmp_path / "erro.lx"
    script.write_text("""print(1 + );
""", encoding="utf-8")

    result = run_cli("--error-format=short", str(script))

    assert result.returncode == 65
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1
    assert lines[0] == "erro.lx:1:11: error[E1001]: Expect expression."


def test_error_format_human_includes_source_snippet(tmp_path: Path) -> None:
    script = tmp_path / "erro.lx"
    script.write_text("""print(1 + );
""", encoding="utf-8")

    result = run_cli(str(script))

    assert result.returncode == 65
    assert "erro.lx:1:11: error[E1001]: Expect expression." in result.stderr
    assert "  |\n" in result.stderr
    assert """1 | print(1 + );
""" in result.stderr
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
    script.write_text("""fn f(a: Int) -> Int { return a; }
print(f(1));
""", encoding="utf-8")

    result = run_cli("--check", "--error-format=json", str(script))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["diagnostics"] == []


def test_error_format_json_goes_to_stderr_on_run(tmp_path: Path) -> None:
    script = tmp_path / "boom.lx"
    script.write_text("""print(1 / 0);
""", encoding="utf-8")

    result = run_cli("--error-format=json", str(script))

    assert result.returncode == 70
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["command"] == "run"
    assert payload["diagnostics"][0]["code"] == "R1002"
    assert payload["diagnostics"][0]["message"] == "Division by zero not allowed"


def test_runtime_human_uses_the_same_header_as_compilation(tmp_path: Path) -> None:
    script = tmp_path / "boom.lx"
    script.write_text("""print(1 / 0);
""", encoding="utf-8")

    result = run_cli(str(script))

    assert result.returncode == 70
    assert result.stderr == (
        "boom.lx:1:9: error[R1002]: Division by zero not allowed\n"
    )


def test_color_always_emits_ansi_and_never_does_not(tmp_path: Path) -> None:
    script = tmp_path / "erro.lx"
    script.write_text("""print(1 + );
""", encoding="utf-8")

    colored = run_cli("--color=always", str(script))
    plain = run_cli("--color=never", str(script))

    assert "\x1b[" in colored.stderr
    assert "\x1b[" not in plain.stderr


def test_no_color_is_respected_in_auto_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "erro.lx"
    script.write_text("""print(1 + );
""", encoding="utf-8")
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
    script.write_text("""print(1 + );
""", encoding="utf-8")

    result = run_cli("--error-format=short", str(script))

    assert str(tmp_path) not in result.stderr
    assert result.stderr.startswith("fora.lx:1:11: ")
