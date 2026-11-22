# SPDX-License-Identifier: MIT OR Apache-2.0
"""Spans de tokens para diagnósticos e fixes.

`span_of_token` é o span barato para fixes de nome: identificadores são ASCII e lexemas
multi-linha (strings) usam o fim da primeira linha de propósito. `span_of_token_exact`
percorre o lexema e devolve o fim real — linha/coluna em code points e offset em bytes
UTF-8 —, que é o contrato do JSON da AST (ADR-0129).
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
