from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from src.expr import Expr
from src.tokens import Token
from src.ty import Ty

if TYPE_CHECKING:
    from src.expr import Variable


class Visitor[R](Protocol):
    """Protocolo que define os métodos que qualquer Visitor de Stmt precisa implementar."""

    def visit_block_stmt(self, stmt: Block) -> R: ...
    def visit_class_stmt(self, stmt: Class) -> R: ...
    def visit_expression_stmt(self, stmt: Expression) -> R: ...
    def visit_for_in_stmt(self, stmt: ForIn) -> R: ...
    def visit_function_stmt(self, stmt: Function) -> R: ...
    def visit_if_stmt(self, stmt: If) -> R: ...
    def visit_print_stmt(self, stmt: Print) -> R: ...
    def visit_return_stmt(self, stmt: Return) -> R: ...
    def visit_var_stmt(self, stmt: Var) -> R: ...
    def visit_while_stmt(self, stmt: While) -> R: ...


class Stmt(Protocol):
    def accept[R](self, visitor: Visitor[R]) -> R: ...


@dataclass(frozen=True, eq=False)
class Block(Stmt):
    statements: list[Stmt]

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_block_stmt(self)


@dataclass(frozen=True, eq=False)
class Field:
    name: Token
    initializer: Expr | None
    mutable: bool
    type_annotation: Ty | None = None


@dataclass(frozen=True, eq=False)
class Class(Stmt):
    name: Token
    superclass: Variable | None
    fields: list[Field]
    methods: list[Function]

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_class_stmt(self)


@dataclass(frozen=True, eq=False)
class Expression(Stmt):
    expression: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_expression_stmt(self)


@dataclass(frozen=True, eq=False)
class Param:
    name: Token
    mutable: bool
    default: Expr | None = None
    type_annotation: Ty | None = None


@dataclass(frozen=True, eq=False)
class Function(Stmt):
    name: Token
    params: list[Param]
    body: list[Stmt]
    return_type: Ty | None = None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_function_stmt(self)


@dataclass(frozen=True, eq=False)
class ForIn(Stmt):
    name: Token
    iterable: Expr
    body: Stmt

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_for_in_stmt(self)


@dataclass(frozen=True, eq=False)
class If(Stmt):
    condition: Expr
    then_branch: Stmt
    else_branch: Stmt | None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_if_stmt(self)


@dataclass(frozen=True, eq=False)
class Print(Stmt):
    expression: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_print_stmt(self)


@dataclass(frozen=True, eq=False)
class Return(Stmt):
    keyword: Token
    value: Expr | None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_return_stmt(self)


@dataclass(frozen=True, eq=False)
class Var(Stmt):
    name: Token
    initializer: Expr | None
    mutable: bool
    type_annotation: Ty | None = None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_var_stmt(self)


@dataclass(frozen=True, eq=False)
class While(Stmt):
    condition: Expr
    body: Stmt

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_while_stmt(self)
