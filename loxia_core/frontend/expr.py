from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import Ty

if TYPE_CHECKING:
    from loxia_core.frontend.stmt import Param, Stmt


class Visitor[R](Protocol):
    """Protocolo que define os métodos que qualquer Visitor de Expr precisa implementar."""

    def visit_binary_expr(self, expr: Binary) -> R: ...
    def visit_grouping_expr(self, expr: Grouping) -> R: ...
    def visit_index_expr(self, expr: Index) -> R: ...
    def visit_index_set_expr(self, expr: IndexSet) -> R: ...
    def visit_is_expr(self, expr: Is) -> R: ...
    def visit_as_expr(self, expr: As) -> R: ...
    def visit_lambda_expr(self, expr: Lambda) -> R: ...
    def visit_list_expr(self, expr: ListLiteral) -> R: ...
    def visit_map_expr(self, expr: MapLiteral) -> R: ...
    def visit_match_expr(self, expr: Match) -> R: ...
    def visit_tuple_expr(self, expr: TupleLiteral) -> R: ...
    def visit_interpolated_expr(self, expr: InterpolatedString) -> R: ...
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
    start: Token | None = None
    end: Token | None = None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_grouping_expr(self)


@dataclass(frozen=True, eq=False)
class Is(Expr):
    left: Expr
    test_type: Ty
    operator: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_is_expr(self)


@dataclass(frozen=True, eq=False)
class As(Expr):
    left: Expr
    target_type: Ty
    operator: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_as_expr(self)


@dataclass(frozen=True, eq=False)
class Literal(Expr):
    value: object
    token: Token | None = None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_literal_expr(self)


@dataclass(frozen=True, eq=False)
class InterpolatedString(Expr):
    parts: list[str | Expr]
    token: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_interpolated_expr(self)


@dataclass(frozen=True, eq=False)
class Lambda(Expr):
    """Função sem nome. O corpo de expressão vira um `Return` sintético."""

    keyword: Token
    params: list[Param]
    body: list[Stmt]
    return_type: Ty | None = None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_lambda_expr(self)


@dataclass(frozen=True, eq=False)
class ListLiteral(Expr):
    elements: list[Expr]
    bracket: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_list_expr(self)


@dataclass(frozen=True, eq=False)
class MapLiteral(Expr):
    entries: list[tuple[Expr, Expr]]
    brace: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_map_expr(self)


@dataclass(frozen=True, eq=False)
class Index(Expr):
    object: Expr
    index: Expr
    bracket: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_index_expr(self)


@dataclass(frozen=True, eq=False)
class IndexSet(Expr):
    object: Expr
    index: Expr
    value: Expr
    bracket: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_index_set_expr(self)


@dataclass(frozen=True, eq=False)
class VariantPattern:
    enum: Token
    variant: Token
    bindings: list[Token]


@dataclass(frozen=True, eq=False)
class WildcardPattern:
    token: Token


Pattern = VariantPattern | WildcardPattern


@dataclass(frozen=True, eq=False)
class MatchArm:
    pattern: Pattern
    body: Expr


@dataclass(frozen=True, eq=False)
class Match(Expr):
    keyword: Token
    scrutinee: Expr
    arms: list[MatchArm]

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_match_expr(self)


@dataclass(frozen=True, eq=False)
class TupleLiteral(Expr):
    elements: list[Expr]
    paren: Token

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_tuple_expr(self)


@dataclass(frozen=True, eq=False)
class Range(Expr):
    start: Expr
    end: Expr
    operator: Token
    inclusive: bool = False

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
    spread: bool = False
    commas: tuple[Token, ...] = ()
    arg_ends: tuple[Token, ...] = ()

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
