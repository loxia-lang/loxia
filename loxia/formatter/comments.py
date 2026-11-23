# SPDX-License-Identifier: MIT OR Apache-2.0
"""Trivia → layout: separa comentários trailing de leading e conta linhas em branco.

O printer anda pela fonte em ordem de offset. Antes de cada âncora (token, item ou
fechamento) ele consome a trivia do intervalo e pergunta o que fazer com ela. A regra de
attachment é a do ADR-0134: comentário na mesma linha do último token é trailing; os
demais são leading e pertencem ao que vem depois. Linha em branco quebra a ligação, mas
o texto do comentário nunca é descartado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from loxia_core.frontend.trivia import Trivia, TriviaKind


@dataclass(frozen=True)
class Gap:
    """Comentários de um intervalo entre dois pontos da fonte."""

    trailing: tuple[Trivia, ...] = ()
    leading: tuple[Trivia, ...] = ()
    blank_before: int = 0
    blank_after: int = 0
    blanks_between: tuple[int, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.trailing and not self.leading


def newlines(items: Sequence[Trivia], start: int, end: int) -> int:
    text = "".join(item.text for item in items if item.start >= start and item.end <= end)
    return text.count("\n")


def blank_lines(items: Sequence[Trivia], start: int, end: int) -> int:
    """N de newlines consecutivos = N-1 linhas em branco."""
    return max(0, newlines(items, start, end) - 1)


def split_gap(
    items: Sequence[Trivia],
    *,
    previous_end: int,
    previous_line: int,
    offset: int,
) -> Gap:
    """Separa trailing/leading e mede as linhas em branco relevantes."""
    comments = [item for item in items if item.is_comment]
    trailing: list[Trivia] = []
    leading: list[Trivia] = []
    for comment in comments:
        if not leading and comment.span.start.line == previous_line:
            trailing.append(comment)
        else:
            leading.append(comment)

    content_end = trailing[-1].end if trailing else previous_end
    if leading:
        blank_before = blank_lines(items, content_end, leading[0].start)
        blank_after = blank_lines(items, leading[-1].end, offset)
        blanks_between = tuple(
            blank_lines(items, leading[index - 1].end, leading[index].start)
            for index in range(1, len(leading))
        )
    else:
        blank_before = blank_lines(items, content_end, offset)
        blank_after = 0
        blanks_between = ()

    return Gap(
        trailing=tuple(trailing),
        leading=tuple(leading),
        blank_before=blank_before,
        blank_after=blank_after,
        blanks_between=blanks_between,
    )


def comment_text(item: Trivia) -> str:
    """Normaliza `# texto`; doc comments e blocos ficam verbatim (sem reflow)."""
    value = item.text
    if item.kind is TriviaKind.LINE_COMMENT and len(value) > 1 and value[1] not in " \t#!":
        return "# " + value[1:]
    return value
