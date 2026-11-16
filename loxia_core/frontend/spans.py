"""Spans de tokens para diagnósticos e fixes.

Identificadores são ASCII, então coluna e offset andam juntos; spans de lexemas
multi-linha (strings) usam o fim da primeira linha de propósito — fixes de nome só
precisam de tokens simples.
"""

from __future__ import annotations

from loxia_core.diagnostics.diagnostic import Position, Span
from loxia_core.frontend.tokens import Token


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
