# SPDX-License-Identifier: MIT OR Apache-2.0
"""Execução dos subcomandos do CLI (quem faz, não quem decide).

Cada `*_command` recebe o `argparse.Namespace` já parseado e o parser (para `parser.error`),
valida o que é específico do comando e delega para a engine (`loxia.engine.Loxia`). O mapa
`HANDLERS` é a única tabela de despacho: `loxia.cli` só olha o primeiro argumento.
"""

import argparse
import json
import os
import signal
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import NoReturn, cast

from loxia import __version__
from loxia.cli_args import _validate
from loxia.engine import Loxia, manifest_token
from loxia.manifest_edit import (
    DependencySpec,
    ManifestEditError,
    add_dependency,
    read_manifest_text,
    remove_dependency,
    unified_diff,
    validate_dependency_name,
    write_manifest_text,
)
from loxia_core.diagnostics.codes import CODE_DESCRIPTIONS, CODE_PHASE, Code
from loxia_core.diagnostics.diagnostic import Severity
from loxia_core.diagnostics.render import SCHEMA_VERSION
from loxia_core.diagnostics.source import display_path
from loxia_core.execution.limits import (
    DEFAULT_HEAP_BYTES,
    MAX_CALL_DEPTH,
    STACK_BUDGET_BYTES,
)
from loxia_core.execution.primitives import (
    GROUP_BUDGET,
    KERNEL_BUDGET,
    NATIVE_MODULE_BUDGET,
    PRIMITIVES,
    kernel_primitives,
)
from loxia_core.loader.deps import (
    DependencyError,
    fetch_dependencies,
    lock_is_current,
    lock_manifest,
)
from loxia_core.loader.lock import (
    LOCK_NAME,
    LockError,
    read_lock,
    write_lock,
)
from loxia_core.loader.manifest import (
    MANIFEST_NAME,
    Manifest,
    ManifestError,
    discover_manifest,
)

_WATCH_INTERVAL_SECONDS = 0.25


class _Timeout(BaseException):
    """Timeout de comando; BaseException para não ser capturado pelo interpretador."""


def _raise_timeout(signum: int, frame: FrameType | None) -> None:
    raise _Timeout


@contextmanager
def _deadline(milliseconds: int) -> Iterator[None]:
    if not hasattr(signal, "setitimer"):
        raise RuntimeError("--timeout is not supported on this platform")
    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, milliseconds / 1000)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _with_timeout(
    milliseconds: int | None,
    call: Callable[[], object],
    *,
    lox: Loxia,
    command: str,
) -> None:
    if not milliseconds:
        call()
        return
    try:
        with _deadline(milliseconds):
            call()
    except _Timeout:
        lox.report_timeout(command, milliseconds)
        sys.exit(124)


def make_loxia(args: argparse.Namespace) -> Loxia:
    error_format = "json" if args.json or args.json_lines else args.error_format
    return Loxia(
        debug=getattr(args, "debug", False),
        error_format=error_format,
        color=args.color,
        max_errors=args.max_errors,
        script_args=getattr(args, "script_args", None),
        json_lines=args.json_lines,
        werror=getattr(args, "werror", False),
        module_paths=getattr(args, "module_path", None),
        frozen=getattr(args, "frozen", False),
        offline=getattr(args, "offline", False),
        cache_dir=getattr(args, "cache_dir", None),
        sandbox=getattr(args, "sandbox", False),
    )


