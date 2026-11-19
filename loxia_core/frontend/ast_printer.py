# SPDX-License-Identifier: MIT OR Apache-2.0
from loxia_core.execution.values import repr_value
from loxia_core.frontend.destructuring import DestructurePattern, NamePattern
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
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import Ty, display


class AstPrinter(ExprVisitor[str], StmtVisitor[str]):
    """Serializa a AST em S-expressions — ferramenta de debug, não de execução."""

    def print(self, expr: Expr) -> str:
        return expr.accept(self)

    def print_program(self, statements: list[Stmt]) -> str:
        return "\n".join(statement.accept(self) for statement in statements)

    def visit_binary_expr(self, expr: Binary) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.left, expr.right)

    def visit_grouping_expr(self, expr: Grouping) -> str:
        return self._parenthesize("group", expr.expression)

    def visit_literal_expr(self, expr: Literal) -> str:
        return repr_value(expr.value)

    def visit_list_expr(self, expr: ListLiteral) -> str:
        if not expr.elements:
            return "(list)"

        inner = " ".join(element.accept(self) for element in expr.elements)
        return f"(list {inner})"

    def visit_interpolated_expr(self, expr: InterpolatedString) -> str:
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, str):
                if part:
                    parts.append(repr_value(part))
            else:
                parts.append(part.accept(self))

        return f"(interp {' '.join(parts)})"

    def visit_match_expr(self, expr: Match) -> str:
        arms = " ".join(
            f"({self._pattern(arm.pattern)} {arm.body.accept(self)})" for arm in expr.arms
        )
        return f"(match {expr.scrutinee.accept(self)} {arms})"

    def _block(self, statements: list[Stmt]) -> str:
        return "(block " + " ".join(s.accept(self) for s in statements) + ")"

    def _pattern(self, pattern: object) -> str:
        if isinstance(pattern, VariantPattern):
            bindings = " ".join(token.lexeme for token in pattern.bindings)
            suffix = f" ({bindings})" if bindings else ""
            return f"({pattern.enum.lexeme}.{pattern.variant.lexeme}{suffix})"
        return "_"

    def visit_try_stmt(self, stmt: Try) -> str:
        handlers = " ".join(
            f"(except {clause.type_name.lexeme} as {clause.binding.lexeme} "
            f"{self._block(clause.body)})"
            for clause in stmt.handlers
        )
        finally_part = (
            f" (finally {self._block(stmt.finally_body)})" if stmt.finally_body is not None else ""
        )
        return f"(try {self._block(stmt.body)} {handlers}{finally_part})"

    def visit_raise_stmt(self, stmt: Raise) -> str:
        if stmt.value is None:
            return "(raise)"
        return f"(raise {stmt.value.accept(self)})"

    def visit_enum_stmt(self, stmt: EnumDecl) -> str:
        params = ""
        if stmt.type_params:
            names = ", ".join(token.lexeme for token in stmt.type_params)
            params = f"[{names}]"
        variants = []
        for variant in stmt.variants:
            payload = " ".join(display(ty) for ty in variant.payload)
            if payload:
                variants.append(f"({variant.name.lexeme} ({payload}))")
            else:
                variants.append(f"({variant.name.lexeme})")
        body = " ".join(variants)
        return f"(enum {stmt.name.lexeme}{params} {body})"

    def visit_tuple_expr(self, expr: TupleLiteral) -> str:
        inner = " ".join(element.accept(self) for element in expr.elements)
        return f"(tuple {inner})"

    def visit_map_expr(self, expr: MapLiteral) -> str:
        if not expr.entries:
            return "(map)"

        inner = " ".join(
            f"({key.accept(self)} {value.accept(self)})" for key, value in expr.entries
        )
        return f"(map {inner})"

    def visit_index_expr(self, expr: Index) -> str:
        return self._parenthesize("index", expr.object, expr.index)

    def visit_index_set_expr(self, expr: IndexSet) -> str:
        return self._parenthesize("index-set", expr.object, expr.index, expr.value)

    def visit_is_expr(self, expr: Is) -> str:
        return f"(is {expr.left.accept(self)} {display(expr.test_type)})"

    def visit_as_expr(self, expr: As) -> str:
        return f"(as {expr.left.accept(self)} {display(expr.target_type)})"

    def visit_unary_expr(self, expr: Unary) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.right)

    def visit_logical_expr(self, expr: Logical) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.left, expr.right)

    def visit_range_expr(self, expr: Range) -> str:
        return self._parenthesize("..=" if expr.inclusive else "..", expr.start, expr.end)

    def visit_assign_expr(self, expr: Assign) -> str:
        return self._parenthesize(f"= {expr.name.lexeme}", expr.value)

    def visit_variable_expr(self, expr: Variable) -> str:
        return expr.name.lexeme

    def visit_call_expr(self, expr: Call) -> str:
        name = "?call" if expr.optional else "call"
        arguments = [self.print(argument) for argument in expr.arguments]
        if expr.spread and arguments:
            arguments[-1] = f"...{arguments[-1]}"
        inner = " ".join([name, self.print(expr.callee), *arguments])
        return f"({inner})"

    def visit_conditional_expr(self, expr: Conditional) -> str:
        return self._parenthesize("if", expr.condition, expr.then_branch, expr.else_branch)

    def visit_get_expr(self, expr: Get) -> str:
        name = "?." if expr.optional else "."
        return self._parenthesize(f"{name} {expr.name.lexeme}", expr.object)

    def visit_set_expr(self, expr: Set) -> str:
        return self._parenthesize(f"set {expr.name.lexeme}", expr.object, expr.value)

    def visit_super_expr(self, expr: Super) -> str:
        return f"(super {expr.method.lexeme})"

    def visit_this_expr(self, expr: This) -> str:
        return "this"

    def _parenthesize(self, name: str, *exprs: Expr) -> str:
        if not exprs:
            return f"({name})"

        inner = " ".join(expr.accept(self) for expr in exprs)
        return f"({name} {inner})"

    # --- statements ---

    def visit_block_stmt(self, stmt: Block) -> str:
        inner = " ".join(statement.accept(self) for statement in stmt.statements)
        return f"(block {inner})" if inner else "(block)"

    def visit_import_stmt(self, stmt: Import) -> str:
        path = ".".join(token.lexeme for token in stmt.path)
        if stmt.from_import:
            names = ", ".join(
                f"{item.name.lexeme} as {item.alias.lexeme}"
                if item.alias is not None
                else item.name.lexeme
                for item in stmt.names
            )
            return f"(from {path} import {names})"
        alias = f" as {stmt.alias.lexeme}" if stmt.alias is not None else ""
        return f"(import {path}{alias})"

    def visit_class_stmt(self, stmt: Class) -> str:
        params = ""
        if stmt.type_params:
            names = ", ".join(token.lexeme for token in stmt.type_params)
            params = f"[{names}]"
        parts = [f"class {stmt.name.lexeme}{params}"]
        if stmt.superclass is not None:
            parts.append(f"(super {stmt.superclass.name.lexeme})")
        if stmt.implements:
            names = " ".join(token.lexeme for token in stmt.implements)
            parts.append(f"(implements {names})")

        for field in stmt.fields:
            keyword = "var" if field.mutable else "val"
            suffix = self._type_suffix(field.type_annotation)
            value = f" {field.initializer.accept(self)}" if field.initializer is not None else ""
            parts.append(f"({keyword} {field.name.lexeme}{suffix}{value})")

        parts.extend(method.accept(self) for method in stmt.methods)

        return f"({' '.join(parts)})"

    def visit_expression_stmt(self, stmt: Expression) -> str:
        return f"(expr {stmt.expression.accept(self)})"

    def visit_for_in_stmt(self, stmt: ForIn) -> str:
        return f"(for-in {stmt.name.lexeme} {stmt.iterable.accept(self)} {stmt.body.accept(self)})"

    def visit_lambda_expr(self, expr: Lambda) -> str:
        params = " ".join(
            ("var " if param.mutable else "")
            + ("..." if param.variadic else "")
            + param.name.lexeme
            + self._type_suffix(param.type_annotation)
            for param in expr.params
        )
        returns = f" -> {display(expr.return_type)}" if expr.return_type is not None else ""
        body = " ".join(statement.accept(self) for statement in expr.body)
        inner = f"({params})"
        return f"(lambda {inner}{returns}{f' {body}' if body else ''})"

    def _function_signature(self, stmt: Function) -> tuple[str, str]:
        params = " ".join(
            ("var " if param.mutable else "")
            + ("..." if param.variadic else "")
            + param.name.lexeme
            + self._type_suffix(param.type_annotation)
            for param in stmt.params
        )
        returns = f" -> {display(stmt.return_type)}" if stmt.return_type is not None else ""
        return f"({params})", returns

    def visit_type_alias_stmt(self, stmt: TypeAlias) -> str:
        return f"(type {stmt.name.lexeme} {display(stmt.target)})"

    def visit_interface_stmt(self, stmt: Interface) -> str:
        parts = [f"interface {stmt.name.lexeme}"]
        for method in stmt.methods:
            inner, returns = self._function_signature(method)
            if method.abstract:
                parts.append(f"(sig {method.name.lexeme} {inner}{returns})")
            else:
                body = " ".join(statement.accept(self) for statement in method.body)
                parts.append(
                    f"(fn {method.name.lexeme} {inner}{returns}{f' {body}' if body else ''})"
                )
        return f"({' '.join(parts)})"

    def visit_function_stmt(self, stmt: Function) -> str:
        inner, returns = self._function_signature(stmt)
        body = " ".join(statement.accept(self) for statement in stmt.body)
        type_params = ""
        if stmt.type_params:
            rendered = []
            for index, token in enumerate(stmt.type_params):
                text = token.lexeme
                if index < len(stmt.type_param_bounds) and stmt.type_param_bounds[index]:
                    constraints = " + ".join(
                        bound.lexeme for bound in stmt.type_param_bounds[index]
                    )
                    text = f"{text}: {constraints}"
                rendered.append(text)
            type_params = "[" + " ".join(rendered) + "]"
        return f"(fn {stmt.name.lexeme}{type_params} {inner}{returns}{f' {body}' if body else ''})"

    def visit_if_stmt(self, stmt: If) -> str:
        condition = stmt.condition.accept(self)
        then_branch = stmt.then_branch.accept(self)
        if stmt.else_branch is None:
            return f"(if {condition} {then_branch})"

        return f"(if {condition} {then_branch} {stmt.else_branch.accept(self)})"

    def visit_return_stmt(self, stmt: Return) -> str:
        if stmt.value is None:
            return "(return)"

        return f"(return {stmt.value.accept(self)})"

    def visit_destructure_stmt(self, stmt: Destructure) -> str:
        keyword = "var" if stmt.mutable else "val"
        names = self._destructure_pattern(stmt.pattern)
        suffix = self._type_suffix(stmt.type_annotation)
        value = stmt.initializer.accept(self)
        return f"({keyword}-destructure {names}{suffix} {value})"

    def _destructure_pattern(self, pattern: DestructurePattern) -> str:
        if isinstance(pattern, NamePattern):
            return pattern.name.lexeme
        inner = " ".join(self._destructure_pattern(element) for element in pattern.elements)
        return f"({inner})"

    def visit_var_stmt(self, stmt: Var) -> str:
        keyword = "var" if stmt.mutable else "val"
        suffix = self._type_suffix(stmt.type_annotation)
        value = "nil" if stmt.initializer is None else stmt.initializer.accept(self)
        return f"({keyword} {stmt.name.lexeme}{suffix} {value})"

    def _type_suffix(self, ty: Ty | None) -> str:
        if ty is None:
            return ""

        return f": {display(ty)}"

    def visit_while_stmt(self, stmt: While) -> str:
        return f"(while {stmt.condition.accept(self)} {stmt.body.accept(self)})"


# Teste manual do capítulo 6:
if __name__ == "__main__":
    # Representa a expressão: -123 * (45.67)
    expression = Binary(
        left=Unary(
            operator=Token(TokenType.MINUS, "-", None, 1),
            right=Literal(123),
        ),
        operator=Token(TokenType.STAR, "*", None, 1),
        right=Grouping(
            expression=Literal(45.67),
        ),
    )

    printer = AstPrinter()
    print(printer.print(expression))
    # Saída esperada: (* (- 123) (group 45.67))
