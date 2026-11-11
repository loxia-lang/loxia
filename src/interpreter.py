from expr import Logical
from src.environment import Environment
from src.error_reporter import ErrorReporter
from src.errors import LoxRuntimeError
from src.expr import Assign, Binary, Expr, Grouping, Literal, Unary, Variable
from src.expr import Visitor as ExprVisitor
from src.stmt import Block, Expression, Print, Stmt, Var
from src.stmt import Visitor as StmtVisitor
from src.token import Token
from src.token_type import TokenType
from stmt import If, While


class Interpreter(ExprVisitor[object], StmtVisitor[None]):
    def __init__(self) -> None:
        self.environment = Environment()

    def interpret(self, statements: list[Stmt]):
        try:
            for statement in statements:
                self._execute(statement)
        except LoxRuntimeError as e:
            ErrorReporter.runtime_error(e)

    def _evaluate(self, expr: Expr) -> object:
        return expr.accept(self)

    def _execute(self, stmt: Stmt) -> None:
        stmt.accept(self)

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

    def _execute_block(self, statements: list[Stmt], environment: Environment) -> None:
        previous = self.environment

        try:
            self.environment = environment

            for st in statements:
                self._execute(st)
        finally:
            self.environment = previous

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
                assert isinstance(right, float)
                return -right

        return None

    def visit_binary_expr(self, expr: Binary) -> object:
        left = self._evaluate(expr.left)
        right = self._evaluate(expr.right)

        # TODO(desafio-cap-7): Suportar comparadores relacionais (>, >=, <, <=) para strings.
        # Regra: permitir apenas entre dois números (float) OU duas strings (ordem lexicográfica).
        # Jamais misturar tipos diferentes (ex: 3 < "pancake") para evitar coerções confusas à la JS/Python 2.

        match expr.operator.type:
            case TokenType.GREATER:
                self._check_number_operands(expr.operator, left, right)
                assert isinstance(left, float) and isinstance(right, float)
                return left > right
            case TokenType.GREATER_EQUAL:
                self._check_number_operands(expr.operator, left, right)
                assert isinstance(left, float) and isinstance(right, float)
                return left >= right
            case TokenType.LESS:
                self._check_number_operands(expr.operator, left, right)
                assert isinstance(left, float) and isinstance(right, float)
                return left < right
            case TokenType.LESS_EQUAL:
                self._check_number_operands(expr.operator, left, right)
                assert isinstance(left, float) and isinstance(right, float)
                return left <= right
            case TokenType.MINUS:
                self._check_number_operands(expr.operator, left, right)
                assert isinstance(left, float) and isinstance(right, float)
                return left - right
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
                if right == 0:
                    raise LoxRuntimeError(expr.operator, "Division by zero not allowed")
                assert isinstance(left, float) and isinstance(right, float)
                return left / right
            case TokenType.STAR:
                self._check_number_operands(expr.operator, left, right)
                assert isinstance(left, float) and isinstance(right, float)
                return left * right
            case TokenType.BANG_EQUAL:
                return not self._is_equal(left, right)
            case TokenType.EQUAL_EQUAL:
                return self._is_equal(left, right)

        return None

    def visit_expression_stmt(self, stmt: Expression) -> None:
        self._evaluate(stmt.expression)

    def visit_print_stmt(self, stmt: Print) -> None:
        value = self._evaluate(stmt.expression)
        print(self._stringify(value))

    def visit_var_stmt(self, stmt: Var) -> None:
        val: object = object()
        if stmt.initializer is not None:
            val = self._evaluate(stmt.initializer)

        self.environment.define(stmt.name.lexeme, val)

    def visit_variable_expr(self, expr: Variable) -> object:
        return self.environment.get(expr.name)

    def visit_assign_expr(self, expr: Assign) -> object:
        val = self._evaluate(expr.value)
        self.environment.assign(expr.name, val)
        return val

    def visit_block_stmt(self, stmt: Block) -> None:
        self._execute_block(stmt.statements, Environment(self.environment))

    def visit_if_stmt(self, stmt: If) -> None:
        if self._is_truthy(self._evaluate(stmt.condition)):
            self._execute(stmt.then_branch)
        elif stmt.else_branch is not None:
            self._execute(stmt.else_branch)

    def visit_logical_expr(self, expr: Logical) -> object:
        left = self._evaluate(expr.left)

        if expr.operator.type == TokenType.OR:
            if self._is_truthy(left):
                return left
        elif not self._is_truthy(left):  # TokenType.AND
            return left

        return self._evaluate(expr.right)

    def visit_while_stmt(self, stmt: While) -> None:
        while self._is_truthy(self._evaluate(stmt.condition)):
            self._execute(stmt.body)
