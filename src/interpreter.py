from src import numeric
from src.environment import Environment
from src.error_reporter import ErrorReporter
from src.errors import (
    LoxRuntimeError,
    ReturnSignal,
    immutable_redeclare_message,
)
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
from src.expr import Visitor as ExprVisitor
from src.lox_callable import LoxCallable
from src.lox_class import LoxClass
from src.lox_function import LoxFunction
from src.lox_instance import LoxInstance
from src.natives.clock import Clock
from src.stmt import Block, Class, Expression, Function, If, Print, Return, Stmt, Var, While
from src.stmt import Visitor as StmtVisitor
from src.token_type import TokenType
from src.tokens import Token
from src.values import stringify


class Interpreter(ExprVisitor[object], StmtVisitor[None]):
    def __init__(self, reporter: ErrorReporter | None = None) -> None:
        self.reporter: ErrorReporter = reporter if reporter is not None else ErrorReporter()
        self.globals = Environment()
        self.environment = self.globals
        self.locals: dict[Expr, int] = {}
        self.globals.define("clock", Clock())

    def interpret(self, statements: list[Stmt]) -> None:
        try:
            for statement in statements:
                self._execute(statement)
        except LoxRuntimeError as e:
            self.reporter.runtime_error(e)

    def resolve(self, expr: Expr, depth: int) -> None:
        self.locals[expr] = depth

    def _evaluate(self, expr: Expr) -> object:
        return expr.accept(self)

    def _execute(self, stmt: Stmt) -> None:
        stmt.accept(self)

    def _reject_immutable_redeclaration(self, name: Token) -> None:
        if self.environment is not self.globals:
            return

        if name.lexeme in self.environment.values and not self.environment.is_mutable(
            name.lexeme
        ):
            raise LoxRuntimeError(name, immutable_redeclare_message(name.lexeme))

    def _is_truthy(self, obj: object) -> bool:
        if obj is None:
            return False
        if isinstance(obj, bool):
            return bool(obj)
        return True

    def _is_equal(self, a: object, b: object) -> bool:
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False

        if isinstance(a, bool) or isinstance(b, bool):
            return isinstance(a, bool) and isinstance(b, bool) and a == b

        if numeric.is_number(a) and numeric.is_number(b):
            return numeric.equal(a, b)

        return a == b

    def _check_number_operand(self, operator: Token, operand: object) -> None:
        if not numeric.is_number(operand):
            raise LoxRuntimeError(operator, "Operand must be a number.")

    def _check_number_operands(self, operator: Token, *operands: object) -> None:
        for operand in operands:
            if not numeric.is_number(operand):
                raise LoxRuntimeError(operator, "Operands must be numbers.")

    def execute_block(self, statements: list[Stmt], environment: Environment) -> None:
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
                return not self._is_truthy(right)
            case TokenType.MINUS:
                self._check_number_operand(expr.operator, right)
                return numeric.negate(right)

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
                comparison = numeric.compare(left, right)
                return comparison is not None and comparison > 0
            case TokenType.GREATER_EQUAL:
                self._check_number_operands(expr.operator, left, right)
                comparison = numeric.compare(left, right)
                return comparison is not None and comparison >= 0
            case TokenType.LESS:
                self._check_number_operands(expr.operator, left, right)
                comparison = numeric.compare(left, right)
                return comparison is not None and comparison < 0
            case TokenType.LESS_EQUAL:
                self._check_number_operands(expr.operator, left, right)
                comparison = numeric.compare(left, right)
                return comparison is not None and comparison <= 0
            case TokenType.MINUS:
                self._check_number_operands(expr.operator, left, right)
                return numeric.subtract(left, right)
            case TokenType.PLUS:
                if numeric.is_number(left) and numeric.is_number(right):
                    return numeric.add(left, right)
                if isinstance(left, str) and isinstance(right, str):
                    return str(left) + str(right)
                raise LoxRuntimeError(
                    expr.operator, "Operands must be two numbers or two strings."
                )
            case TokenType.SLASH:
                self._check_number_operands(expr.operator, left, right)
                if right == 0:
                    raise LoxRuntimeError(expr.operator, "Division by zero not allowed")
                return numeric.divide(left, right)
            case TokenType.PERCENT:
                self._check_number_operands(expr.operator, left, right)
                if right == 0:
                    raise LoxRuntimeError(expr.operator, "Modulo by zero not allowed")
                return numeric.modulo(left, right)
            case TokenType.STAR:
                self._check_number_operands(expr.operator, left, right)
                return numeric.multiply(left, right)
            case TokenType.BANG_EQUAL:
                return not self._is_equal(left, right)
            case TokenType.EQUAL_EQUAL:
                return self._is_equal(left, right)

        return None

    def visit_call_expr(self, expr: Call) -> object:
        callee = self._evaluate(expr.callee)

        arguments: list[object] = []
        for argument in expr.arguments:
            arguments.append(self._evaluate(argument))

        if not isinstance(callee, LoxCallable):
            raise LoxRuntimeError(expr.paren, "Can only call functions and classes.")

        if len(arguments) != callee.arity():
            raise LoxRuntimeError(
                expr.paren,
                f"Expected {callee.arity()} arguments but got {len(arguments)}.",
            )

        return callee.call(self, arguments)

    def visit_class_stmt(self, stmt: Class) -> None:
        self._reject_immutable_redeclaration(stmt.name)

        superclass: LoxClass | None = None
        if stmt.superclass is not None:
            candidate = self._evaluate(stmt.superclass)
            if not isinstance(candidate, LoxClass):
                raise LoxRuntimeError(
                    stmt.superclass.name, "Superclass must be a class."
                )

            superclass = candidate

        self.environment.define(stmt.name.lexeme, None)

        if stmt.superclass is not None:
            self.environment = Environment(self.environment)
            self.environment.define("super", superclass)

        methods: dict[str, LoxFunction] = {}
        for method in stmt.methods:
            function = LoxFunction(
                method, self.environment, method.name.lexeme == "init"
            )
            methods[method.name.lexeme] = function

        klass = LoxClass(stmt.name.lexeme, superclass, methods)

        if stmt.superclass is not None:
            enclosing = self.environment.enclosing
            assert enclosing is not None
            self.environment = enclosing

        self.environment.assign(stmt.name, klass)

    def visit_expression_stmt(self, stmt: Expression) -> None:
        self._evaluate(stmt.expression)

    def visit_get_expr(self, expr: Get) -> object:
        ob = self._evaluate(expr.object)

        if isinstance(ob, LoxInstance):
            return ob.get(expr.name)

        raise LoxRuntimeError(expr.name, "Only instances have properties.")

    def visit_set_expr(self, expr: Set) -> object:
        ob = self._evaluate(expr.object)

        if not isinstance(ob, LoxInstance):
            raise LoxRuntimeError(expr.name, "Only instances have fields.")

        value = self._evaluate(expr.value)
        ob.set(expr.name, value)
        return value

    def visit_super_expr(self, expr: Super) -> object:
        distance = self.locals.get(expr)
        assert distance is not None

        superclass = self.environment.get_at(distance, "super")
        assert isinstance(superclass, LoxClass)

        ob = self.environment.get_at(distance - 1, "this")
        assert isinstance(ob, LoxInstance)

        method = superclass.find_method(expr.method.lexeme)
        if method is None:
            raise LoxRuntimeError(
                expr.method, f"Undefined property '{expr.method.lexeme}'."
            )

        return method.bind(ob)

    def visit_this_expr(self, expr: This) -> object:
        return self.look_up_variable(expr.keyword, expr)

    def visit_function_stmt(self, stmt: Function) -> None:
        self._reject_immutable_redeclaration(stmt.name)

        function = LoxFunction(stmt, self.environment, False)
        self.environment.define(stmt.name.lexeme, function)

    def visit_print_stmt(self, stmt: Print) -> None:
        value = self._evaluate(stmt.expression)
        print(stringify(value))

    def visit_return_stmt(self, stmt: Return) -> None:
        value: object = None
        if stmt.value is not None:
            value = self._evaluate(stmt.value)

        raise ReturnSignal(stmt.keyword, value)

    def visit_var_stmt(self, stmt: Var) -> None:
        self._reject_immutable_redeclaration(stmt.name)

        val: object = None
        if stmt.initializer is not None:
            val = self._evaluate(stmt.initializer)

        self.environment.define(stmt.name.lexeme, val, stmt.mutable)

    def visit_variable_expr(self, expr: Variable) -> object:
        return self.look_up_variable(expr.name, expr)

    def look_up_variable(self, name: Token, expr: Expr) -> object:
        distance = self.locals.get(expr)
        if distance is not None:
            return self.environment.get_at(distance, name.lexeme)

        return self.globals.get(name)

    def visit_assign_expr(self, expr: Assign) -> object:
        value = self._evaluate(expr.value)

        distance = self.locals.get(expr)
        if distance is not None:
            self.environment.assign_at(distance, expr.name, value)
        else:
            self.globals.assign(expr.name, value)

        return value

    def visit_block_stmt(self, stmt: Block) -> None:
        self.execute_block(stmt.statements, Environment(self.environment))

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
