# SPDX-License-Identifier: MIT OR Apache-2.0
"""Spans de tokens para diagnósticos e fixes.

`span_of_token` é o span barato para fixes de nome: identificadores são ASCII e lexemas
multi-linha (strings) usam o fim da primeira linha de propósito. `span_of_token_exact`
percorre o lexema e devolve o fim real — linha/coluna em code points e offset em bytes
UTF-8 —, que é o contrato do JSON da AST (ADR-0129).
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, cast

from loxia_core.diagnostics.diagnostic import Position, Span
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import Ty


def span_of_token(token: Token, fallback_file: str = "") -> Span:
    """Span half-open do lexema do token, com arquivo de fallback do reporter."""
    file = token.file or fallback_file
    column = token.column or 1
    offset = token.offset or 0
    width = len(token.lexeme)
    return Span(
        file,
        Position(token.line, column, offset),
        Position(
            token.line,
            column + width,
            offset + len(token.lexeme.encode("utf-8")),
        ),
    )


def span_of_token_range(start: Token, end: Token, fallback_file: str = "") -> Span:
    """Span half-open do primeiro ao último token do intervalo."""
    first = span_of_token_exact(start, fallback_file)
    last = span_of_token_exact(end, fallback_file)
    return Span(first.file or last.file, first.start, last.end)


def span_of_token_exact(token: Token, fallback_file: str = "") -> Span:
    """Span half-open com o fim real do lexema, inclusive em strings multi-linha.

    O scanner conta colunas em code points e offsets em bytes UTF-8; aqui a mesma regra é
    aplicada ao lexema inteiro. `\\n` reinicia a coluna e avança a linha; `\\r` conta como
    code point normal (o offset inclui o byte).
    """
    file = token.file or fallback_file
    start_line = token.line
    start_column = token.column or 1
    start_offset = token.offset or 0
    line = start_line
    column = start_column
    offset = start_offset

    for char in token.lexeme:
        if char == "\n":
            line += 1
            column = 1
        else:
            column += 1
        offset += len(char.encode("utf-8"))

    return Span(
        file,
        Position(start_line, start_column, start_offset),
        Position(line, column, offset),
    )


def node_span(value: object, memo: dict[int, Span | None] | None = None) -> Span | None:
    """Menor span que contém os tokens do nó; `None` quando o nó não tem token.

    Vale para qualquer dataclass da AST (nós, `Param`, `Field`, `MatchArm`, …) porque
    percorre os campos por reflexão. `memo` evita O(n²) quando o chamador pede o span
    de todo nó da árvore: a chave é a identidade do objeto, que é estável durante a
    construção (os nós são imutáveis).
    """
    cache: dict[int, Span | None] = {} if memo is None else memo
    if isinstance(value, Token):
        return span_of_token_exact(value)
    if isinstance(value, Ty):
        return None
    if isinstance(value, (list, tuple)):
        merged: Span | None = None
        for item in value:
            merged = _merge_span(merged, node_span(item, cache))
        return merged
    if not (is_dataclass(value) and not isinstance(value, type)):
        return None

    key = id(value)
    if key in cache:
        return cache[key]

    merged = None
    for item in fields(cast(Any, value)):
        merged = _merge_span(merged, node_span(getattr(value, item.name), cache))
    cache[key] = merged
    return merged


def _merge_span(left: Span | None, right: Span | None) -> Span | None:
    if left is None:
        return right
    if right is None:
        return left

    start = left.start if _start_key(left.start) <= _start_key(right.start) else right.start
    end = left.end if _end_key(left.end) >= _end_key(right.end) else right.end
    return Span(left.file or right.file, start, end)


def _start_key(position: Position) -> tuple[int, int]:
    return (
        position.offset if position.offset is not None else -1,
        position.line * 1_000_000 + (position.column or 0),
    )


def _end_key(position: Position) -> tuple[int, int]:
    return _start_key(position)
