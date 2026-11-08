from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.token import Token


class Visitor[R](Protocol):
    """Protocolo que define os métodos que qualquer Visitor de Expr precisa implementar."""

    def visit_binary_expr(self, expr: Binary) -> R: ...
    def visit_grouping_expr(self, expr: Grouping) -> R: ...
    def visit_literal_expr(self, expr: Literal) -> R: ...
    def visit_unary_expr(self, expr: Unary) -> R: ...


class Expr(Protocol):
    """Interface base de qualquer expressão da AST."""

    def accept[R](self, visitor: Visitor[R]) -> R: ...


# --- Nós da AST (Classes Concretas) ---


@dataclass(frozen=True)
class Binary(Expr):
    left: Expr
    operator: Token
    right: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_binary_expr(self)


@dataclass(frozen=True)
class Grouping(Expr):
    expression: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_grouping_expr(self)


@dataclass(frozen=True)
class Literal(Expr):
    value: object

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_literal_expr(self)


@dataclass(frozen=True)
class Unary(Expr):
    operator: Token
    right: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_unary_expr(self)