"""`loxia fix`: aplica apenas fixes `safe`, com reparse/check a cada rodada (ADR-0093)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loxia.cli import Loxia
from loxia_core.diagnostics.diagnostic import (
    Applicability,
    Diagnostic,
)
from loxia_core.diagnostics.source import display_path

if TYPE_CHECKING:
    import argparse

MAX_ITERATIONS_DEFAULT = 10


@dataclass(frozen=True)
class Change:
    """Um fix aplicado (ou que seria, em dry-run)."""

    line: int
    column: int
    title: str
    applicability: str


@dataclass
class FixResult:
    """Resultado de uma execução de `loxia fix`."""

    source: str
    changes: list[Change]
    remaining: list[Diagnostic]


def _check(path: Path, source: str) -> list[Diagnostic]:
    lox = Loxia(error_format="json")
    lox._file = display_path(str(path))
    lox._module_root = path.resolve().parent
    lox._sources.add(lox._file, source)
    lox.check(source, emit=False)
    return list(lox.reporter.batch().diagnostics)


def _safe_edits(diagnostics: list[Diagnostic], file: str) -> list[tuple[int, int, str, Diagnostic]]:
    edits: list[tuple[int, int, str, Diagnostic]] = []
    for diagnostic in diagnostics:
        for fix in diagnostic.fixes:
            if fix.applicability is not Applicability.SAFE:
                continue
            for edit in fix.edits:
                if edit.span.file != file:
                    continue
                start = edit.span.start.offset
                end = edit.span.end.offset
                if start is None or end is None:
                    continue
                edits.append((start, end, edit.new_text, diagnostic))
    return edits


def _apply(source: str, edits: list[tuple[int, int, str, Diagnostic]]) -> str:
    """Aplica edições não sobrepostas em ordem decrescente de offset."""
    data = source.encode("utf-8")
    limit = len(data)
    for start, end, text, _diagnostic in sorted(edits, key=lambda item: item[0], reverse=True):
        if end > limit or start < 0 or end < start:
            continue
        data = data[:start] + text.encode("utf-8") + data[end:]
        limit = start
    return data.decode("utf-8")


def run_fix(path: Path, *, apply: bool, max_iterations: int) -> FixResult:
    """Executa as rodadas de fix; nunca aplica `unsafe`."""
    source = path.read_text(encoding="utf-8")
    file = display_path(str(path))
    changes: list[Change] = []
    diagnostics: list[Diagnostic] = []
    for _ in range(max(1, max_iterations)):
        diagnostics = _check(path, source)
        edits = _safe_edits(diagnostics, file)
        if not edits:
            break
        by_id: dict[int, Diagnostic] = {}
        for _start, _end, _text, diagnostic in edits:
            by_id.setdefault(id(diagnostic), diagnostic)
        for diagnostic in by_id.values():
            span = diagnostic.span
            for fix in diagnostic.fixes:
                if fix.applicability is not Applicability.SAFE:
                    continue
                if span is None:
                    continue
                changes.append(
                    Change(
                        span.start.line,
                        span.start.column or 1,
                        fix.message,
                        fix.applicability.value,
                    )
                )
        source = _apply(source, edits)
    if apply:
        _write_atomic(path, source)
    return FixResult(source, changes, diagnostics)


def _write_atomic(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def _unsafe_count(diagnostics: list[Diagnostic]) -> int:
    return sum(
        1
        for diagnostic in diagnostics
        for fix in diagnostic.fixes
        if fix.applicability is Applicability.UNSAFE
    )


def run_fix_command(args: argparse.Namespace) -> int:
    """Implementa `loxia fix`; devolve o código de saída."""
    path = Path(args.script)
    if not path.is_file():
        print(f"Erro: arquivo '{args.script}' não encontrado.", file=sys.stderr)
        return 66
    result = run_fix(
        path,
        apply=args.apply,
        max_iterations=args.max_iterations,
    )
    remaining_errors = [
        diagnostic for diagnostic in result.remaining if diagnostic.severity.value == "error"
    ]
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "file": display_path(str(path)),
                    "apply": args.apply,
                    "changes": [
                        {
                            "line": change.line,
                            "column": change.column,
                            "title": change.title,
                            "applicability": change.applicability,
                        }
                        for change in result.changes
                    ],
                    "applied": len(result.changes),
                    "unsafe": _unsafe_count(result.remaining),
                    "remaining_errors": len(remaining_errors),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for change in result.changes:
            verb = "aplicado" if args.apply else "aplicaria"
            print(
                f"{display_path(str(path))}:{change.line}:{change.column}: {verb}: {change.title}"
            )
        skipped = _unsafe_count(result.remaining)
        if skipped:
            print(f"{skipped} fix(es) unsafe não aplicados.", file=sys.stderr)
        if remaining_errors:
            print(
                f"{len(remaining_errors)} erro(s) restante(s).",
                file=sys.stderr,
            )
    if remaining_errors:
        return 1
    return 0
