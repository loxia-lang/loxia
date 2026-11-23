# SPDX-License-Identifier: MIT OR Apache-2.0
"""Edits estruturados do formatter: diff determinístico em linhas → `TextEdit[]`.

As posições usam a convenção do diagnóstico: `line`/`column` 1-based em code points e
`offset` 0-based em bytes UTF-8. O LSP converte o offset para UTF-16 na borda. Aplicar os
edits na fonte produz exatamente o texto formatado, sem reler o arquivo.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EditPosition:
    line: int
    column: int
    offset: int


@dataclass(frozen=True)
class TextEdit:
    start: EditPosition
    end: EditPosition
    new_text: str


def _split_lines(text: str) -> list[str]:
    """Divide só em `\n` (keepends), como o scanner; `splitlines` criaria linhas fantasma."""
    pieces = text.split("\n")
    lines = [piece + "\n" for piece in pieces[:-1]]
    if pieces[-1]:
        lines.append(pieces[-1])
    return lines


def _position(source: str, source_bytes: bytes, offsets: Sequence[int], index: int) -> EditPosition:
    line_count = len(offsets) - 1
    offset = offsets[index]
    if index < line_count:
        return EditPosition(line=index + 1, column=1, offset=offset)
    prefix = source_bytes[:offset].decode("utf-8")
    line = prefix.count("\n") + 1
    column = len(prefix.rsplit("\n", 1)[-1]) + 1
    return EditPosition(line=line, column=column, offset=offset)


def build_edits(source: str, formatted: str) -> tuple[TextEdit, ...]:
    """Diff por linhas; cada hunk substitui um intervalo half-open da fonte."""
    if source == formatted:
        return ()
    source_lines = _split_lines(source)
    formatted_lines = _split_lines(formatted)
    source_bytes = source.encode("utf-8")
    offsets = [0]
    for line in source_lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    matcher = difflib.SequenceMatcher(a=source_lines, b=formatted_lines, autojunk=False)
    edits: list[TextEdit] = []
    for tag, start_line, end_line, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        edits.append(
            TextEdit(
                start=_position(source, source_bytes, offsets, start_line),
                end=_position(source, source_bytes, offsets, end_line),
                new_text="".join(formatted_lines[new_start:new_end]),
            )
        )
    return tuple(edits)


def apply_edits(source: str, edits: Iterable[TextEdit]) -> str:
    data = source.encode("utf-8")
    previous_end = 0
    for edit in edits:
        if edit.start.offset < previous_end:
            raise ValueError("overlapping edits")
        previous_end = edit.end.offset
    for edit in sorted(edits, key=lambda item: item.start.offset, reverse=True):
        data = data[: edit.start.offset] + edit.new_text.encode("utf-8") + data[edit.end.offset :]
    return data.decode("utf-8")


def edit_position_json(position: EditPosition) -> dict[str, int]:
    return {"line": position.line, "column": position.column, "offset": position.offset}


def edits_json(edits: Sequence[TextEdit]) -> list[dict[str, object]]:
    return [
        {
            "start": edit_position_json(edit.start),
            "end": edit_position_json(edit.end),
            "newText": edit.new_text,
        }
        for edit in edits
    ]


def unified_diff(name: str, source: str, formatted: str) -> str:
    """Diff unificado determinístico, incluindo a mudança de newline final."""
    lines = difflib.unified_diff(
        _split_lines(source),
        _split_lines(formatted),
        fromfile=f"a/{name}",
        tofile=f"b/{name}",
        lineterm="\n",
    )
    out: list[str] = []
    for line in lines:
        if line.endswith("\n"):
            out.append(line)
        else:
            out.append(line + "\n\\ No newline at end of file\n")
    return "".join(out)
