from src.error_reporter import ErrorReporter
from src.errors import LoxRuntimeError
from src.expr import Binary, Expr, Grouping, Literal, Unary, Visitor
from src.token import Token
from src.token_type import TokenType


class Interpreter(Visitor[object]):
    def interpret(self, expression: Expr):
        try:
            value = self._evaluate(expression)
            print(self._stringify(value))
        except LoxRuntimeError as e:
            ErrorReporter.runtime_error(e)

    def _evaluate(self, expr: Expr) -> object:
        return expr.accept(self)

    def _is_truthy(self, obj: object) -> bool:
        if obj is None:
            return False
        if isinstance(obj, bool):
            return bool(obj)
        return True

    def _is_equal(self, a: object, b: object) -> bool:
        if a is None and b is None:
            return True
        if a is None:
            return False

        if type(a) is not type(b) and (isinstance(a, bool) or isinstance(b, bool)):
            return False

        return a == b

    def _check_number_operands(self, operator: Token, *operands: object) -> None:
        for operand in operands:
            if isinstance(operand, float) and not isinstance(operand, bool):
                continue

            message = (
                "Operand must be a number."
                if len(operands) == 1
                else "Operands must be numbers."
            )
            raise LoxRuntimeError(operator, message)

    def _stringify(self, obj: object) -> str:
        if obj is None:
            return "nil"
        if isinstance(obj, bool):
            return str(obj).lower()
        if isinstance(obj, float):
            if obj.is_integer():
                return str(int(obj))
            return str(obj)

        return str(obj)

    def visit_literal_expr(self, expr: Literal) -> object:
        return expr.value

    def visit_grouping_expr(self, expr: Grouping) -> object:
        return self._evaluate(expr.expression)

    def visit_unary_expr(self, expr: Unary) -> object:
        right = self._evaluate(expr.right)

        match expr.operator.type:
            case TokenType.BANG:
                return self._is_truthy(right)
            case TokenType.MINUS:
                self._check_number_operands(expr.operator, right)
                return -float(right)

        return None

    def visit_binary_expr(self, expr: Binary) -> object:
        left = self._evaluate(expr.left)
        right = self._evaluate(expr.right)

        match expr.operator.type:
            case TokenType.GREATER:
                self._check_number_operands(expr.operator, left, right)
                return float(left) > float(right)
            case TokenType.GREATER_EQUAL:
                self._check_number_operands(expr.operator, left, right)
                return float(left) >= float(right)
            case TokenType.LESS:
                self._check_number_operands(expr.operator, left, right)
                return float(left) < float(right)
            case TokenType.LESS_EQUAL:
                self._check_number_operands(expr.operator, left, right)
                return float(left) <= float(right)
            case TokenType.MINUS:
                self._check_number_operands(expr.operator, left, right)
                return float(left) - float(right)
            case TokenType.PLUS:
                if isinstance(left, float) and isinstance(right, float):
                    return float(left) + float(right)
                if isinstance(left, str) and isinstance(right, str):
                    return str(left) + str(right)
                raise LoxRuntimeError(
                    expr.operator, "Operands must be two numbers or two strings."
                )
            case TokenType.SLASH:
                self._check_number_operands(expr.operator, left, right)
                return float(left) / float(right)
            case TokenType.STAR:
                self._check_number_operands(expr.operator, left, right)
                return float(left) * float(right)
            case TokenType.BANG_EQUAL:
                return not self._is_equal(left, right)
            case TokenType.EQUAL_EQUAL:
                return self._is_equal(left, right)

        return None
