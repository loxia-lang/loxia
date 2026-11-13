from src.execution.values import repr_value
from src.frontend.expr import (
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
    Range,
    Set,
    Super,
    This,
    TupleLiteral,
    Unary,
    Variable,
)
from src.frontend.stmt import (
    Block,
    Class,
    Destructure,
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
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token
from src.frontend.ty import Ty, display


class AstPrinter:
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

    def visit_tuple_expr(self, expr: TupleLiteral) -> str:
        inner = " ".join(element.accept(self) for element in expr.elements)
        return f"(tuple {inner})"

    def visit_map_expr(self, expr: MapLiteral) -> str:
        if not expr.entries:
            return "(map)"

        inner = " ".join(
            f"({key.accept(self)} {value.accept(self)})"
            for key, value in expr.entries
        )
        return f"(map {inner})"

    def visit_index_expr(self, expr: Index) -> str:
        return self._parenthesize("index", expr.object, expr.index)

    def visit_index_set_expr(self, expr: IndexSet) -> str:
        return self._parenthesize(
            "index-set", expr.object, expr.index, expr.value
        )

    def visit_is_expr(self, expr: Is) -> str:
        return f"(is {expr.left.accept(self)} {display(expr.test_type)})"

    def visit_as_expr(self, expr: As) -> str:
        return f"(as {expr.left.accept(self)} {display(expr.target_type)})"

    def visit_unary_expr(self, expr: Unary) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.right)

    def visit_logical_expr(self, expr: Logical) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.left, expr.right)

    def visit_range_expr(self, expr: Range) -> str:
        return self._parenthesize("..", expr.start, expr.end)

    def visit_assign_expr(self, expr: Assign) -> str:
        return self._parenthesize(f"= {expr.name.lexeme}", expr.value)

    def visit_variable_expr(self, expr: Variable) -> str:
        return expr.name.lexeme

    def visit_call_expr(self, expr: Call) -> str:
        name = "?call" if expr.optional else "call"
        return self._parenthesize(f"{name} {self.print(expr.callee)}", *expr.arguments)

    def visit_conditional_expr(self, expr: Conditional) -> str:
        return self._parenthesize(
            "if", expr.condition, expr.then_branch, expr.else_branch
        )

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

    def visit_class_stmt(self, stmt: Class) -> str:
        params = ""
        if stmt.type_params:
            names = ", ".join(token.lexeme for token in stmt.type_params)
            params = f"[{names}]"
        parts = [f"class {stmt.name.lexeme}{params}"]
        if stmt.superclass is not None:
            parts.append(f"(super {stmt.superclass.name.lexeme})")

        for field in stmt.fields:
            keyword = "var" if field.mutable else "val"
            suffix = self._type_suffix(field.type_annotation)
            value = (
                f" {field.initializer.accept(self)}"
                if field.initializer is not None
                else ""
            )
            parts.append(f"({keyword} {field.name.lexeme}{suffix}{value})")

        parts.extend(method.accept(self) for method in stmt.methods)

        return f"({' '.join(parts)})"

    def visit_expression_stmt(self, stmt: Expression) -> str:
        return f"(expr {stmt.expression.accept(self)})"

    def visit_for_in_stmt(self, stmt: ForIn) -> str:
        return (
            f"(for-in {stmt.name.lexeme} {stmt.iterable.accept(self)} "
            f"{stmt.body.accept(self)})"
        )

    def visit_lambda_expr(self, expr: Lambda) -> str:
        params = " ".join(
            ("var " if param.mutable else "")
            + param.name.lexeme
            + self._type_suffix(param.type_annotation)
            for param in expr.params
        )
        returns = (
            f" -> {display(expr.return_type)}"
            if expr.return_type is not None
            else ""
        )
        body = " ".join(statement.accept(self) for statement in expr.body)
        inner = f"({params})"
        return f"(lambda {inner}{returns}{f' {body}' if body else ''})"

    def visit_function_stmt(self, stmt: Function) -> str:
        params = " ".join(
            ("var " if param.mutable else "")
            + param.name.lexeme
            + self._type_suffix(param.type_annotation)
            for param in stmt.params
        )
        returns = (
            f" -> {display(stmt.return_type)}"
            if stmt.return_type is not None
            else ""
        )
        body = " ".join(statement.accept(self) for statement in stmt.body)
        inner = f"({params})"
        type_params = (
            "[" + " ".join(token.lexeme for token in stmt.type_params) + "]"
            if stmt.type_params
            else ""
        )
        return (
            f"(fn {stmt.name.lexeme}{type_params} {inner}{returns}"
            f"{f' {body}' if body else ''})"
        )

    def visit_if_stmt(self, stmt: If) -> str:
        condition = stmt.condition.accept(self)
        then_branch = stmt.then_branch.accept(self)
        if stmt.else_branch is None:
            return f"(if {condition} {then_branch})"

        return f"(if {condition} {then_branch} {stmt.else_branch.accept(self)})"

    def visit_print_stmt(self, stmt: Print) -> str:
        return f"(print {stmt.expression.accept(self)})"

    def visit_return_stmt(self, stmt: Return) -> str:
        if stmt.value is None:
            return "(return)"

        return f"(return {stmt.value.accept(self)})"

    def visit_destructure_stmt(self, stmt: Destructure) -> str:
        keyword = "var" if stmt.mutable else "val"
        names = " ".join(name.lexeme for name in stmt.names)
        suffix = self._type_suffix(stmt.type_annotation)
        value = stmt.initializer.accept(self)
        return f"({keyword}-destructure ({names}){suffix} {value})"

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
