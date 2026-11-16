"""Índice de spans de expressão (ADR-0090).

O parser não guarda spans em todo nó; o índice deriva a extensão a partir dos tokens
do próprio nó e dos filhos. Parênteses de agrupamento entram no span porque `Grouping`
guarda os dois tokens. É a base formal para hover/definition/diagnósticos por expressão.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, cast

from loxia_core.frontend.expr import (
    As,
    Assign,
    Binary,
    Call,
    Conditional,
    Expr,
    Get,
    Grouping,
    Index,
    IndexSet,
    InterpolatedString,
    Is,
    Lambda,
    ListLiteral,
    Literal,
    Logical,
    MapLiteral,
    Match,
    Range,
    Set,
    Super,
    This,
    TupleLiteral,
    Unary,
    Variable,
)
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.tokens import Token

EXPR_TYPES = (
    As, Assign, Binary, Call, Conditional, Get, Grouping, Index, IndexSet,
    InterpolatedString, Is, Lambda, ListLiteral, Literal, Logical, MapLiteral,
    Match, Range, Set, Super, This, TupleLiteral, Unary, Variable,
)


@dataclass(frozen=True)
class ExprSpan:
    """Extensão half-open de uma expressão, em offsets de bytes UTF-8."""

    expression: Expr
    start: int
    end: int


class SourceIndex:
    """Mapeia offset → menor expressão que contém aquele offset."""

    def __init__(self, statements: list[Stmt], source: str) -> None:
        self.source = source
        self.spans: list[ExprSpan] = []
        for statement in statements:
            self._walk(statement)

    def _walk(self, value: object) -> tuple[int, int] | None:
        if isinstance(value, Token):
            offset = value.offset or 0
            return offset, offset + len(value.lexeme.encode("utf-8"))
        if isinstance(value, EXPR_TYPES):
            own = self._own_extent(value)
            if own is None:
                return None
            self.spans.append(ExprSpan(value, own[0], own[1]))
            return own
        if is_dataclass(value) and not isinstance(value, type):
            extents = [
                extent
                for item in fields(value)
                if (extent := self._walk(getattr(value, item.name))) is not None
            ]
            if not extents:
                return None
            return min(item[0] for item in extents), max(item[1] for item in extents)
        if isinstance(value, (list, tuple)):
            extents = [
                extent
                for item in value
                if (extent := self._walk(item)) is not None
            ]
            if not extents:
                return None
            return min(item[0] for item in extents), max(item[1] for item in extents)
        return None

    def _own_extent(self, expression: Expr) -> tuple[int, int] | None:
        if (
            isinstance(expression, Grouping)
            and expression.start is not None
            and expression.end is not None
        ):
            start = expression.start.offset or 0
            end = (expression.end.offset or 0) + len(
                expression.end.lexeme.encode("utf-8")
            )
            return start, end
        if isinstance(expression, Literal) and expression.token is not None:
            start = expression.token.offset or 0
            return start, start + len(expression.token.lexeme.encode("utf-8"))
        extents: list[tuple[int, int]] = []
        for item in fields(cast(Any, expression)):
            value = getattr(expression, item.name)
            extent = self._walk(value)
            if extent is not None:
                extents.append(extent)
        if not extents:
            return None
        return min(item[0] for item in extents), max(item[1] for item in extents)

    def at(self, offset: int) -> ExprSpan | None:
        """Menor expressão que contém `offset` (half-open)."""
        found = [
            span
            for span in self.spans
            if span.start <= offset < span.end
        ]
        if not found:
            return None
        return min(found, key=lambda span: span.end - span.start)
