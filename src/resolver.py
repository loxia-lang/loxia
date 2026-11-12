from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from src.error_reporter import ErrorReporter
from src.errors import immutable_assignment_message
from src.expr import (
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
    Lambda,
    ListLiteral,
    Literal,
    Logical,
    MapLiteral,
    Range,
    Set,
    Super,
    This,
    Unary,
    Variable,
)
from src.expr import Visitor as ExprVisitor
from src.interpreter import Interpreter
from src.stmt import (
    Block,
    Class,
    Expression,
    ForIn,
    Function,
    If,
    Print,
    Return,
    Stmt,
    Var,
    While,
)
from src.stmt import Visitor as StmtVisitor
from src.tokens import Token


class FunctionType(Enum):
    NONE = auto()
    FUNCTION = auto()
    METHOD = auto()
    INITIALIZER = auto()


class ClassType(Enum):
    NONE = auto()
    CLASS = auto()
    SUBCLASS = auto()


@dataclass
class _VariableInfo:
    defined: bool
    mutable: bool


class Resolver(ExprVisitor[None], StmtVisitor[None]):
    """Resolve escopos léxicos e grava no interpretador a distância de cada variável."""

    def __init__(self, interpreter: Interpreter, reporter: ErrorReporter) -> None:
        self._interpreter = interpreter
        self._reporter = reporter
        self._scopes: list[dict[str, _VariableInfo]] = []
        self._current_function: FunctionType = FunctionType.NONE
        self._current_class: ClassType = ClassType.NONE
        self._current_fields: dict[str, bool] | None = None
        self._class_fields: dict[str, dict[str, bool]] = {}

    def resolve(self, statements: list[Stmt]) -> None:
        for statement in statements:
            self._resolve_stmt(statement)

    def _resolve_stmt(self, stmt: Stmt) -> None:
        stmt.accept(self)

    def _resolve_expr(self, expr: Expr) -> None:
        expr.accept(self)

    def _begin_scope(self) -> None:
        self._scopes.append({})

    def _end_scope(self) -> None:
        self._scopes.pop()

    def _declare(self, name: Token, mutable: bool) -> None:
        if not self._scopes:
            return

        scope = self._scopes[-1]
        if name.lexeme in scope:
            self._reporter.error(name, "Already a variable with this name in this scope.")

        scope[name.lexeme] = _VariableInfo(defined=False, mutable=mutable)

    def _define(self, name: Token) -> None:
        if not self._scopes:
            return

        self._scopes[-1][name.lexeme].defined = True

    def _resolve_local(self, expr: Expr, name: Token) -> _VariableInfo | None:
        for i in range(len(self._scopes) - 1, -1, -1):
            info = self._scopes[i].get(name.lexeme)
            if info is not None:
                self._interpreter.resolve(expr, len(self._scopes) - 1 - i)
                return info

        return None

    def _resolve_function(
        self, function: Function | Lambda, function_type: FunctionType
    ) -> None:
        enclosing_function = self._current_function
        self._current_function = function_type

        self._begin_scope()
        for param in function.params:
            self._declare(param.name, param.mutable)
            self._define(param.name)

        self.resolve(function.body)
        self._end_scope()

        self._current_function = enclosing_function

    # --- statements ---

    def visit_block_stmt(self, stmt: Block) -> None:
        self._begin_scope()
        self.resolve(stmt.statements)
        self._end_scope()

    def visit_class_stmt(self, stmt: Class) -> None:
        enclosing_class = self._current_class
        self._current_class = ClassType.CLASS

        self._declare(stmt.name, mutable=True)
        self._define(stmt.name)

        if (
            stmt.superclass is not None
            and stmt.name.lexeme == stmt.superclass.name.lexeme
        ):
            self._reporter.error(
                stmt.superclass.name, "A class can't inherit from itself."
            )

        if stmt.superclass is not None:
            self._current_class = ClassType.SUBCLASS
            self._resolve_expr(stmt.superclass)

        if stmt.superclass is not None:
            self._begin_scope()
            self._scopes[-1]["super"] = _VariableInfo(defined=True, mutable=False)

        inherited: dict[str, bool] = {}
        if stmt.superclass is not None:
            inherited = self._class_fields.get(stmt.superclass.name.lexeme, {})

        fields: dict[str, bool] = dict(inherited)
        method_names = {method.name.lexeme for method in stmt.methods}
        for field in stmt.fields:
            if field.name.lexeme in fields:
                self._reporter.error(
                    field.name, f"Field '{field.name.lexeme}' already declared."
                )
            if field.name.lexeme in method_names:
                self._reporter.error(
                    field.name,
                    f"Field '{field.name.lexeme}' conflicts with a method.",
                )

            fields[field.name.lexeme] = field.mutable
            if field.initializer is not None:
                self._resolve_expr(field.initializer)

        self._class_fields[stmt.name.lexeme] = fields

        enclosing_fields = self._current_fields
        self._current_fields = fields

        self._begin_scope()
        self._scopes[-1]["this"] = _VariableInfo(defined=True, mutable=False)

        for method in stmt.methods:
            declaration = FunctionType.METHOD
            if method.name.lexeme == "init":
                declaration = FunctionType.INITIALIZER

            self._resolve_function(method, declaration)

        self._end_scope()

        self._current_fields = enclosing_fields

        if stmt.superclass is not None:
            self._end_scope()

        self._current_class = enclosing_class

    def visit_expression_stmt(self, stmt: Expression) -> None:
        self._resolve_expr(stmt.expression)

    def visit_for_in_stmt(self, stmt: ForIn) -> None:
        # O iterável é avaliado antes do binding do laço (como em Python).
        self._resolve_expr(stmt.iterable)

        self._begin_scope()
        self._declare(stmt.name, mutable=False)
        self._define(stmt.name)
        self._resolve_stmt(stmt.body)
        self._end_scope()

    def visit_function_stmt(self, stmt: Function) -> None:
        self._declare(stmt.name, mutable=True)
        self._define(stmt.name)
        self._resolve_function(stmt, FunctionType.FUNCTION)

    def visit_if_stmt(self, stmt: If) -> None:
        self._resolve_expr(stmt.condition)
        self._resolve_stmt(stmt.then_branch)
        if stmt.else_branch is not None:
            self._resolve_stmt(stmt.else_branch)

    def visit_print_stmt(self, stmt: Print) -> None:
        self._resolve_expr(stmt.expression)

    def visit_return_stmt(self, stmt: Return) -> None:
        if self._current_function is FunctionType.NONE:
            self._reporter.error(stmt.keyword, "Can't return from top-level code.")

        if stmt.value is not None:
            if self._current_function is FunctionType.INITIALIZER:
                self._reporter.error(
                    stmt.keyword, "Can't return a value from an initializer."
                )

            self._resolve_expr(stmt.value)

    def visit_var_stmt(self, stmt: Var) -> None:
        self._declare(stmt.name, stmt.mutable)
        if stmt.initializer is not None:
            self._resolve_expr(stmt.initializer)

        self._define(stmt.name)

    def visit_while_stmt(self, stmt: While) -> None:
        self._resolve_expr(stmt.condition)
        self._resolve_stmt(stmt.body)

    # --- expressions ---

    def visit_assign_expr(self, expr: Assign) -> None:
        self._resolve_expr(expr.value)
        info = self._resolve_local(expr, expr.name)
        if info is not None and not info.mutable:
            self._reporter.error(
                expr.name, immutable_assignment_message(expr.name.lexeme)
            )

    def visit_binary_expr(self, expr: Binary) -> None:
        self._resolve_expr(expr.left)
        self._resolve_expr(expr.right)

    def visit_call_expr(self, expr: Call) -> None:
        self._resolve_expr(expr.callee)
        for argument in expr.arguments:
            self._resolve_expr(argument)

    def visit_conditional_expr(self, expr: Conditional) -> None:
        self._resolve_expr(expr.condition)
        self._resolve_expr(expr.then_branch)
        self._resolve_expr(expr.else_branch)

    def visit_get_expr(self, expr: Get) -> None:
        self._resolve_expr(expr.object)

    def visit_index_expr(self, expr: Index) -> None:
        self._resolve_expr(expr.object)
        self._resolve_expr(expr.index)

    def visit_index_set_expr(self, expr: IndexSet) -> None:
        self._resolve_expr(expr.object)
        self._resolve_expr(expr.index)
        self._resolve_expr(expr.value)

    def visit_lambda_expr(self, expr: Lambda) -> None:
        self._resolve_function(expr, FunctionType.FUNCTION)

    def visit_list_expr(self, expr: ListLiteral) -> None:
        for element in expr.elements:
            self._resolve_expr(element)

    def visit_interpolated_expr(self, expr: InterpolatedString) -> None:
        for part in expr.parts:
            if not isinstance(part, str):
                self._resolve_expr(part)

    def visit_map_expr(self, expr: MapLiteral) -> None:
        for key, value in expr.entries:
            self._resolve_expr(key)
            self._resolve_expr(value)

    def visit_grouping_expr(self, expr: Grouping) -> None:
        self._resolve_expr(expr.expression)

    def visit_literal_expr(self, expr: Literal) -> None:
        pass

    def visit_logical_expr(self, expr: Logical) -> None:
        self._resolve_expr(expr.left)
        self._resolve_expr(expr.right)

    def visit_range_expr(self, expr: Range) -> None:
        self._resolve_expr(expr.start)
        self._resolve_expr(expr.end)

    def visit_set_expr(self, expr: Set) -> None:
        self._resolve_expr(expr.value)
        self._resolve_expr(expr.object)

        if (
            self._current_fields is not None
            and isinstance(expr.object, This)
            and expr.name.lexeme in self._current_fields
            and not self._current_fields[expr.name.lexeme]
            and self._current_function is not FunctionType.INITIALIZER
        ):
            self._reporter.error(
                expr.name,
                f"Can't assign to immutable field '{expr.name.lexeme}'.",
            )

    def visit_super_expr(self, expr: Super) -> None:
        if self._current_class is ClassType.NONE:
            self._reporter.error(
                expr.keyword, "Can't use 'super' outside of a class."
            )
        elif self._current_class is not ClassType.SUBCLASS:
            self._reporter.error(
                expr.keyword, "Can't use 'super' in a class with no superclass."
            )

        self._resolve_local(expr, expr.keyword)

    def visit_this_expr(self, expr: This) -> None:
        if self._current_class is ClassType.NONE:
            self._reporter.error(expr.keyword, "Can't use 'this' outside of a class.")
            return

        self._resolve_local(expr, expr.keyword)

    def visit_unary_expr(self, expr: Unary) -> None:
        self._resolve_expr(expr.right)

    def visit_variable_expr(self, expr: Variable) -> None:
        if self._scopes:
            info = self._scopes[-1].get(expr.name.lexeme)
            if info is not None and not info.defined:
                self._reporter.error(
                    expr.name, "Can't read local variable in its own initializer."
                )

        self._resolve_local(expr, expr.name)
