# SPDX-License-Identifier: MIT OR Apache-2.0
"""Snapshot do oráculo do front-end (ADR-0129).

Gera e confere três coisas sobre o corpus (`std/`, `tests/cases/` e `examples/`):

- hash canônico do JSON da AST em arquivo único;
- hash dos bytes do `format_source` (formatter Python é a referência);
- diagnósticos estruturados (fase/código/severidade/span) dos casos de erro.

O manifesto é o contrato de congelamento: qualquer mudança no oráculo aparece como diff
consciente, não como drift silencioso. `--update` regrava; o teste
`tests/test_frontend_oracle.py` só lê.

Uso:
    uv run python tools/oracle_snapshot.py --check
    uv run python tools/oracle_snapshot.py --update
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, cast

from loxia.engine import Loxia
from loxia.formatter import format_source
from loxia_core.diagnostics.diagnostic import Diagnostic, Severity, Span
from loxia_core.diagnostics.source import display_path
from loxia_core.frontend.ast_json import canonical, program_payload

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "oracle" / "frontend.json"
SCHEMA_VERSION = 1

CORPUS_GLOBS = ("std/*.lx", "tests/cases/**/*.lx", "examples/*.lx")


def corpus_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in CORPUS_GLOBS:
        files.update(ROOT.glob(pattern))
    return sorted(files)


def error_cases() -> list[Path]:
    return sorted((ROOT / "tests" / "cases" / "errors").glob("*.lx"))


def _key(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ast_hash(lox: Loxia, path: Path) -> str | None:
    file = _key(path)
    lox.use_file(file)
    parsed = lox.parse_file(path.read_text(encoding="utf-8"))
    if parsed is None:
        return None
    tokens, statements = parsed
    payload = program_payload(statements, tokens, file)
    return _sha256(canonical(payload))


def _fmt_hash(path: Path) -> str | None:
    result = format_source(path.read_text(encoding="utf-8"))
    if result is None:
        return None
    return _sha256(result.text)


def _span_json(span: Span | None) -> dict[str, object] | None:
    if span is None:
        return None
    return {
        "file": display_path(span.file),
        "start": {
            "line": span.start.line,
            "column": span.start.column,
            "offset": span.start.offset,
        },
        "end": {
            "line": span.end.line,
            "column": span.end.column,
            "offset": span.end.offset,
        },
    }


def _diagnostic_json(diagnostic: Diagnostic) -> dict[str, object]:
    return {
        "phase": diagnostic.phase.value,
        "code": diagnostic.code.value,
        "severity": diagnostic.severity.value,
        "span": _span_json(diagnostic.span),
    }


def _diagnostics(path: Path) -> list[dict[str, object]]:
    lox = Loxia(max_errors=0)
    lox.use_file(_key(path))
    source = path.read_text(encoding="utf-8")
    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        lox.check(source)
        batch = lox.reporter.batch()
        if not batch.errors:
            lox.run(source)
            batch = lox.reporter.batch()

    items = [
        _diagnostic_json(item) for item in batch.diagnostics if item.severity is Severity.ERROR
    ]
    if not items:
        raise RuntimeError(f"{_key(path)}: expected at least one error diagnostic")
    return items


def build_manifest() -> dict[str, object]:
    """Manifesto completo, em memória (o teste usa esta função)."""
    files = corpus_files()
    lox = Loxia(max_errors=0)
    ast: dict[str, str] = {}
    fmt: dict[str, str] = {}
    parse_errors: list[str] = []

    for path in files:
        key = _key(path)
        ast_hash = _ast_hash(lox, path)
        fmt_hash = _fmt_hash(path)
        if ast_hash is None:
            if fmt_hash is not None:
                raise RuntimeError(f"{key}: parse error but formatter accepted the file")
            parse_errors.append(key)
            continue
        if fmt_hash is None:
            raise RuntimeError(f"{key}: parser accepted but formatter rejected the file")
        ast[key] = ast_hash
        fmt[key] = fmt_hash

    diagnostics = {_key(path): _diagnostics(path) for path in error_cases()}
    return {
        "schema_version": SCHEMA_VERSION,
        "ast": ast,
        "fmt": fmt,
        "parse_errors": parse_errors,
        "diagnostics": diagnostics,
    }


def load_manifest() -> dict[str, object]:
    return cast(dict[str, object], json.loads(MANIFEST.read_text(encoding="utf-8")))


def write_manifest(manifest: dict[str, object]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    MANIFEST.write_text(text, encoding="utf-8")


def _diff(label: str, expected: object, actual: object) -> list[str]:
    if expected == actual:
        return []
    if isinstance(expected, dict) and isinstance(actual, dict):
        expected_map = cast(dict[str, object], expected)
        actual_map = cast(dict[str, object], actual)
        lines: list[str] = []
        for key in sorted(set(expected_map) | set(actual_map)):
            if expected_map.get(key) != actual_map.get(key):
                lines.append(f"  {label}[{key!r}]: expected {expected_map.get(key)!r}")
                lines.append(f"  {label}[{key!r}]: actual   {actual_map.get(key)!r}")
            if len(lines) >= 40:
                lines.append("  ...")
                break
        return lines
    return [f"  {label}: expected {expected!r}", f"  {label}: actual   {actual!r}"]


def check(manifest: dict[str, object]) -> list[str]:
    expected = load_manifest()
    problems: list[str] = []
    for section in ("schema_version", "ast", "fmt", "parse_errors", "diagnostics"):
        problems.extend(_diff(section, expected.get(section), manifest.get(section)))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="confere contra o manifesto")
    group.add_argument("--update", action="store_true", help="regrava o manifesto")
    args = parser.parse_args(argv)

    manifest = build_manifest()
    if args.update:
        write_manifest(manifest)
        print(
            f"oracle: {len(cast(dict[str, Any], manifest['ast']))} AST, "
            f"{len(cast(dict[str, Any], manifest['fmt']))} fmt, "
            f"{len(cast(dict[str, Any], manifest['diagnostics']))} diagnostics, "
            f"{len(cast(list[str], manifest['parse_errors']))} parse errors"
        )
        return 0

    problems = check(manifest)
    if not problems:
        print("oracle: manifest is current")
        return 0
    print("oracle: manifest is stale; run `make oracle-update`")
    print("\n".join(problems))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
