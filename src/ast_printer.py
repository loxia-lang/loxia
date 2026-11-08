from src.expr import Binary, Expr, Grouping, Literal, Unary, Visitor
from src.token import Token
from src.token_type import TokenType


class AstPrinter:

    def print(self, expr: Expr) -> str:
        return expr.accept(self)

    def visit_binary_expr(self, expr: Binary) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.left, expr.right)

    def visit_grouping_expr(self, expr: Grouping) -> str:
        return self._parenthesize("group", expr.expression)

    def visit_literal_expr(self, expr: Literal) -> str:
        if expr.value is None:
            return "nil"
        return str(expr.value)

    def visit_unary_expr(self, expr: Unary) -> str:
        return self._parenthesize(expr.operator.lexeme, expr.right)

    def _parenthesize(self, name: str, *exprs: Expr) -> str:
        inner = " ".join(expr.accept(self) for expr in exprs)
        return f"({name} {inner})"


# Teste manual do capítulo:
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