def _normalize_source(text: str) -> str:
    """Universal newlines também para stdin: o contrato de spans é do texto normalizado."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_source(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(
            f"Erro: Arquivo '{display_path(path)}' não encontrado.",
            file=sys.stderr,
        )
        sys.exit(66)


def _set_source(
    lox: Loxia,
    *,
    path: str | None,
    stdin: bool,
    file_name: str | None,
) -> str:
    if stdin:
        lox.use_file(file_name or "<stdin>", module_root=Path.cwd())
        return _normalize_source(sys.stdin.read())
    assert path is not None
    source = _read_source(path)
    lox.use_file(display_path(path), module_root=Path(path).resolve().parent)
    return source


def run_source(
    lox: Loxia,
    args: argparse.Namespace,
    *,
    command: str,
) -> None:
    source = _set_source(
        lox,
        path=args.script,
        stdin=args.stdin,
        file_name=args.file_name,
    )
    if command == "ast":
        lox.dump_ast(
            source,
            file_only=getattr(args, "file_only", False),
            output_format=getattr(args, "format", "sexp"),
            allow_errors=getattr(args, "allow_errors", False),
            typed=getattr(args, "typed", False),
        )
        sys.exit(lox.exit_code())
    if command == "check":
        _with_timeout(
            args.timeout,
            lambda: lox.check(source),
            lox=lox,
            command="check",
        )
        sys.exit(lox.exit_code())
    _with_timeout(
        args.timeout,
        lambda: lox.run(source),
        lox=lox,
        command="run",
    )
    sys.exit(lox.exit_code())


def fmt_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from loxia.formatter import format_source
    from loxia.formatter.edits import build_edits, edits_json, unified_diff

    if args.stdin and args.script:
        parser.error("--stdin cannot be combined with a script")
    if not args.stdin and not args.script:
        parser.error("fmt requires a script (or --stdin)")
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    if not 20 <= args.max_width <= 1000:
        parser.error("--max-width must be between 20 and 1000")
    if args.edits is not None and not args.check:
        parser.error("--edits=json requires --check")
    if args.diff and args.edits is not None:
        parser.error("--diff cannot be combined with --edits")

    lox = Loxia(
        error_format=("json" if args.json or args.json_lines else args.error_format),
        color=args.color,
        max_errors=args.max_errors,
        json_lines=args.json_lines,
    )
    source = _set_source(
        lox,
        path=args.script,
        stdin=args.stdin,
        file_name=args.file_name,
    )
    result = format_source(source, reporter=lox.reporter, max_width=args.max_width)
    if result is None:
        lox.flush("fmt", exit_code=65, always=True)
        sys.exit(65)

    label = (args.file_name or "<stdin>") if args.stdin else _display_path(Path(args.script))
    if args.diff:
        if result.changed:
            sys.stdout.write(unified_diff(label, source, result.text))
        sys.exit(1 if result.changed else 0)

    if args.check:
        if args.edits == "json":
            payload = {
                "file": label,
                "changed": result.changed,
                "max_width": args.max_width,
                "edits": edits_json(build_edits(source, result.text)),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.exit(1 if result.changed else 0)

    if args.stdin:
        sys.stdout.write(result.text)
        sys.stdout.flush()
        return

    assert args.script is not None
    if result.changed:
        Path(args.script).write_text(result.text, encoding="utf-8")
    sys.exit(0)


def _display_path(path: Path) -> str:
    """Nome determinístico: relativo ao cwd quando possível, nunca absoluto."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def doc_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.script and args.stdin:
        parser.error("--stdin cannot be combined with a script")
    if not args.script and not args.stdin:
        parser.error("doc requires a script (or --stdin)")
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    lox = Loxia(
        error_format=args.error_format,
        color=args.color,
        max_errors=args.max_errors,
    )
    source = _set_source(
        lox,
        path=args.script,
        stdin=args.stdin,
        file_name=args.file_name,
    )
    if not lox.document(source, json_output=args.json):
        sys.exit(65)


def _run_scaffold(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    command: str,
) -> None:
    from loxia.scaffold import ScaffoldError, create, validate_name

    _validate(args, parser, command=command)
    lox = make_loxia(args)
    if args.name is not None:
        try:
            validate_name(args.name)
        except ScaffoldError as error:
            parser.error(error.message)
    target = Path(args.path)
    try:
        project = create(
            target,
            name=args.name,
            git=not args.no_git,
            require_new=command == "new",
            library=args.lib,
        )
    except ScaffoldError as error:
        lox.reporter.error(
            manifest_token(target / "loxia.toml"),
            error.message,
            code=Code.SCAFFOLD_STATE,
        )
        lox.flush(command, exit_code=65, always=True)
        sys.exit(65)
    shown = display_path(project.path, cwd=Path.cwd())
    if args.json:
        print(
            json.dumps(
                {
                    "path": shown,
                    "name": project.name,
                    "files": list(project.files),
                    "git": project.git_initialized,
                },
                ensure_ascii=False,
            )
        )
        return
    verb = "Created" if command == "new" else "Initialized"
    print(f"{verb} project '{project.name}' at '{shown}'.")


def _dependency_failure(
    lox: Loxia,
    command: str,
    path: Path,
    message: str,
    *,
    line: int = 1,
    column: int = 1,
) -> NoReturn:
    lox.dependency_error(path, message, line=line, column=column)
    lox.flush(command, exit_code=65, always=True)
    sys.exit(65)


def _project_manifest(lox: Loxia, command: str) -> Manifest:
    manifest_path = discover_manifest(Path.cwd())
    if manifest_path is None:
        _dependency_failure(lox, command, Path.cwd() / MANIFEST_NAME, "No loxia.toml found.")
    manifest = lox._load_manifest(manifest_path)
    if manifest is None:
        lox.flush(command, exit_code=65, always=True)
        sys.exit(65)
    return manifest


