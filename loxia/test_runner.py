# SPDX-License-Identifier: MIT OR Apache-2.0
"""Runner `lox test`: descobre `*_test.lx`, roda cada unidade e agrega TAP (ADR-0096).

`--isolate=file` (padrão) roda um subprocesso por arquivo; `--isolate=test` lista os
nomes (`--list`) e roda um subprocesso por teste (`--only`), com `--jobs` processos em
paralelo. O relatório humano é TAP com numeração global; `--json` emite o mesmo conteúdo
em envelope estável, sem duração/timestamp (I3).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".uv-cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)
_TAP_HEAD = re.compile(r"^(ok|not ok) (\d+) - (.*)$")


@dataclass(frozen=True)
class TestResult:
    """Um teste individual, já normalizado para o relatório."""

    file: str
    name: str
    status: str  # pass | fail | skip
    message: str = ""


@dataclass
class FileRun:
    """Resultados de um arquivo (uma unidade ou o agregado do isolamento por teste)."""

    path: Path
    results: list[TestResult] = field(default_factory=list)


@dataclass(frozen=True)
class Invocation:
    """Saída bruta de um subprocesso."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def discover(paths: list[str]) -> list[Path]:
    """Expande arquivos e diretórios em `*_test.lx` ordenados."""
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            if path.suffix == ".lx":
                files.append(path)
            continue
        if not path.is_dir():
            raise FileNotFoundError(raw)
        for candidate in path.rglob("*_test.lx"):
            if any(part in SKIP_DIRS or part.startswith(".tmp") for part in candidate.parts):
                continue
            files.append(candidate)
    return sorted(set(files))


def _parse_tap(path: Path, stdout: str, returncode: int) -> list[TestResult]:
    results: list[TestResult] = []
    current: TestResult | None = None
    diagnostics: list[str] = []
    for line in stdout.splitlines():
        match = _TAP_HEAD.match(line)
        if match is None:
            if current is not None and line.startswith("  # "):
                diagnostics.append(line[4:])
            continue
        if current is not None and diagnostics:
            results[-1] = TestResult(
                current.file,
                current.name,
                current.status,
                "\n".join(diagnostics),
            )
        diagnostics = []
        kind, _number, body = match.groups()
        name, _sep, skip = body.partition(" # SKIP ")
        status = "skip" if skip else ("pass" if kind == "ok" else "fail")
        current = TestResult(_display(path), name, status, skip)
        results.append(current)
    if current is not None and diagnostics:
        results[-1] = TestResult(current.file, current.name, current.status, "\n".join(diagnostics))
    if returncode != 0 and not any(item.status == "fail" for item in results):
        results.append(
            TestResult(
                _display(path),
                f"<{_display(path)}>",
                "fail",
                f"exit {returncode}",
            )
        )
    return results


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _invoke(
    path: Path,
    script_args: list[str],
    binary: str | None,
    timeout_s: float | None,
) -> Invocation:
    command = (
        [binary] if binary is not None else [sys.executable, "-m", "loxia", "run", str(path), "--"]
    )
    command = [*command, *script_args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return Invocation(124, _text(expired.stdout), _text(expired.stderr), True)
    return Invocation(completed.returncode, completed.stdout, completed.stderr)


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _build(path: Path, binary: Path) -> str | None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "loxia",
            "build",
            str(path),
            "-o",
            str(binary),
            "--emit=exe",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return None
    return _last_line(completed.stderr or completed.stdout) or "native build failed"


def _file_failure(path: Path, reason: str) -> FileRun:
    display = _display(path)
    return FileRun(path, [TestResult(display, f"<{display}>", "fail", reason)])


def _run_file_unit(
    path: Path,
    binary: str | None,
    build_error: str | None,
    script_args: list[str],
    timeout_s: float | None,
) -> FileRun:
    if build_error is not None:
        return _file_failure(path, build_error)
    invocation = _invoke(path, script_args, binary, timeout_s)
    if invocation.timed_out:
        return _file_failure(path, "timeout")
    return FileRun(path, _parse_tap(path, invocation.stdout, invocation.returncode))


def _list_names(
    path: Path,
    binary: str | None,
    build_error: str | None,
    script_args: list[str],
    timeout_s: float | None,
) -> tuple[list[str], str | None]:
    if build_error is not None:
        return [], build_error
    invocation = _invoke(path, ["--list", *script_args], binary, timeout_s)
    if invocation.timed_out:
        return [], "timeout"
    if invocation.returncode != 0:
        return [], _last_line(invocation.stderr) or f"exit {invocation.returncode}"
    names = [
        line[len("# test ") :]
        for line in invocation.stdout.splitlines()
        if line.startswith("# test ")
    ]
    return names, None


def _run_single_test(
    path: Path,
    name: str,
    binary: str | None,
    timeout_s: float | None,
) -> TestResult:
    invocation = _invoke(path, [f"--only={name}"], binary, timeout_s)
    display = _display(path)
    if invocation.timed_out:
        return TestResult(display, name, "fail", "timeout")
    for result in _parse_tap(path, invocation.stdout, invocation.returncode):
        if result.name == name:
            return result
    reason = f"exit {invocation.returncode}" if invocation.returncode else "no output"
    return TestResult(display, name, "fail", reason)


def _run_files(
    files: list[Path],
    binaries: dict[Path, str | None],
    build_errors: dict[Path, str],
    script_args: list[str],
    timeout_s: float | None,
    jobs: int,
    fail_fast: bool,
) -> list[FileRun]:
    runs: list[FileRun] = []
    if jobs == 1:
        for path in files:
            run = _run_file_unit(
                path,
                binaries[path],
                build_errors.get(path),
                script_args,
                timeout_s,
            )
            runs.append(run)
            if fail_fast and any(item.status == "fail" for item in run.results):
                break
        return runs
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [
            pool.submit(
                _run_file_unit,
                path,
                binaries[path],
                build_errors.get(path),
                script_args,
                timeout_s,
            )
            for path in files
        ]
        return [future.result() for future in futures]


def _collect_names(
    files: list[Path],
    binaries: dict[Path, str | None],
    build_errors: dict[Path, str],
    script_args: list[str],
    timeout_s: float | None,
    jobs: int,
) -> tuple[dict[Path, list[str]], dict[Path, str]]:
    names: dict[Path, list[str]] = {}
    errors: dict[Path, str] = {}

    def list_unit(path: Path) -> tuple[list[str], str | None]:
        return _list_names(
            path,
            binaries[path],
            build_errors.get(path),
            script_args,
            timeout_s,
        )

    if jobs == 1:
        for path in files:
            listed, error = list_unit(path)
            names[path] = listed
            if error is not None:
                errors[path] = error
        return names, errors
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(list_unit, path) for path in files]
        for path, future in zip(files, futures, strict=True):
            listed, error = future.result()
            names[path] = listed
            if error is not None:
                errors[path] = error
    return names, errors


