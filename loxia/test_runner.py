"""Runner `lox test`: descobre `*_test.lx`, roda cada arquivo e agrega TAP (ADR-0096).

Um subprocesso por arquivo isola `os.exit`, panic e stack overflow; o timeout é por
arquivo (não há preempção dentro do processo). O relatório humano é TAP com numeração
global; `--json` emite o mesmo conteúdo em envelope estável, sem duração/timestamp (I3).
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
    """Resultado bruto da execução de um arquivo (ou do build nativo)."""

    path: Path
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    build_error: str | None = None
    results: list[TestResult] = field(default_factory=list)


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
            if any(
                part in SKIP_DIRS or part.startswith(".tmp")
                for part in candidate.parts
            ):
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
        results[-1] = TestResult(
            current.file, current.name, current.status, "\n".join(diagnostics)
        )
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


def _run_file(
    path: Path,
    *,
    filter_text: str | None,
    only: str | None,
    timeout_s: float | None,
    native: bool,
) -> FileRun:
    script_args = [f"--filter={filter_text}"] if filter_text else []
    if only:
        script_args.append(f"--only={only}")
    run = FileRun(path=path)
    with tempfile.TemporaryDirectory(prefix="lox-test-") as directory:
        if native:
            binary = Path(directory) / path.stem
            build = subprocess.run(
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
            if build.returncode != 0:
                run.build_error = (build.stderr or build.stdout).strip()
                run.returncode = build.returncode
                return run
            command = [str(binary), *script_args]
        else:
            command = [
                sys.executable,
                "-m",
                "loxia",
                "run",
                str(path),
                "--",
                *script_args,
            ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as expired:
            run.timed_out = True
            run.returncode = 124
            run.stdout = _text(expired.stdout)
            run.stderr = _text(expired.stderr)
            return run
    run.returncode = completed.returncode
    run.stdout = completed.stdout
    run.stderr = completed.stderr
    return run


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _native_missing(build_error: str | None) -> str:
    text = (build_error or "").strip()
    if not text:
        return "native build failed"
    return text.splitlines()[-1]


def _file_failure(run: FileRun) -> None:
    """Troca o resultado parseado por uma falha de arquivo (build/timeout)."""
    if run.build_error is not None:
        run.results = [
            TestResult(
                _display(run.path),
                f"<{_display(run.path)}>",
                "fail",
                _native_missing(run.build_error),
            )
        ]
    elif run.timed_out:
        run.results = [
            TestResult(
                _display(run.path),
                f"<{_display(run.path)}>",
                "fail",
                "timeout",
            )
        ]


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


def _collect(runs: list[FileRun]) -> list[TestResult]:
    results: list[TestResult] = []
    for run in runs:
        results.extend(run.results)
    return results


def _payload(runs: list[FileRun]) -> dict[str, object]:
    results = _collect(runs)
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
    paths: list[str] = args.paths or (
        ["tests"] if Path("tests").is_dir() else ["."]
    )
    try:
        files = discover(paths)
    except FileNotFoundError as error:
        print(f"Erro: caminho não encontrado: {error.args[0]}", file=sys.stderr)
        return 2
    if not files:
        print("Erro: nenhum arquivo *_test.lx encontrado.", file=sys.stderr)
        return 2
    timeout_s = args.timeout / 1000 if args.timeout else None
    jobs = 1 if args.fail_fast else max(1, args.jobs)
    runs: list[FileRun] = []
    if jobs == 1:
        for path in files:
            run = _run_file(
                path,
                filter_text=args.filter,
                only=args.only,
                timeout_s=timeout_s,
                native=args.native,
            )
            run.results = _parse_tap(path, run.stdout, run.returncode)
            _file_failure(run)
            runs.append(run)
            if args.fail_fast and any(
                result.status == "fail" for result in run.results
            ):
                break
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(
                    _run_file,
                    path,
                    filter_text=args.filter,
                    only=args.only,
                    timeout_s=timeout_s,
                    native=args.native,
                )
                for path in files
            ]
            runs = [future.result() for future in futures]
        for run in runs:
            run.results = _parse_tap(run.path, run.stdout, run.returncode)
            _file_failure(run)
    if args.json:
        print(json.dumps(_payload(runs), ensure_ascii=False, indent=2))
    else:
        text, _failed = _render_human(runs)
        print(text)
    failed = sum(1 for run in runs for item in run.results if item.status == "fail")
    return 1 if failed or any(run.build_error for run in runs) else 0