def _edit_failure(
    lox: Loxia,
    command: str,
    path: Path,
    error: ManifestEditError,
) -> NoReturn:
    lox.reporter.error(
        manifest_token(path, error.line, error.column),
        error.message,
        code=Code.MANIFEST_EDIT,
    )
    lox.flush(command, exit_code=65, always=True)
    sys.exit(65)


def _dependency_spec(args: argparse.Namespace, parser: argparse.ArgumentParser) -> DependencySpec:
    path = getattr(args, "path", None)
    git = getattr(args, "git", None)
    rev = getattr(args, "rev", None)
    if (path is None) == (git is None):
        parser.error("use exactly one of --path or --git")
    if path is not None and rev is not None:
        parser.error("--rev is only valid with --git")
    if git is not None and rev is None:
        parser.error("--git requires --rev")
    return DependencySpec(path=path, git=git, rev=rev)


def _relock(lox: Loxia, command: str, manifest: Manifest) -> None:
    lock_path = manifest.path.parent / LOCK_NAME
    try:
        lock = lock_manifest(manifest, offline=lox.offline, cache_dir=lox.cache_dir)
        write_lock(lock_path, lock)
    except LockError as error:
        _dependency_failure(
            lox, command, lock_path, error.message, line=error.line, column=error.column
        )
    except DependencyError as error:
        _dependency_failure(lox, command, manifest.path, error.message)


