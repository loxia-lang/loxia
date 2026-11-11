from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from src.expr import Expr
from src.tokens import Token

if TYPE_CHECKING:
    from src.expr import Variable


class Visitor[R](Protocol):
    """Protocolo que define os métodos que qualquer Visitor de Stmt precisa implementar."""

    def visit_block_stmt(self, stmt: Block) -> R: ...
    def visit_class_stmt(self, stmt: Class) -> R: ...
    def visit_expression_stmt(self, stmt: Expression) -> R: ...
    def visit_function_stmt(self, stmt: Function) -> R: ...
    def visit_if_stmt(self, stmt: If) -> R: ...
    def visit_print_stmt(self, stmt: Print) -> R: ...
    def visit_return_stmt(self, stmt: Return) -> R: ...
    def visit_var_stmt(self, stmt: Var) -> R: ...
    def visit_while_stmt(self, stmt: While) -> R: ...


class Stmt(Protocol):
    def accept[R](self, visitor: Visitor[R]) -> R: ...


@dataclass(frozen=True)
class Block(Stmt):
    statements: list[Stmt]

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_block_stmt(self)


@dataclass(frozen=True)
class Class(Stmt):
    name: Token
    superclass: Variable | None
    methods: list[Function]

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_class_stmt(self)


@dataclass(frozen=True)
class Expression(Stmt):
    expression: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_expression_stmt(self)


@dataclass(frozen=True)
class Function(Stmt):
    name: Token
    params: list[Token]
    body: list[Stmt]

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_function_stmt(self)


@dataclass(frozen=True)
class If(Stmt):
    condition: Expr
    then_branch: Stmt
    else_branch: Stmt | None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_if_stmt(self)


@dataclass(frozen=True)
class Print(Stmt):
    expression: Expr

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_print_stmt(self)


@dataclass(frozen=True)
class Return(Stmt):
    keyword: Token
    value: Expr | None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_return_stmt(self)


@dataclass(frozen=True)
class Var(Stmt):
    name: Token
    initializer: Expr | None

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_var_stmt(self)


@dataclass(frozen=True)
class While(Stmt):
    condition: Expr
    body: Stmt

    def accept[R](self, visitor: Visitor[R]) -> R:
        return visitor.visit_while_stmt(self)
