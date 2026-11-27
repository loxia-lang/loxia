# SPDX-License-Identifier: MIT OR Apache-2.0
"""Runner `lox test`: descobre `*_test.lx`, roda cada unidade e agrega TAP (ADR-0096).

`--isolate=file` (padrão) roda um subprocesso por arquivo; `--isolate=test` lista os
nomes (`--list`) e roda um subprocesso por teste (`--only`), com `--jobs` processos em
paralelo. O relatório humano é TAP com numeração global; `--json` emite o mesmo conteúdo
em envelope estável, sem duração/timestamp (I3).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape, quoteattr

from loxia.engine import Loxia
from loxia.test_selection import (
    SelectionError,
    changed_paths,
    select_changed,
    shard_files,
)
from loxia_core.diagnostics.diagnostic import Severity
from loxia_core.diagnostics.render import render_short
from loxia_core.loader.loader import ModuleError
from loxia_core.loader.manifest import ManifestError, discover_manifest, parse_manifest

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
class Location:
    """Posição da falha, relativa ao CWD (nunca caminho absoluto, I3)."""

    file: str
    line: int
    column: int


@dataclass(frozen=True)
class TestResult:
    """Um teste individual, já normalizado para o relatório."""

    file: str
    name: str
    status: str  # pass | fail | skip
    message: str = ""
    kind: str = ""  # assertion | exception | hook | crash | timeout | skip
    location: Location | None = None
    output: str = ""


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
    """Caminho exibido no relatório, sempre relativo ao diretório de execução.

    O runner roda em projetos fora do repositório; usar a raiz do pacote fazia
    `tests/sub/a_test.lx` virar `a_test.lx` (e dois arquivos homônimos ficavam
    indistinguíveis no JSON). Fora do CWD, degrada para o basename — a mesma regra
    dos diagnósticos (I3: nunca caminho absoluto).
    """
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
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


def _parse_events(path: Path, stdout: str, returncode: int, token: str) -> list[TestResult]:
    """Lê o protocolo v2: linhas `<token>{json}` e o stdout do usuário.

    O token (nonce passado ao processo) separa controle de saída do teste; um
    `print("ok 1 - falso")` do usuário nunca vira resultado.
    """
    display = _display(path)
    results: list[TestResult] = []
    current: str | None = None
    output: list[str] = []
    for line in stdout.splitlines():
        if token and line.startswith(token):
            try:
                event = json.loads(line[len(token) :])
            except json.JSONDecodeError:
                if current is not None:
                    output.append(line)
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("event")
            if kind == "start":
                current = str(event.get("name", ""))
                output = []
            elif kind == "result":
                name = str(event.get("name", ""))
                status = str(event.get("status", "fail"))
                if status not in {"pass", "fail", "skip"}:
                    status = "fail"
                results.append(
                    TestResult(
                        file=display,
                        name=name,
                        status=status,
                        message=str(event.get("message", "")),
                        kind=str(event.get("kind", "")),
                        location=_location(event.get("location")) or _site(event.get("site")),
                        output="\n".join(output),
                    )
                )
                current = None
                output = []
            continue
        if current is not None:
            output.append(line)
    if returncode != 0 and not any(result.status == "fail" for result in results):
        results.append(
            TestResult(
                display,
                f"<{display}>",
                "fail",
                f"exit {returncode}",
                kind="crash",
                output="\n".join(output),
            )
        )
    return results


def _location(value: object) -> Location | None:
    if not isinstance(value, dict):
        return None
    file = value.get("file")
    line = value.get("line")
    column = value.get("column")
    if not isinstance(file, str) or not isinstance(line, int) or not isinstance(column, int):
        return None
    return Location(file, line, column)


def _site(value: object) -> Location | None:
    """Converte o `"arquivo:linha:coluna"` do std.test em `Location`."""
    if not isinstance(value, str) or not value:
        return None
    parts = value.rsplit(":", 2)
    if len(parts) != 3:
        return None
    file, line, column = parts
    if not line.isdigit() or not column.isdigit():
        return None
    return Location(file, int(line), int(column))


def _parse_output(path: Path, stdout: str, returncode: int, token: str) -> list[TestResult]:
    if token and any(line.startswith(token) for line in stdout.splitlines()):
        return _parse_events(path, stdout, returncode, token)
    return _parse_tap(path, stdout, returncode)


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _terminate(process: subprocess.Popen[str]) -> None:
    """Mata a unidade inteira, não só o processo direto.

    Um teste pode criar filhos (`std.proc`); com o timeout matando apenas o pai, os
    netos continuariam rodando e segurando pipes. No POSIX o filho nasce em sessão
    própria e o grupo inteiro é morto.
    """
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            return
        except OSError:
            pass
    process.kill()


def _invoke(
    path: Path,
    script_args: list[str],
    binary: str | None,
    timeout_s: float | None,
    deps: tuple[str, ...] = (),
) -> Invocation:
    command = (
        [binary]
        if binary is not None
        else [sys.executable, "-m", "loxia", "run", *deps, str(path), "--"]
    )
    command = [*command, *script_args]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _terminate(process)
        stdout, stderr = process.communicate()
        return Invocation(124, _text(stdout), _text(stderr), True)
    except BaseException:
        _terminate(process)
        process.wait()
        raise
    return Invocation(process.returncode, _text(stdout), _text(stderr))


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _build(path: Path, binary: Path, deps: tuple[str, ...] = ()) -> str | None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "loxia",
            "build",
            *deps,
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
    return FileRun(
        path,
        [TestResult(display, f"<{display}>", "fail", reason, kind="crash")],
    )


def _run_file_unit(
    path: Path,
    binary: str | None,
    build_error: str | None,
    script_args: list[str],
    timeout_s: float | None,
    token: str,
    deps: tuple[str, ...] = (),
) -> FileRun:
    if build_error is not None:
        return _file_failure(path, build_error)
    invocation = _invoke(path, script_args, binary, timeout_s, deps)
    if invocation.timed_out:
        return _file_failure(path, "timeout")
    return FileRun(path, _parse_output(path, invocation.stdout, invocation.returncode, token))


def _list_names(
    path: Path,
    binary: str | None,
    build_error: str | None,
    script_args: list[str],
    timeout_s: float | None,
    token: str,
    deps: tuple[str, ...] = (),
) -> tuple[list[str], str | None]:
    if build_error is not None:
        return [], build_error
    invocation = _invoke(path, ["--list", *script_args], binary, timeout_s, deps)
    if invocation.timed_out:
        return [], "timeout"
    if invocation.returncode != 0:
        return [], _last_line(invocation.stderr) or f"exit {invocation.returncode}"
    names: list[str] = []
    for line in invocation.stdout.splitlines():
        if not token or not line.startswith(token):
            continue
        try:
            event = json.loads(line[len(token) :])
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "discover":
            names.append(str(event.get("name", "")))
    if not names:
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
    token: str,
    script_args: list[str],
    deps: tuple[str, ...] = (),
) -> TestResult:
    invocation = _invoke(path, [f"--only={name}", *script_args], binary, timeout_s, deps)
    display = _display(path)
    if invocation.timed_out:
        return TestResult(display, name, "fail", "timeout", kind="timeout")
    for result in _parse_output(path, invocation.stdout, invocation.returncode, token):
        if result.name == name:
            return result
    reason = f"exit {invocation.returncode}" if invocation.returncode else "no output"
    return TestResult(display, name, "fail", reason, kind="crash")


def _run_files(
    files: list[Path],
    binaries: dict[Path, str | None],
    build_errors: dict[Path, str],
    script_args: list[str],
    timeout_s: float | None,
    jobs: int,
    fail_fast: bool,
    token: str,
    deps: tuple[str, ...] = (),
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
                token,
                deps,
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
                token,
                deps,
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
    token: str,
    deps: tuple[str, ...] = (),
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
            token,
            deps,
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
    token: str,
    deps: tuple[str, ...] = (),
) -> list[FileRun]:
    names, errors = _collect_names(
        files, binaries, build_errors, script_args, timeout_s, jobs, token, deps
    )
    units = [(path, name) for path in files for name in names.get(path, []) if path not in errors]
    results: list[TestResult] = []
    if jobs == 1:
        for path, name in units:
            result = _run_single_test(
                path, name, binaries[path], timeout_s, token, script_args, deps
            )
            results.append(result)
            if fail_fast and result.status == "fail":
                break
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(
                    _run_single_test,
                    path,
                    name,
                    binaries[path],
                    timeout_s,
                    token,
                    script_args,
                    deps,
                )
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
            name = _tap_text(result.name)
            if result.status == "pass":
                passed += 1
                lines.append(f"ok {total} - {name}")
            elif result.status == "skip":
                skipped += 1
                lines.append(f"ok {total} - {name} # SKIP {_tap_text(result.message)}")
            else:
                failed += 1
                lines.append(f"not ok {total} - {name}")
                for diagnostic in result.message.splitlines() or [""]:
                    lines.append(f"  # {diagnostic}")
    lines.append(f"1..{total}")
    lines.append(f"# tests {total}")
    lines.append(f"# pass {passed}")
    lines.append(f"# fail {failed}")
    lines.append(f"# skip {skipped}")
    lines.append(f"# files {len(runs)}")
    return "\n".join(lines), failed


def _tap_text(value: str) -> str:
    """Mantém o TAP humano em uma linha; `#` não vira diretiva por acidente."""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("#", "\\#")
    )


def _test_payload(result: TestResult, capture: bool) -> dict[str, object]:
    return {
        "file": result.file,
        "name": result.name,
        "status": result.status,
        "kind": result.kind,
        "message": result.message,
        "location": (
            {
                "file": result.location.file,
                "line": result.location.line,
                "column": result.location.column,
            }
            if result.location is not None
            else None
        ),
        "output": (
            result.output if capture and result.status == "fail" and result.output else None
        ),
    }


def _payload(runs: list[FileRun], *, exit_code: int, capture: bool = False) -> dict[str, object]:
    results = [result for run in runs for result in run.results]
    return {
        "schema_version": 1,
        "command": "test",
        "success": exit_code == 0,
        "exit_code": exit_code,
        "tests": [_test_payload(result, capture) for result in results],
        "summary": _summary(runs, results),
    }


def _summary(runs: list[FileRun], results: list[TestResult]) -> dict[str, int]:
    return {
        "files": len(runs),
        "tests": len(results),
        "pass": sum(1 for result in results if result.status == "pass"),
        "fail": sum(1 for result in results if result.status == "fail"),
        "skip": sum(1 for result in results if result.status == "skip"),
    }


def _json_lines(runs: list[FileRun], *, exit_code: int, capture: bool = False) -> str:
    results = [result for run in runs for result in run.results]
    lines = [
        json.dumps(
            {"schema_version": 1, "type": "test", **_test_payload(result, capture)},
        )
        for result in results
    ]
    lines.append(
        json.dumps(
            {
                "schema_version": 1,
                "type": "summary",
                "success": exit_code == 0,
                "exit_code": exit_code,
                **_summary(runs, results),
            },
        )
    )
    return "\n".join(lines)


def _xml_text(value: str) -> str:
    """Remove caracteres inválidos em XML 1.0 e escapa o resto."""
    cleaned = "".join(
        ch
        for ch in value
        if ch in "\t\n\r"
        or 0x20 <= ord(ch) <= 0xD7FF
        or 0xE000 <= ord(ch) <= 0xFFFD
        or 0x10000 <= ord(ch) <= 0x10FFFF
    )
    return escape(cleaned)


def _junit(runs: list[FileRun], *, capture: bool = False) -> str:
    results = [result for run in runs for result in run.results]
    summary = _summary(runs, results)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<testsuites name="loxia-test" '
            f'tests="{summary["tests"]}" failures="{summary["fail"]}" '
            f'skipped="{summary["skip"]}" time="0">'
        ),
    ]
    for run in runs:
        failures = sum(1 for result in run.results if result.status == "fail")
        skipped = sum(1 for result in run.results if result.status == "skip")
        lines.append(
            "  <testsuite "
            f"name={quoteattr(_xml_text(_display(run.path)))} "
            f'tests="{len(run.results)}" failures="{failures}" '
            f'skipped="{skipped}" time="0">'
        )
        for result in run.results:
            name = quoteattr(_xml_text(result.name))
            file = quoteattr(_xml_text(result.file))
            if result.status == "pass":
                lines.append(f'    <testcase classname={file} name={name} time="0"/>')
            elif result.status == "skip":
                lines.append(
                    f'    <testcase classname={file} name={name} time="0">'
                    f"<skipped message={quoteattr(_xml_text(result.message))}/>"
                    "</testcase>"
                )
            else:
                body = result.message
                if capture and result.output:
                    body = f"{body}\n{result.output}" if body else result.output
                kind = quoteattr(_xml_text(result.kind or "failure"))
                lines.append(
                    f'    <testcase classname={file} name={name} time="0">'
                    f"<failure message={quoteattr(_xml_text(result.message))} type={kind}>"
                    f"{_xml_text(body)}</failure></testcase>"
                )
        lines.append("  </testsuite>")
    lines.append("</testsuites>")
    return "\n".join(lines) + "\n"


def _default_jobs() -> int:
    """Paralelismo conservador: 4 é o bastante para esconder o boot do Python."""
    return max(1, min(4, os.cpu_count() or 1))


def _dependency_roots() -> list[Path]:
    """Raízes que o loader pode importar e que não vivem no CWD.

    Inclui dependências `path` (recursivamente) e o cache git padrão do projeto.
    Qualquer mudança em `.lx`/manifesto dessas raízes precisa invalidar o binário.
    """
    roots: list[Path] = []
    pending: list[Path] = []
    seen: set[Path] = set()
    manifest_path = discover_manifest(Path.cwd())
    if manifest_path is not None:
        pending.append(manifest_path)
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            manifest = parse_manifest(path, path.read_text(encoding="utf-8"))
        except (OSError, ManifestError):
            continue
        roots.append(manifest.path.parent)
        for dependency in manifest.dependencies.values():
            if dependency.path is not None:
                roots.append(dependency.path)
                child = dependency.path / "loxia.toml"
                if child.is_file():
                    pending.append(child)
        cache = manifest.path.parent / ".loxia" / "cache"
        if cache.is_dir():
            roots.append(cache)
    return list(dict.fromkeys(roots))


def _cache_dir_from_args(deps: tuple[str, ...]) -> Path | None:
    for index, argument in enumerate(deps):
        if argument == "--cache-dir" and index + 1 < len(deps):
            return Path(deps[index + 1])
    return None


def _cache_files(deps: tuple[str, ...] = ()) -> list[Path]:
    """Fontes que podem mudar um binário: projeto, deps e runtime embarcado."""
    package = Path(__file__).resolve().parent.parent
    roots = [
        (Path.cwd(), (".lx", ".toml", ".lock")),
        (package / "loxia", (".py", ".lx")),
        (package / "loxia_core", (".py", ".lx", ".c", ".h")),
        (package / "runtime", (".c", ".h")),
    ]
    for root in _dependency_roots():
        roots.append((root, (".lx", ".toml", ".lock")))
    cache = _cache_dir_from_args(deps)
    if cache is not None:
        roots.append((cache, (".lx", ".toml", ".lock")))
    files: set[Path] = set()
    for root, suffixes in roots:
        if not root.is_dir():
            continue
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")
            )
            for name in filenames:
                if name.endswith(suffixes):
                    files.add(Path(directory) / name)
    return sorted(files)


def _compiler_identity() -> str:
    compiler = os.environ.get("CC") or shutil.which("cc") or "cc"
    try:
        process = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return compiler
    version = process.stdout.splitlines()[0] if process.stdout else ""
    return f"{compiler}\0{version}"


def _binary_cache_key(files: list[Path], deps: tuple[str, ...]) -> str:
    """Hash de tudo que entra no binário, não só do arquivo de teste.

    O loader resolve imports em tempo de build; hashear o projeto inteiro é conservador
    e evita cache velho quando um módulo importado muda. O custo é ler alguns MB.
    """
    from loxia import __version__

    digest = hashlib.sha256()
    digest.update(__version__.encode("utf-8"))
    digest.update(sys.platform.encode("utf-8"))
    digest.update(platform.machine().encode("utf-8"))
    digest.update(_compiler_identity().encode("utf-8"))
    digest.update(os.environ.get("CPATH", "").encode("utf-8"))
    digest.update(os.environ.get("LIBRARY_PATH", "").encode("utf-8"))
    digest.update("\0".join(deps).encode("utf-8"))
    for path in _cache_files(deps):
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        digest.update(str(path).encode("utf-8"))
        digest.update(payload)
    for path in files:
        try:
            payload = path.read_bytes()
        except OSError:
            payload = b""
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(payload)
    return digest.hexdigest()[:32]


def _binary_cache_dir() -> Path | None:
    configured = os.environ.get("LOX_BUILD_CACHE")
    if configured:
        base = Path(configured)
    else:
        user = str(os.getuid()) if hasattr(os, "getuid") else "user"
        base = Path(tempfile.gettempdir()) / f"loxia-build-{user}"
    try:
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        return None
    return base / "tests"


def _cached_build(
    path: Path,
    binary: Path,
    deps: tuple[str, ...],
    cache_dir: Path | None,
    key: str | None,
) -> tuple[str | None, str | None]:
    """Builda uma vez por conteúdo; devolve (binário, erro)."""
    if cache_dir is None or key is None:
        error = _build(path, binary, deps)
        return (str(binary) if error is None else None), error
    target = (
        cache_dir
        / key
        / (hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16] + "-" + path.stem)
    )
    if target.is_file() and target.stat().st_size > 0 and os.access(target, os.X_OK):
        return str(target), None
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        error = _build(path, temporary, deps)
        if error is None:
            temporary.chmod(0o755)
            os.replace(temporary, target)
            return str(target), None
        return None, error
    except OSError:
        # Cache é só desempenho; qualquer falha cai no build temporário normal.
        error = _build(path, binary, deps)
        return (str(binary) if error is None else None), error
    finally:
        temporary.unlink(missing_ok=True)


def _build_all(
    files: list[Path],
    directory: str,
    deps: tuple[str, ...],
    jobs: int,
    use_cache: bool = True,
) -> tuple[dict[Path, str | None], dict[Path, str]]:
    binaries: dict[Path, str | None] = {path: None for path in files}
    build_errors: dict[Path, str] = {}
    cache_dir = _binary_cache_dir() if use_cache else None
    cache_key = _binary_cache_key(files, deps) if cache_dir is not None else None

    def build_one(item: tuple[int, Path]) -> tuple[Path, str | None, str | None]:
        index, path = item
        binary = Path(directory) / f"{index}-{path.stem}"
        built, error = _cached_build(path, binary, deps, cache_dir, cache_key)
        return path, built, error

    items = list(enumerate(files))
    if jobs == 1:
        built = [build_one(item) for item in items]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            built = list(pool.map(build_one, items))
    for path, binary, error in built:
        if error is None and binary is not None:
            binaries[path] = binary
        else:
            build_errors[path] = error or "native build failed"
    return binaries, build_errors


def _precheck(files: list[Path], args: argparse.Namespace) -> dict[Path, str]:
    """Checa os tipos de cada arquivo em modo gradual (ADR-0142, fase 1).

    Anotação ausente não reprova (vira aviso e o tipo é `Any`); erro de tipo real sim.
    Devolve só os arquivos que falharam, com as linhas curtas do diagnóstico. Usa as
    mesmas flags de dependência do `run`/build, para não resolver o projeto de outro jeito.
    """
    failures: dict[Path, str] = {}
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            failures[path] = f"cannot read file: {error}"
            continue
        lox = Loxia(
            max_errors=5,
            # `--native` compila com o checker estrito; o precheck tem que ser estrito
            # também, senão o build falha depois de o precheck ter aprovado.
            gradual=not getattr(args, "native", False),
            frozen=getattr(args, "frozen", False),
            offline=getattr(args, "offline", False),
            cache_dir=getattr(args, "cache_dir", None),
        )
        lox.use_file(_display(path), module_root=path.resolve().parent)
        # O loader já reporta o diagnóstico antes de levantar; segue para o resumo.
        with contextlib.suppress(ModuleError):
            lox.check(source, emit=False, defer_lowerable=True)
        if not lox.reporter.had_error:
            continue
        errors = [
            item for item in lox.reporter.batch().diagnostics if item.severity is Severity.ERROR
        ]
        failures[path] = "\n".join(render_short(item) for item in errors[:5]) or "type check failed"
    return failures


def run_tests(args: argparse.Namespace) -> int:
    """Executa o subcomando `loxia test`; devolve o código de saída."""
    if getattr(args, "json", False) and getattr(args, "json_lines", False):
        print("Erro: --json e --json-lines são mutuamente exclusivos.", file=sys.stderr)
        return 2
    paths: list[str] = args.paths or (["tests"] if Path("tests").is_dir() else ["."])
    try:
        files = discover(paths)
    except FileNotFoundError as missing:
        print(f"Erro: caminho não encontrado: {missing.args[0]}", file=sys.stderr)
        return 2
    if not files:
        print("Erro: nenhum arquivo *_test.lx encontrado.", file=sys.stderr)
        return 2
    changed = getattr(args, "changed", None)
    if changed is not None:
        try:
            files = select_changed(files, changed_paths(changed))
        except SelectionError as error:
            print(f"Erro: --changed: {error}", file=sys.stderr)
            return 2
    shard = getattr(args, "shard", None)
    if shard is not None:
        try:
            files = shard_files(files, shard)
        except ValueError as error:
            print(f"Erro: --shard: {error}", file=sys.stderr)
            return 2
    timeout_s = args.timeout / 1000 if args.timeout else None
    requested_jobs = args.jobs if args.jobs is not None else _default_jobs()
    jobs = 1 if args.fail_fast else max(1, requested_jobs)
    token = secrets.token_hex(8)
    script_args: list[str] = []
    if args.filter:
        script_args.append(f"--filter={args.filter}")
    if args.only:
        script_args.append(f"--only={args.only}")
    script_args.extend(["--protocol=json", f"--token={token}"])
    deps: list[str] = []
    if getattr(args, "frozen", False):
        deps.append("--frozen")
    if getattr(args, "offline", False):
        deps.append("--offline")
    if getattr(args, "cache_dir", None):
        deps.extend(["--cache-dir", args.cache_dir])
    with tempfile.TemporaryDirectory(prefix="lox-test-") as directory:
        # Fase 1 do ADR-0142: checa cada arquivo em modo gradual antes de executar.
        check_errors = _precheck(files, args)
        binaries: dict[Path, str | None] = {path: None for path in files}
        build_errors: dict[Path, str] = dict(check_errors)
        if args.native:
            runnable = [path for path in files if path not in check_errors]
            built, errors = _build_all(
                runnable,
                directory,
                tuple(deps),
                jobs,
                use_cache=not getattr(args, "no_cache", False),
            )
            binaries.update(built)
            build_errors.update(errors)
        if args.isolate == "test":
            runs = _run_isolated(
                files,
                binaries,
                build_errors,
                script_args,
                timeout_s,
                jobs,
                args.fail_fast,
                token,
                tuple(deps),
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
                token,
                tuple(deps),
            )
    total = sum(len(run.results) for run in runs)
    failed = sum(1 for run in runs for result in run.results if result.status == "fail")
    exit_code = 1 if failed else 0
    if total == 0:
        print(
            "warning: no tests were selected (use --require-tests to exit 5).",
            file=sys.stderr,
        )
        if getattr(args, "require_tests", False):
            exit_code = 5
    capture = bool(getattr(args, "capture", False))
    if getattr(args, "junit", None):
        try:
            Path(args.junit).write_text(_junit(runs, capture=capture), encoding="utf-8")
        except OSError as error:
            print(f"Erro: não foi possível escrever {args.junit}: {error}", file=sys.stderr)
            return 2
    if getattr(args, "json_lines", False):
        print(_json_lines(runs, exit_code=exit_code, capture=capture))
    elif args.json:
        print(
            json.dumps(
                _payload(runs, exit_code=exit_code, capture=capture),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        text, _failed = _render_human(runs)
        print(text)
    return exit_code
