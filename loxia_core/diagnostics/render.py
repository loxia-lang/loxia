"""Renderizadores puros de diagnóstico: `human`, `short` e `json` (ADR-0075).

Nenhum deles imprime; todos devolvem a string. O `Lox` decide o stream e o exit code.
"""

from __future__ import annotations

import json

from loxia_core.diagnostics.diagnostic import (
    Diagnostic,
    DiagnosticBatch,
    Label,
    Phase,
    Position,
    Span,
    Trace,
)
from loxia_core.diagnostics.source import SourceMap, display_text

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
    """Cabeçalho + trecho da fonte com caret, labels, notas e ajuda.

    Sem fonte, degrada para `short` (o caret some, mas labels/notas/ajuda continuam).
    """
    text = _header(diagnostic, color=color)
    text += _snippet(diagnostic, sources, color=color)
    for label in diagnostic.labels:
        text += _label_block(label, sources, color=color)
    for note in diagnostic.notes:
        text += f"note: {note}\n"
    if diagnostic.help is not None:
        text += f"help: {diagnostic.help}\n"
    return text


def render_runtime(diagnostic: Diagnostic) -> str:
    """Formato humano do erro de runtime, igual ao `lox_panic` do runtime C.

    Cabeçalho `arquivo:linha:col: error[CODIGO]: mensagem`, sem trecho de código: o
    binário pode rodar sem a fonte (ADR-0075, fase 2). Depois do cabeçalho, os frames
    do stack trace no mesmo formato do runtime C (ADR-0089).
    """
    return _header(diagnostic, color=False) + _trace_lines(diagnostic)


def _trace_lines(diagnostic: Diagnostic) -> str:
    trace = diagnostic.trace
    if trace is None:
        return ""

    parts: list[str] = []
    for index, frame in enumerate(trace.frames):
        if trace.omitted > 0 and index == trace.head:
            parts.append(f"  ... {trace.omitted} frames omitted\n")
        parts.append(
            f"  at {frame.name} ({frame.file}:{frame.line}:{frame.column})\n"
        )
    return "".join(parts)


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


def _label_block(label: Label, sources: SourceMap, *, color: bool) -> str:
    """Trecho secundário de um label (`-` em vez de `^`) ou nota sem fonte."""
    span = label.span
    location = f"{span.file}:{span.start.line}"
    if span.start.column is not None:
        location += f":{span.start.column}"

    if span.start.column is None:
        return _label_note(label, location)

    source = sources.get(span.file)
    line_text = source.line(span.start.line) if source is not None else None
    if line_text is None:
        return _label_note(label, location)

    return _caret_block(
        line_text,
        span,
        color=color,
        marker="-",
        message=label.message,
        marker_color=_BLUE,
    )


def _label_note(label: Label, location: str) -> str:
    text = f"note: {location}"
    if label.message:
        text += f": {label.message}"
    return text + "\n"


def _caret_block(
    line_text: str,
    span: Span,
    *,
    color: bool,
    marker: str = "^",
    message: str | None = None,
    marker_color: str = _RED,
    separator: bool = True,
) -> str:
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

    marks = marker * max(1, caret_width)
    if color:
        marks = f"{marker_color}{marks}{_RESET}"

    line_number = f"{span.start.line:>{width}}"
    if color:
        line_number = f"{_BLUE}{line_number}{_RESET}"

    suffix = f" {message}" if message else ""
    leading = f"{gutter} |\n" if separator else ""
    return (
        f"{leading}"
        f"{line_number} | {display_line}\n"
        f"{gutter} | {' ' * prefix_width}{marks}{suffix}\n"
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


def _trace_json(trace: Trace | None) -> dict[str, object] | None:
    if trace is None:
        return None
    return {
        "frames": [
            {
                "name": frame.name,
                "file": frame.file,
                "line": frame.line,
                "column": frame.column,
            }
            for frame in trace.frames
        ],
        "omitted": trace.omitted,
        "head": trace.head,
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
        "trace": _trace_json(diagnostic.trace),
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