def _run_edit(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    command: str,
) -> None:
    _validate(args, parser, command=command)
    lox = make_loxia(args)
    spec = _dependency_spec(args, parser) if command == "add" else None
    try:
        validate_dependency_name(args.name)
    except ManifestEditError as error:
        parser.error(error.message)
    manifest_path = discover_manifest(Path.cwd())
    if manifest_path is None:
        _dependency_failure(lox, command, Path.cwd() / MANIFEST_NAME, "No loxia.toml found.")
    if lox._load_manifest(manifest_path) is None:
        lox.flush(command, exit_code=65, always=True)
        sys.exit(65)

    old_text = read_manifest_text(manifest_path)
    try:
        if command == "add":
            assert spec is not None
            result = add_dependency(manifest_path, old_text, args.name, spec)
        else:
            result = remove_dependency(manifest_path, old_text, args.name)
    except ManifestEditError as error:
        _edit_failure(lox, command, manifest_path, error)
    except ManifestError as error:
        lox.reporter.error(
            manifest_token(manifest_path, error.line, error.column),
            error.message,
            code=Code.SYNTAX_UNEXPECTED,
        )
        lox.flush(command, exit_code=65, always=True)
        sys.exit(65)

    if not result.changed:
        if args.json:
            print(
                json.dumps(
                    {"manifest": manifest_path.name, "changed": False, "dry_run": False},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"Dependency '{args.name}' is already declared.")
        return
    if args.dry_run:
        diff = unified_diff(old_text, result.text, manifest_path.name)
        if args.json:
            print(
                json.dumps(
                    {
                        "manifest": manifest_path.name,
                        "changed": True,
                        "dry_run": True,
                        "diff": diff,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(diff, end="")
        return
    write_manifest_text(manifest_path, result.text)
    if args.lock:
        _relock(lox, command, result.manifest)
    if args.json:
        print(
            json.dumps(
                {"manifest": manifest_path.name, "changed": True, "dry_run": False},
                ensure_ascii=False,
            )
        )
        return
    verb = "Added" if command == "add" else "Removed"
    preposition = "to" if command == "add" else "from"
    print(f"{verb} dependency '{args.name}' {preposition} {manifest_path.name}.")


def add_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _run_edit(args, parser, command="add")


def remove_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _run_edit(args, parser, command="remove")


def lock_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="lock")
    lox = make_loxia(args)
    manifest = _project_manifest(lox, "lock")
    lock_path = manifest.path.parent / LOCK_NAME
    try:
        lock = lock_manifest(manifest, offline=args.offline, cache_dir=lox.cache_dir)
        if args.check:
            if not lock_is_current(read_lock(lock_path), lock):
                print("loxia.lock is out of date; run 'loxia lock'.", file=sys.stderr)
                sys.exit(1)
            return
        write_lock(lock_path, lock)
    except LockError as error:
        _dependency_failure(
            lox,
            "lock",
            lock_path,
            error.message,
            line=error.line,
            column=error.column,
        )
    except DependencyError as error:
        _dependency_failure(lox, "lock", manifest.path, error.message)


def fetch_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="fetch")
    lox = make_loxia(args)
    manifest = _project_manifest(lox, "fetch")
    lock_path = manifest.path.parent / LOCK_NAME
    try:
        lock = read_lock(lock_path)
        fetch_dependencies(
            manifest,
            lock=lock,
            offline=args.offline,
            cache_dir=lox.cache_dir,
        )
    except LockError as error:
        _dependency_failure(
            lox,
            "fetch",
            lock_path,
            error.message,
            line=error.line,
            column=error.column,
        )
    except DependencyError as error:
        _dependency_failure(lox, "fetch", manifest.path, error.message)


def run_build(lox: Loxia, args: argparse.Namespace) -> None:
    source = _set_source(
        lox,
        path=args.script,
        stdin=False,
        file_name=None,
    )
    destination = Path(args.output) if args.output is not None else None
    ok = lox.build(
        source,
        emit=args.emit,
        output=destination,
        stem=Path(args.script).stem,
        max_heap=args.max_heap,
    )
    sys.exit(0 if ok else 65)


def _snapshot(paths: list[Path]) -> tuple[tuple[str, int | None, int | None], ...]:
    snapshot: list[tuple[str, int | None, int | None]] = []
    for path in sorted(set(paths)):
        try:
            stat = os.stat(path)
        except OSError:
            snapshot.append((str(path), None, None))
        else:
            snapshot.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(snapshot)


def watch_check(lox: Loxia, args: argparse.Namespace) -> None:
    assert args.script is not None
    entry = Path(args.script).resolve()
    last: tuple[tuple[str, int | None, int | None], ...] | None = None
    revision = 0
    try:
        while True:
            paths = [entry, *lox.watched_files]
            current = _snapshot(paths)
            if current != last:
                source = _read_source(args.script)
                lox.use_file(display_path(args.script), module_root=entry.parent)
                code = lox.check(source, emit=False)
                lox.flush("check", exit_code=code, always=True, revision=revision)
                last = _snapshot([entry, *lox.watched_files])
                revision += 1
            time.sleep(_WATCH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        sys.exit(130)


def _capabilities_payload() -> dict[str, object]:
    commands: list[dict[str, object]] = [
        {
            "name": "run",
            "features": [
                "json",
                "json-lines",
                "stdin",
                "timeout",
                "sandbox",
                "frozen",
                "offline",
                "cache-dir",
            ],
        },
        {
            "name": "repl",
            "features": ["json", "json-lines", "debug", "module-path"],
        },
        {"name": "new", "features": ["name", "no-git", "json"]},
        {"name": "init", "features": ["name", "no-git", "json"]},
        {
            "name": "check",
            "features": [
                "json",
                "json-lines",
                "stdin",
                "timeout",
                "watch",
                "frozen",
                "offline",
                "cache-dir",
            ],
        },
        {
            "name": "build",
            "features": ["json", "json-lines", "frozen", "offline", "cache-dir"],
        },
        {
            "name": "ast",
            "features": ["json", "json-lines", "stdin", "frozen", "offline", "cache-dir"],
        },
        {"name": "fmt", "features": ["check", "stdin"]},
        {"name": "fix", "features": ["apply", "json"]},
        {
            "name": "test",
            "features": [
                "json",
                "filter",
                "only",
                "jobs",
                "isolate",
                "fail-fast",
                "native",
                "timeout",
                "frozen",
                "offline",
                "cache-dir",
            ],
        },
        {"name": "lock", "features": ["check", "offline", "cache-dir"]},
        {"name": "fetch", "features": ["offline", "cache-dir"]},
        {"name": "doc", "features": ["json", "stdin"]},
        {"name": "explain", "features": ["json"]},
        {"name": "capabilities", "features": ["json"]},
        {
            "name": "mcp",
            "features": ["stdio", "tools"],
        },
        {
            "name": "lsp",
            "features": [
                "stdio",
                "hover",
                "definition",
                "documentSymbol",
                "completion",
                "signatureHelp",
                "inlayHint",
                "formatting",
                "codeAction",
                "rename",
                "workspaceSymbol",
                "semanticTokens",
            ],
        },
    ]
    codes = [
        {
            "code": code.value,
            "phase": CODE_PHASE[code].value,
            "description": CODE_DESCRIPTIONS[code],
        }
        for code in sorted(Code, key=lambda item: item.value)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "version": __version__,
        "program": "loxia",
        "commands": commands,
        "error_formats": ["human", "short", "json"],
        "jsonl_events": ["start", "diagnostic", "summary"],
        "codes": codes,
        "limits": {
            "max_call_depth": MAX_CALL_DEPTH,
            "stack_budget_bytes": STACK_BUDGET_BYTES,
            "default_heap_bytes": DEFAULT_HEAP_BYTES,
        },
        "primitives": [
            {
                "name": primitive.lox,
                "group": primitive.group,
                "layer": primitive.layer,
                "ambient": primitive.ambient,
                "native_only": primitive.native_only,
                "site": primitive.site,
            }
            for primitive in kernel_primitives()
        ],
        "native_modules": [
            {
                "name": module,
                "budget": budget,
                "used": sum(1 for primitive in PRIMITIVES if primitive.group == module),
            }
            for module, budget in sorted(NATIVE_MODULE_BUDGET.items())
        ],
        "kernel_budget": {"total": KERNEL_BUDGET, "groups": GROUP_BUDGET},
        "warnings": {"codes": ["W1001"], "werror": True},
        "fixes": {
            "applicability": ["safe", "unsafe"],
            "implemented": True,
        },
    }


def _print_capabilities(as_json: bool) -> None:
    payload = _capabilities_payload()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    commands = cast(list[dict[str, object]], payload["commands"])
    primitives = cast(list[dict[str, object]], payload["primitives"])
    groups = Counter(str(primitive["group"]) for primitive in primitives)
    layers = Counter(str(primitive["layer"]) for primitive in primitives)
    print(f"loxia {payload['version']}")
    print("commands: " + ", ".join(str(command["name"]) for command in commands))
    print("error formats: " + ", ".join(cast(list[str], payload["error_formats"])))
    print("jsonl events: " + ", ".join(cast(list[str], payload["jsonl_events"])))
    print(
        f"primitives: {len(primitives)} ("
        + ", ".join(f"{group} {count}" for group, count in sorted(groups.items()))
        + ")"
    )
    print("layers: " + ", ".join(f"{layer} {count}" for layer, count in sorted(layers.items())))
    modules = cast(list[dict[str, object]], payload["native_modules"])
    print(
        "native modules: "
        + ", ".join(f"{module['name']} {module['used']}/{module['budget']}" for module in modules)
    )
    print(f"max call depth: {MAX_CALL_DEPTH}")
    print(f"default heap: {DEFAULT_HEAP_BYTES // 1024**2}M")


def _explain(code_text: str, as_json: bool) -> None:
    try:
        code = Code(code_text.upper())
    except ValueError:
        print(f"Erro: código de diagnóstico desconhecido: {code_text}", file=sys.stderr)
        sys.exit(2)

    phase = CODE_PHASE[code]
    description = CODE_DESCRIPTIONS[code]
    if as_json:
        print(
            json.dumps(
                {
                    "code": code.value,
                    "phase": phase.value,
                    "severity": (
                        Severity.WARNING.value
                        if code.value.startswith("W")
                        else Severity.ERROR.value
                    ),
                    "description": description,
                    "doc": "docs/spec/erros.md",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(f"{code.value} ({phase.value}): {description}")
    print("See docs/spec/erros.md.")


# -- pontos de entrada por comando -------------------------------------------


def run_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="run")
    run_source(make_loxia(args), args, command="run")


def repl_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="repl")
    make_loxia(args).run_prompt()


def check_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="check")
    lox = make_loxia(args)
    if args.watch:
        watch_check(lox, args)
    else:
        run_source(lox, args, command="check")


def ast_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="ast")
    run_source(make_loxia(args), args, command="ast")


def build_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate(args, parser, command="build")
    run_build(make_loxia(args), args)


def new_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _run_scaffold(args, parser, command="new")


def init_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _run_scaffold(args, parser, command="init")


def explain_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _explain(args.code, args.json)


def capabilities_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _print_capabilities(args.json)


def lsp_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from loxia.lsp import main as lsp_main

    raise SystemExit(lsp_main())


def mcp_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from loxia.mcp import main as mcp_main

    raise SystemExit(mcp_main())


def test_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from loxia.test_runner import run_tests

    raise SystemExit(run_tests(args))


def fix_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from loxia.fixer import run_fix_command

    raise SystemExit(run_fix_command(args))


Command = Callable[[argparse.Namespace, argparse.ArgumentParser], None]

HANDLERS: dict[str, Command] = {
    "run": run_command,
    "repl": repl_command,
    "new": new_command,
    "init": init_command,
    "add": add_command,
    "remove": remove_command,
    "check": check_command,
    "build": build_command,
    "ast": ast_command,
    "fmt": fmt_command,
    "doc": doc_command,
    "explain": explain_command,
    "capabilities": capabilities_command,
    "lsp": lsp_command,
    "mcp": mcp_command,
    "test": test_command,
    "fix": fix_command,
    "lock": lock_command,
    "fetch": fetch_command,
}
