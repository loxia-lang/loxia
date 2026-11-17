# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.diagnostic import (
    Applicability,
    Edit,
    Fix,
)
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.errors import immutable_assignment_message
from loxia_core.execution.interpreter import Interpreter
from loxia_core.frontend.destructuring import pattern_names
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
    VariantPattern,
)
from loxia_core.frontend.expr import Visitor as ExprVisitor
from loxia_core.frontend.spans import span_of_token
from loxia_core.frontend.stmt import (
    Block,
    Class,
    Destructure,
    EnumDecl,
    Expression,
    ForIn,
    Function,
    If,
    Import,
    Interface,
    Raise,
    Return,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from loxia_core.frontend.stmt import Visitor as StmtVisitor
from loxia_core.frontend.tokens import Token


class FunctionType(Enum):
    NONE = auto()
    FUNCTION = auto()
    METHOD = auto()
    INITIALIZER = auto()


class ClassType(Enum):
    NONE = auto()
    CLASS = auto()
    SUBCLASS = auto()
    INTERFACE = auto()


@dataclass
class _VariableInfo:
    defined: bool
    mutable: bool
    declaration: Token | None = None
    used: bool = False
    parameter: bool = False
    warn: bool = True
    keyword: Token | None = None


class Resolver(ExprVisitor[None], StmtVisitor[None]):
    """Resolve escopos léxicos e grava no interpretador a distância de cada variável."""

    def __init__(
        self,
        interpreter: Interpreter,
        reporter: ErrorReporter,
        *,
        warn_unused: bool = True,
    ) -> None:
        self._interpreter = interpreter
        self._reporter = reporter
        self._warn_unused = warn_unused
        self._scopes: list[dict[str, _VariableInfo]] = []
        self._scope_duplicates: list[list[tuple[Token, Token | None, _VariableInfo]]] = []
        self._current_field_keywords: dict[str, Token] | None = None
        self._class_field_keywords: dict[str, dict[str, Token]] = {}
        self._current_function: FunctionType = FunctionType.NONE
        self._current_class: ClassType = ClassType.NONE
        self._current_fields: dict[str, bool] | None = None
        self._class_fields: dict[str, dict[str, bool]] = {}
        self._function_starts: list[int] = []
        self.captured_mutables: set[Token] = set()
        # Uso -> token da declaração, para go-to-definition (LSP-1).
        self.references: dict[Token, Token] = {}
        self.captured_global_names: set[str] = set()

    def resolve(self, statements: list[Stmt]) -> None:
        for statement in statements:
            self._resolve_stmt(statement)

    def _resolve_stmt(self, stmt: Stmt) -> None:
        stmt.accept(self)

    def _resolve_expr(self, expr: Expr) -> None:
        expr.accept(self)

    def _begin_scope(self) -> None:
        self._scopes.append({})
        self._scope_duplicates.append([])

    def _end_scope(self) -> None:
        scope = self._scopes.pop()
        duplicates = self._scope_duplicates.pop()
        for token, previous, info in duplicates:
            self._emit_duplicate(token, previous, info)
        if not self._warn_unused or self._reporter.had_error:
            return
        for name, info in scope.items():
            if (
                info.warn
                and not info.used
                and not info.parameter
                and not name.startswith("_")
                and info.declaration is not None
            ):
                replacement = self._unused_name(info.declaration)
                self._reporter.warning(
                    info.declaration,
                    f"Local '{name}' is never used.",
                    code=Code.UNUSED_LOCAL,
                    fixes=(
                        Fix(
                            Applicability.SAFE,
                            f"Rename to '{replacement}' to mark it unused.",
                            (
                                Edit(
                                    span_of_token(info.declaration, self._reporter.file),
                                    replacement,
                                ),
                            ),
                        ),
                    ),
                )

    def _emit_duplicate(self, token: Token, previous: Token | None, info: _VariableInfo) -> None:
        replacement = self._unique_name(token, "_dup_")
        edits: list[Edit] = [Edit(span_of_token(token, self._reporter.file), replacement)]
        for use, declaration in self.references.items():
            if declaration is info.declaration:
                edits.append(
                    Edit(
                        span_of_token(use, self._reporter.file),
                        replacement,
                    )
                )
        self._reporter.error(
            token,
            "Already a variable with this name in this scope.",
            code=Code.DUPLICATE_VARIABLE,
            label_tokens=(((previous, "first declared here"),) if previous is not None else ()),
            fixes=(
                Fix(
                    Applicability.UNSAFE,
                    f"Rename the second binding to '{replacement}'.",
                    tuple(edits),
                ),
            ),
        )

    def _unique_name(self, token: Token, prefix: str) -> str:
        taken: set[str] = set()
        for scope in self._scopes:
            taken.update(scope)
        taken.update(declaration.lexeme for declaration in self.references.values())
        globals_env = getattr(self._interpreter, "globals", None)
        values = getattr(globals_env, "values", None)
        if isinstance(values, dict):
            taken.update(values)
        index = token.offset or 0
        candidate = f"{prefix}{index}"
        while candidate in taken:
            index += 1
            candidate = f"{prefix}{index}"
        return candidate

    def _unused_name(self, token: Token) -> str:
        taken: set[str] = set()
        for scope in self._scopes:
            taken.update(scope)
        taken.update(declaration.lexeme for declaration in self.references.values())
        globals_env = getattr(self._interpreter, "globals", None)
        values = getattr(globals_env, "values", None)
        if isinstance(values, dict):
            taken.update(values)
        index = token.offset or 0
        candidate = f"_unused_{index}"
        while candidate in taken:
            index += 1
            candidate = f"_unused_{index}"
        return candidate

    def _declare(
        self,
        name: Token,
        mutable: bool,
        *,
        parameter: bool = False,
        warn: bool = True,
        keyword: Token | None = None,
    ) -> None:
        if not self._scopes:
            return

        scope = self._scopes[-1]
        previous = scope[name.lexeme].declaration if name.lexeme in scope else None

        info = _VariableInfo(
            defined=False,
            mutable=mutable,
            declaration=name,
            parameter=parameter,
            warn=warn,
            keyword=keyword,
        )
        scope[name.lexeme] = info
        if previous is not None:
            self._scope_duplicates[-1].append((name, previous, info))

    def _define(self, name: Token) -> None:
        if not self._scopes:
            return

        self._scopes[-1][name.lexeme].defined = True

    def _resolve_local(
        self, expr: Expr, name: Token, *, read: bool = True
    ) -> tuple[_VariableInfo, int] | None:
        for i in range(len(self._scopes) - 1, -1, -1):
            info = self._scopes[i].get(name.lexeme)
            if info is not None:
                self._interpreter.resolve(expr, len(self._scopes) - 1 - i)
                if read:
                    info.used = True
                if info.declaration is not None:
                    self.references[name] = info.declaration
                return info, i

        return None

    def _resolve_function(self, function: Function | Lambda, function_type: FunctionType) -> None:
        enclosing_function = self._current_function
        self._current_function = function_type

        self._begin_scope()
        self._function_starts.append(len(self._scopes) - 1)
        try:
            for param in function.params:
                self._declare(param.name, param.mutable, parameter=True, warn=False)
                self._define(param.name)

            self.resolve(function.body)
        finally:
            self._function_starts.pop()
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

        if stmt.superclass is not None and stmt.name.lexeme == stmt.superclass.name.lexeme:
            self._reporter.error(
                stmt.superclass.name,
                "A class can't inherit from itself.",
                code=Code.INVALID_INHERITANCE,
            )

        if stmt.superclass is not None:
            self._current_class = ClassType.SUBCLASS
            self._resolve_expr(stmt.superclass)

        if stmt.superclass is not None:
            self._begin_scope()
            self._scopes[-1]["super"] = _VariableInfo(defined=True, mutable=False, warn=False)

        inherited: dict[str, bool] = {}
        inherited_keywords: dict[str, Token] = {}
        if stmt.superclass is not None:
            inherited = self._class_fields.get(stmt.superclass.name.lexeme, {})
            inherited_keywords = self._class_field_keywords.get(stmt.superclass.name.lexeme, {})

        fields: dict[str, bool] = dict(inherited)
        field_keywords: dict[str, Token] = dict(inherited_keywords)
        method_names = {method.name.lexeme for method in stmt.methods}
        for field in stmt.fields:
            if field.name.lexeme in fields:
                self._reporter.error(
                    field.name,
                    f"Field '{field.name.lexeme}' already declared.",
                    code=Code.FIELD_CONFLICT,
                )
            if field.name.lexeme in method_names:
                self._reporter.error(
                    field.name,
                    f"Field '{field.name.lexeme}' conflicts with a method.",
                    code=Code.FIELD_CONFLICT,
                )

            fields[field.name.lexeme] = field.mutable
            if field.keyword is not None:
                field_keywords[field.name.lexeme] = field.keyword
            if field.initializer is not None:
                self._resolve_expr(field.initializer)

        self._class_fields[stmt.name.lexeme] = fields
        self._class_field_keywords[stmt.name.lexeme] = field_keywords

        enclosing_fields = self._current_fields
        enclosing_field_keywords = self._current_field_keywords
        self._current_fields = fields
        self._current_field_keywords = field_keywords

        self._begin_scope()
        self._scopes[-1]["this"] = _VariableInfo(defined=True, mutable=False, warn=False)

        for method in stmt.methods:
            declaration = FunctionType.METHOD
            if method.name.lexeme == "init":
                declaration = FunctionType.INITIALIZER

            self._resolve_function(method, declaration)

        self._end_scope()

        self._current_fields = enclosing_fields
        self._current_field_keywords = enclosing_field_keywords

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

    def visit_type_alias_stmt(self, stmt: TypeAlias) -> None:
        return

    def visit_interface_stmt(self, stmt: Interface) -> None:
        # Interface é tipo, não valor: o nome não entra no escopo de variáveis.
        # Os corpos default resolvem `this` e não têm `super` nem campos.
        enclosing_class = self._current_class
        self._current_class = ClassType.INTERFACE

        self._begin_scope()
        self._scopes[-1]["this"] = _VariableInfo(defined=True, mutable=False, warn=False)
        for method in stmt.methods:
            if method.abstract:
                continue
            self._resolve_function(method, FunctionType.METHOD)
        self._end_scope()

        self._current_class = enclosing_class

    def visit_if_stmt(self, stmt: If) -> None:
        self._resolve_expr(stmt.condition)
        self._resolve_stmt(stmt.then_branch)
        if stmt.else_branch is not None:
            self._resolve_stmt(stmt.else_branch)

    def visit_return_stmt(self, stmt: Return) -> None:
        if self._current_function is FunctionType.NONE:
            self._reporter.error(
                stmt.keyword,
                "Can't return from top-level code.",
                code=Code.INVALID_RETURN,
            )

        if stmt.value is not None:
            if self._current_function is FunctionType.INITIALIZER:
                self._reporter.error(
                    stmt.keyword,
                    "Can't return a value from an initializer.",
                    code=Code.INVALID_RETURN,
                )

            self._resolve_expr(stmt.value)

    def visit_try_stmt(self, stmt: Try) -> None:
        self._begin_scope()
        for statement in stmt.body:
            self._resolve_stmt(statement)
        self._end_scope()

        for clause in stmt.handlers:
            self._begin_scope()
            self._declare(clause.binding, mutable=False)
            self._define(clause.binding)
            for statement in clause.body:
                self._resolve_stmt(statement)
            self._end_scope()

        if stmt.finally_body is not None:
            self._begin_scope()
            for statement in stmt.finally_body:
                self._resolve_stmt(statement)
            self._end_scope()

    def visit_raise_stmt(self, stmt: Raise) -> None:
        if stmt.value is not None:
            self._resolve_expr(stmt.value)

    def visit_import_stmt(self, stmt: Import) -> None:
        return

    def visit_enum_stmt(self, stmt: EnumDecl) -> None:
        self._declare(stmt.name, mutable=False)
        self._define(stmt.name)

    def visit_match_expr(self, expr: Match) -> None:
        self._resolve_expr(expr.scrutinee)
        for arm in expr.arms:
            self._begin_scope()
            if isinstance(arm.pattern, VariantPattern):
                for name in arm.pattern.bindings:
                    self._declare(name, mutable=False)
                    self._define(name)
            self._resolve_expr(arm.body)
            self._end_scope()

    def visit_destructure_stmt(self, stmt: Destructure) -> None:
        names = pattern_names(stmt.pattern)
        for name in names:
            self._declare(name, stmt.mutable)
        self._resolve_expr(stmt.initializer)
        for name in names:
            self._define(name)

    def visit_tuple_expr(self, expr: TupleLiteral) -> None:
        for element in expr.elements:
            self._resolve_expr(element)

    def visit_var_stmt(self, stmt: Var) -> None:
        self._declare(stmt.name, stmt.mutable, keyword=stmt.keyword)
        if stmt.initializer is not None:
            self._resolve_expr(stmt.initializer)

        self._define(stmt.name)

    def visit_while_stmt(self, stmt: While) -> None:
        self._resolve_expr(stmt.condition)
        self._resolve_stmt(stmt.body)

    # --- expressions ---

    def visit_assign_expr(self, expr: Assign) -> None:
        self._resolve_expr(expr.value)
        resolved = self._resolve_local(expr, expr.name, read=False)
        if resolved is not None:
            info, scope_index = resolved
            if not info.mutable:
                fixes: tuple[Fix, ...] = ()
                if info.keyword is not None and info.keyword.lexeme == "val":
                    fixes = (
                        Fix(
                            Applicability.UNSAFE,
                            "Change 'val' to 'var'.",
                            (
                                Edit(
                                    span_of_token(info.keyword, self._reporter.file),
                                    "var",
                                ),
                            ),
                        ),
                    )
                self._reporter.error(
                    expr.name,
                    immutable_assignment_message(expr.name.lexeme),
                    code=Code.IMMUTABLE_ASSIGNMENT,
                    label_tokens=(
                        ((info.declaration, "declared here"),)
                        if info.declaration is not None
                        else ()
                    ),
                    fixes=fixes,
                )
            elif (
                self._function_starts
                and scope_index < self._function_starts[-1]
                and info.declaration is not None
            ):
                self.captured_mutables.add(info.declaration)
            return

        if self._function_starts:
            self.captured_global_names.add(expr.name.lexeme)

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

    def visit_is_expr(self, expr: Is) -> None:
        self._resolve_expr(expr.left)

    def visit_as_expr(self, expr: As) -> None:
        self._resolve_expr(expr.left)

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
            fixes: tuple[Fix, ...] = ()
            keyword = None
            if self._current_field_keywords is not None:
                keyword = self._current_field_keywords.get(expr.name.lexeme)
            if keyword is not None and keyword.lexeme == "val":
                fixes = (
                    Fix(
                        Applicability.UNSAFE,
                        "Change the field to 'var'.",
                        (
                            Edit(
                                span_of_token(keyword, self._reporter.file),
                                "var",
                            ),
                        ),
                    ),
                )
            self._reporter.error(
                expr.name,
                f"Can't assign to immutable field '{expr.name.lexeme}'.",
                code=Code.IMMUTABLE_FIELD,
                fixes=fixes,
            )

    def visit_super_expr(self, expr: Super) -> None:
        if self._current_class is ClassType.NONE:
            self._reporter.error(
                expr.keyword,
                "Can't use 'super' outside of a class.",
                code=Code.INVALID_SUPER,
            )
        elif self._current_class is ClassType.INTERFACE:
            self._reporter.error(
                expr.keyword,
                "Can't use 'super' in an interface.",
                code=Code.INVALID_SUPER,
            )
        elif self._current_class is not ClassType.SUBCLASS:
            self._reporter.error(
                expr.keyword,
                "Can't use 'super' in a class with no superclass.",
                code=Code.INVALID_SUPER,
            )

        self._resolve_local(expr, expr.keyword)

    def visit_this_expr(self, expr: This) -> None:
        if self._current_class is ClassType.NONE:
            self._reporter.error(
                expr.keyword,
                "Can't use 'this' outside of a class.",
                code=Code.INVALID_THIS,
            )
            return

        self._resolve_local(expr, expr.keyword)

    def visit_unary_expr(self, expr: Unary) -> None:
        self._resolve_expr(expr.right)

    def visit_variable_expr(self, expr: Variable) -> None:
        if self._scopes:
            info = self._scopes[-1].get(expr.name.lexeme)
            if info is not None and not info.defined:
                self._reporter.error(
                    expr.name,
                    "Can't read local variable in its own initializer.",
                    code=Code.SELF_REFERENCE,
                )

        self._resolve_local(expr, expr.name)
