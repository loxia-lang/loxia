from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.tokens import Token


class Visitor[R](Protocol):
    """Protocolo que define os métodos que qualquer Visitor de Expr precisa implementar."""

    def visit_binary_expr(self, expr: Binary) -> R: ...
    def visit_grouping_expr(self, expr: Grouping) -> R: ...
    def visit_literal_expr(self, expr: Literal) -> R: ...
    def visit_range_expr(self, expr: Range) -> R: ...
    def visit_unary_expr(self, expr: Unary) -> R: ...
    def visit_assign_expr(self, expr: Assign) -> R: ...
    def visit_call_expr(self, expr: Call) -> R: ...
    def visit_conditional_expr(self, expr: Conditional) -> R: ...
    def visit_get_expr(self, expr: Get) -> R: ...
    def visit_logical_expr(self, expr: Logical) -> R: ...
    def visit_set_expr(self, expr: Set) -> R: ...
    def visit_super_expr(self, expr: Super) -> R: ...
    def visit_this_expr(self, expr: This) -> R: ...
    def visit_variable_expr(self, expr: Variable) -> R: ...


class Expr(Protocol):
    """Interface base de qualquer expressão da AST."""

    def accept[R](self, visitor: Visitor[R]) -> R: ...


# --- Nós da AST (Classes Concretas) ---


@dataclass(frozen=True, eq=False)
class Binary(Expr):
    left: Expr
    operator: Token
    right: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_binary_expr(self)


@dataclass(frozen=True, eq=False)
class Grouping(Expr):
    expression: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_grouping_expr(self)


@dataclass(frozen=True, eq=False)
class Literal(Expr):
    value: object

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_literal_expr(self)


@dataclass(frozen=True, eq=False)
class Range(Expr):
    start: Expr
    end: Expr
    operator: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_range_expr(self)


@dataclass(frozen=True, eq=False)
class Unary(Expr):
    operator: Token
    right: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_unary_expr(self)


@dataclass(frozen=True, eq=False)
class Assign(Expr):
    name: Token
    value: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_assign_expr(self)


@dataclass(frozen=True, eq=False)
class Call(Expr):
    callee: Expr
    paren: Token
    arguments: list[Expr]
    optional: bool = False

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_call_expr(self)


@dataclass(frozen=True, eq=False)
class Conditional(Expr):
    condition: Expr
    then_branch: Expr
    else_branch: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_conditional_expr(self)


@dataclass(frozen=True, eq=False)
class Get(Expr):
    object: Expr
    name: Token
    optional: bool = False

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_get_expr(self)


@dataclass(frozen=True, eq=False)
class Logical(Expr):
    left: Expr
    operator: Token
    right: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_logical_expr(self)


@dataclass(frozen=True, eq=False)
class Set(Expr):
    object: Expr
    name: Token
    value: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_set_expr(self)


@dataclass(frozen=True, eq=False)
class Super(Expr):
    keyword: Token
    method: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_super_expr(self)


@dataclass(frozen=True, eq=False)
class This(Expr):
    keyword: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_this_expr(self)


@dataclass(frozen=True, eq=False)
class Variable:
    name: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_variable_expr(self)
