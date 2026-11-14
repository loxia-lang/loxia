"""Renderizadores puros de diagnóstico: `human`, `short` e `json` (ADR-0075).

Nenhum deles imprime; todos devolvem a string. O `Lox` decide o stream e o exit code.
"""

from __future__ import annotations

import json

from src.diagnostics.diagnostic import (
    Diagnostic,
    DiagnosticBatch,
    Phase,
    Position,
    Span,
)
from src.diagnostics.source import SourceMap, display_text

SCHEMA_VERSION = 1

_RESET = "\x1b[0m"
_BOLD_RED = "\x1b[1;31m"
_RED = "\x1b[31m"
_BLUE = "\x1b[34m"


def _location(diagnostic: Diagnostic) -> str:
    span = diagnostic.span
    if span is None or span.start.line < 1:
        return ""

    location = f"{span.file}:{span.start.line}"
    if span.start.column is not None:
        location += f":{span.start.column}"
    return location


def _label(diagnostic: Diagnostic, *, color: bool) -> str:
    text = f"{diagnostic.severity.value}[{diagnostic.code.value}]"
    return f"{_BOLD_RED}{text}{_RESET}" if color else text


def _header(diagnostic: Diagnostic, *, color: bool) -> str:
    location = _location(diagnostic)
    prefix = f"{location}: " if location else ""
    return f"{prefix}{_label(diagnostic, color=color)}: {diagnostic.message}\n"


def render_short(diagnostic: Diagnostic, *, color: bool = False) -> str:
    """Uma linha por diagnóstico: `arquivo:linha:col: error[CODE]: mensagem`."""
    return _header(diagnostic, color=color)


def render_human(
    diagnostic: Diagnostic,
    sources: SourceMap,
    *,
    color: bool = False,
) -> str:
    """Cabeçalho + trecho da fonte com caret. Sem fonte, degrada para `short`."""
    text = _header(diagnostic, color=color)
    snippet = _snippet(diagnostic, sources, color=color)
    return text + snippet


def render_runtime(diagnostic: Diagnostic) -> str:
    """Formato humano do erro de runtime, igual ao `lox_panic` do runtime C.

    Cabeçalho `arquivo:linha:col: error[CODIGO]: mensagem`, sem trecho de código: o
    binário pode rodar sem a fonte (ADR-0075, fase 2).
    """
    return _header(diagnostic, color=False)


def _snippet(
    diagnostic: Diagnostic,
    sources: SourceMap,
    *,
    color: bool,
) -> str:
    span = diagnostic.span
    if span is None or span.start.column is None or span.start.column < 1:
        return ""

    source = sources.get(span.file)
    if source is None:
        return ""

    line_text = source.line(span.start.line)
    if line_text is None:
        return ""

    return _caret_block(line_text, span, color=color)


def _caret_block(line_text: str, span: Span, *, color: bool) -> str:
    assert span.start.column is not None  # garantido pelo chamador
    column = span.start.column
    width = len(str(span.start.line))
    gutter = " " * width

    display_line, _ = display_text(line_text)
    prefix_width = display_text(line_text[: column - 1])[1]

    if span.end.line == span.start.line and span.end.column is not None:
        end_column = max(column, span.end.column)
        segment = line_text[column - 1 : end_column - 1]
        caret_width = display_text(segment, prefix_width)[1] - prefix_width
    else:
        caret_width = display_text(line_text[column - 1 :])[1]

    carets = "^" * max(1, caret_width)
    if color:
        carets = f"{_RED}{carets}{_RESET}"

    line_number = f"{span.start.line:>{width}}"
    if color:
        line_number = f"{_BLUE}{line_number}{_RESET}"

    return (
        f"{gutter} |\n"
        f"{line_number} | {display_line}\n"
        f"{gutter} | {' ' * prefix_width}{carets}\n"
    )


def render_batch(
    batch: DiagnosticBatch,
    sources: SourceMap,
    *,
    error_format: str,
    color: bool,
) -> str:
    """Renderiza um lote em `human` ou `short` (o JSON tem envelope próprio)."""
    if error_format == "short":
        return "".join(
            render_short(item, color=color) for item in batch.diagnostics
        )

    parts: list[str] = []
    for item in batch.diagnostics:
        if item.phase is Phase.RUNTIME:
            parts.append(render_runtime(item))
        else:
            parts.append(render_human(item, sources, color=color))
    return "".join(parts)


def _position_json(position: Position) -> dict[str, int | None]:
    return {
        "line": position.line,
        "column": position.column,
        "offset": position.offset,
    }


def _span_json(span: Span) -> dict[str, object]:
    return {
        "file": span.file,
        "start": _position_json(span.start),
        "end": _position_json(span.end),
    }


def _diagnostic_json(diagnostic: Diagnostic) -> dict[str, object]:
    return {
        "code": diagnostic.code.value,
        "phase": diagnostic.phase.value,
        "severity": diagnostic.severity.value,
        "message": diagnostic.message,
        "span": None if diagnostic.span is None else _span_json(diagnostic.span),
        "labels": [
            {
                "span": _span_json(label.span),
                "message": label.message,
            }
            for label in diagnostic.labels
        ],
        "notes": list(diagnostic.notes),
        "help": diagnostic.help,
    }


def render_json(
    batch: DiagnosticBatch,
    *,
    command: str,
    success: bool,
    exit_code: int,
) -> str:
    """Envelope JSON v1, determinístico (ordem de chaves fixa, sem dados voláteis)."""
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "success": success,
        "exit_code": exit_code,
        "diagnostics": [
            _diagnostic_json(item) for item in batch.diagnostics
        ],
        "summary": {
            "errors": batch.errors,
            "warnings": batch.warnings,
            "suppressed": batch.suppressed,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
