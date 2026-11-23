# SPDX-License-Identifier: MIT OR Apache-2.0
"""Trivia (comentários e espaços) para um formatter que preserva a fonte.

O scanner continua entregando a mesma lista de tokens ao parser; em paralelo ele
registra os trechos que não viram token. `render` intercala tokens e trivia e prova
que nenhum byte do texto normalizado se perdeu. `TriviaTable` oferece as consultas
de attachment que o formatter/LSP usam sem duplicar heurísticas de linha.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from loxia_core.diagnostics.diagnostic import Position, Span
from loxia_core.frontend.source_index import NodeSpan
from loxia_core.frontend.tokens import Token


class TriviaKind(StrEnum):
    WHITESPACE = "whitespace"
    NEWLINE = "newline"
    LINE_COMMENT = "line_comment"
    BLOCK_COMMENT = "block_comment"
    DOC_COMMENT = "doc_comment"
    OTHER = "other"


COMMENT_KINDS = frozenset(
    {TriviaKind.LINE_COMMENT, TriviaKind.BLOCK_COMMENT, TriviaKind.DOC_COMMENT}
)


@dataclass(frozen=True)
class Trivia:
    kind: TriviaKind
    text: str
    span: Span

    @property
    def start(self) -> int:
        return self.span.start.offset or 0

    @property
    def end(self) -> int:
        return self.span.end.offset or 0

    @property
    def is_comment(self) -> bool:
        return self.kind in COMMENT_KINDS


def render(tokens: list[Token], trivia: list[Trivia], source: str) -> str:
    """Reconstrói a fonte normalizada intercalando tokens e trivia por offset."""
    pieces: list[tuple[int, str]] = [(item.start, item.text) for item in trivia]
    for token in tokens:
        if token.type.name == "EOF" or not token.lexeme:
            continue
        pieces.append((token.offset or 0, token.lexeme))
    pieces.sort(key=lambda item: item[0])

    data = source.encode("utf-8")
    out: list[bytes] = []
    cursor = 0
    for offset, text in pieces:
        if offset < cursor:
            raise ValueError(f"overlapping trivia/token at byte {offset}")
        if offset > cursor:
            # Sem trivia gravada este gap existe; falhar é o que impede um round-trip
            # falso (o fallback para `source` esconderia a perda da side table).
            raise ValueError(f"uncovered source bytes {cursor}:{offset}")
        out.append(text.encode("utf-8"))
        cursor = offset + len(text.encode("utf-8"))
    if cursor < len(data):
        raise ValueError(f"uncovered source bytes {cursor}:{len(data)}")
    return b"".join(out).decode("utf-8")


@dataclass(frozen=True)
class TriviaTable:
    """Consultas determinísticas sobre trivia entre tokens e nós."""

    tokens: tuple[Token, ...]
    trivia: tuple[Trivia, ...]

    def between(self, start: int, end: int) -> tuple[Trivia, ...]:
        return tuple(item for item in self.trivia if start <= item.start and item.end <= end)

    def leading(self, span: Span | NodeSpan) -> tuple[Trivia, ...]:
        """Trivia entre o token anterior e o início do nó (comentários inclusos).

        Um comentário separado do nó por uma linha em branco é órfão: não entra no
        leading. Espaços/newlines continuam disponíveis para `blank_lines_before`.
        """
        raw = self._leading_raw(span)
        cutoff = self._blank_cutoff(raw)
        previous_line = self._previous_line(span)
        return tuple(
            item
            for item in raw
            if item.start >= cutoff
            and not (item.is_comment and item.span.start.line == previous_line)
        )

    def _leading_raw(self, span: Span | NodeSpan) -> tuple[Trivia, ...]:
        start = self._start(span)
        previous_end = self._previous_end_start(start)
        return self.between(previous_end, start)

    def _previous_end_start(self, start: int) -> int:
        previous = max(
            (
                token
                for token in self.tokens
                if token.offset is not None
                and (token.offset or 0) + len(token.lexeme.encode("utf-8")) <= start
            ),
            key=lambda token: (token.offset or 0) + len(token.lexeme.encode("utf-8")),
            default=None,
        )
        if previous is None:
            return 0
        return (previous.offset or 0) + len(previous.lexeme.encode("utf-8"))

    def _previous_line(self, span: Span | NodeSpan) -> int:
        start = self._start(span)
        previous = max(
            (
                token
                for token in self.tokens
                if token.offset is not None
                and (token.offset or 0) + len(token.lexeme.encode("utf-8")) <= start
            ),
            key=lambda token: (token.offset or 0) + len(token.lexeme.encode("utf-8")),
            default=None,
        )
        if previous is None:
            return 0
        return previous.line + previous.lexeme.count("\n")

    @staticmethod
    def _blank_cutoff(items: tuple[Trivia, ...]) -> int:
        """Offset depois da última linha em branco fora de comentários."""
        cutoff = 0
        run = 0
        for item in items:
            if item.is_comment:
                run = 0
                continue
            for char in item.text:
                if char == "\n":
                    run += 1
                    if run >= 2:
                        cutoff = item.end
                elif char not in " \t\r":
                    run = 0
        return cutoff

    def trailing(self, span: Span | NodeSpan) -> tuple[Trivia, ...]:
        """Trivia depois do nó até o próximo token, restrita à mesma linha."""
        end = self._end(span)
        line = self._end_line(span)
        next_start = min(
            (
                token.offset or 0
                for token in self.tokens
                if (token.offset or 0) >= end and token.type.name != "EOF"
            ),
            default=self._source_length(),
        )
        return tuple(item for item in self.between(end, next_start) if item.span.start.line == line)

    def comments_before(self, span: Span | NodeSpan) -> tuple[Trivia, ...]:
        return tuple(item for item in self.leading(span) if item.is_comment)

    def comments_after(self, span: Span | NodeSpan) -> tuple[Trivia, ...]:
        return tuple(item for item in self.trailing(span) if item.is_comment)

    def blank_lines_before(self, span: Span | NodeSpan) -> int:
        raw = self._leading_raw(span)
        last_comment = max(
            (item for item in raw if item.is_comment),
            key=lambda item: item.end,
            default=None,
        )
        start = last_comment.end if last_comment is not None else raw[0].start if raw else 0
        tail = "".join(item.text for item in raw if item.start >= start)
        # N newlines depois do último comentário/token = N-1 linhas em branco.
        return max(0, tail.count("\n") - 1)

    @staticmethod
    def _start(span: Span | NodeSpan) -> int:
        return (span.start.offset or 0) if isinstance(span, Span) else span.start

    @staticmethod
    def _end(span: Span | NodeSpan) -> int:
        return (span.end.offset or 0) if isinstance(span, Span) else span.end

    def _end_line(self, span: Span | NodeSpan) -> int:
        if isinstance(span, Span):
            return span.end.line
        end = self._end(span)
        for token in self.tokens:
            token_end = (token.offset or 0) + len(token.lexeme.encode("utf-8"))
            if token_end == end:
                return token.line + token.lexeme.count("\n")
        return 1

    def _source_length(self) -> int:
        values = [item.end for item in self.trivia]
        values.extend(
            (token.offset or 0) + len(token.lexeme.encode("utf-8")) for token in self.tokens
        )
        return max(values, default=0)


def position_span(
    file: str,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> Span:
    """Helper para construir um Span a partir de (linha, coluna, offset)."""
    return Span(file, Position(*start), Position(*end))
