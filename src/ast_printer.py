from src.expr import (
    Assign,
    Binary,
    Call,
    Expr,
    Get,
    Grouping,
    Literal,
    Logical,
    Set,
    Super,
    This,
    Unary,
    Variable,
)
from src.token_type import TokenType
from src.tokens import Token
from src.values import stringify


class AstPrinter:
    """Serializa a AST em S-expressions — ferramenta de debug, não de execução."""

    def print(self, expr: Expr) -> str:
        return expr.accept(self)

    def visit_binary_expr(self, expr: Binary) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.left, expr.right)

    def visit_grouping_expr(self, expr: Grouping) -> str:
        return self._parenthesize("group", expr.expression)

    def visit_literal_expr(self, expr: Literal) -> str:
        return stringify(expr.value)

    def visit_unary_expr(self, expr: Unary) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.right)

    def visit_logical_expr(self, expr: Logical) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.left, expr.right)

    def visit_assign_expr(self, expr: Assign) -> str:
        return self._parenthesize(f"= {expr.name.lexeme}", expr.value)

    def visit_variable_expr(self, expr: Variable) -> str:
        return expr.name.lexeme

    def visit_call_expr(self, expr: Call) -> str:
        return self._parenthesize(f"call {self.print(expr.callee)}", *expr.arguments)

    def visit_get_expr(self, expr: Get) -> str:
        return self._parenthesize(f". {expr.name.lexeme}", expr.object)

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