def _run_isolated(
    files: list[Path],
    binaries: dict[Path, str | None],
    build_errors: dict[Path, str],
    script_args: list[str],
    timeout_s: float | None,
    jobs: int,
    fail_fast: bool,
) -> list[FileRun]:
    names, errors = _collect_names(files, binaries, build_errors, script_args, timeout_s, jobs)
    units = [(path, name) for path in files for name in names.get(path, []) if path not in errors]
    results: list[TestResult] = []
    if jobs == 1:
        for path, name in units:
            result = _run_single_test(path, name, binaries[path], timeout_s)
            results.append(result)
            if fail_fast and result.status == "fail":
                break
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(_run_single_test, path, name, binaries[path], timeout_s)
                for path, name in units
            ]
            results = [future.result() for future in futures]
    grouped: dict[Path, list[TestResult]] = {path: [] for path in files}
    for (path, _name), result in zip(units, results, strict=False):
        grouped[path].append(result)
    runs: list[FileRun] = []
    for path in files:
        if path in errors:
            runs.append(_file_failure(path, errors[path]))
        else:
            runs.append(FileRun(path, grouped.get(path, [])))
    return runs


def _render_human(runs: list[FileRun]) -> tuple[str, int]:
    lines: list[str] = []
    total = passed = failed = skipped = 0
    for run in runs:
        lines.append(f"# {_display(run.path)}")
        for result in run.results:
            total += 1
            if result.status == "pass":
                passed += 1
                lines.append(f"ok {total} - {result.name}")
            elif result.status == "skip":
                skipped += 1
                lines.append(f"ok {total} - {result.name} # SKIP {result.message}")
            else:
                failed += 1
                lines.append(f"not ok {total} - {result.name}")
                for diagnostic in result.message.splitlines() or [""]:
                    lines.append(f"  # {diagnostic}")
    lines.append(f"1..{total}")
    lines.append(f"# tests {total}")
    lines.append(f"# pass {passed}")
    lines.append(f"# fail {failed}")
    lines.append(f"# skip {skipped}")
    lines.append(f"# files {len(runs)}")
    return "\n".join(lines), failed


def _payload(runs: list[FileRun]) -> dict[str, object]:
    results = [result for run in runs for result in run.results]
    return {
        "schema_version": 1,
        "tests": [
            {
                "file": result.file,
                "name": result.name,
                "status": result.status,
                "message": result.message,
            }
            for result in results
        ],
        "summary": {
            "files": len(runs),
            "tests": len(results),
            "pass": sum(1 for result in results if result.status == "pass"),
            "fail": sum(1 for result in results if result.status == "fail"),
            "skip": sum(1 for result in results if result.status == "skip"),
        },
    }


def run_tests(args: argparse.Namespace) -> int:
    """Executa o subcomando `loxia test`; devolve o código de saída."""
    paths: list[str] = args.paths or (["tests"] if Path("tests").is_dir() else ["."])
    try:
        files = discover(paths)
    except FileNotFoundError as missing:
        print(f"Erro: caminho não encontrado: {missing.args[0]}", file=sys.stderr)
        return 2
    if not files:
        print("Erro: nenhum arquivo *_test.lx encontrado.", file=sys.stderr)
        return 2
    timeout_s = args.timeout / 1000 if args.timeout else None
    jobs = 1 if args.fail_fast else max(1, args.jobs)
    script_args: list[str] = []
    if args.filter:
        script_args.append(f"--filter={args.filter}")
    if args.only:
        script_args.append(f"--only={args.only}")
    with tempfile.TemporaryDirectory(prefix="lox-test-") as directory:
        binaries: dict[Path, str | None] = {path: None for path in files}
        build_errors: dict[Path, str] = {}
        if args.native:
            for index, path in enumerate(files):
                binary = Path(directory) / f"{index}-{path.stem}"
                error = _build(path, binary)
                if error is None:
                    binaries[path] = str(binary)
                else:
                    build_errors[path] = error
        if args.isolate == "test":
            runs = _run_isolated(
                files,
                binaries,
                build_errors,
                script_args,
                timeout_s,
                jobs,
                args.fail_fast,
            )
        else:
            runs = _run_files(
                files,
                binaries,
                build_errors,
                script_args,
                timeout_s,
                jobs,
                args.fail_fast,
            )
    if args.json:
        print(json.dumps(_payload(runs), ensure_ascii=False, indent=2))
    else:
        text, _failed = _render_human(runs)
        print(text)
    failed = sum(1 for run in runs for result in run.results if result.status == "fail")
    return 1 if failed else 0
