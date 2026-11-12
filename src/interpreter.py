from collections.abc import Callable, Iterator

from src import numeric
from src.environment import Environment
from src.error_reporter import ErrorReporter
from src.errors import (
    LoxRuntimeError,
    NativeError,
    ReturnSignal,
    immutable_redeclare_message,
)
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
    Unary,
    Variable,
)
from src.expr import Visitor as ExprVisitor
from src.lox_callable import LoxCallable
from src.lox_class import FieldInfo, LoxClass
from src.lox_function import LoxFunction
from src.lox_instance import LoxInstance
from src.lox_list import LoxList
from src.lox_map import LoxMap
from src.lox_range import LoxRange
from src.natives.len import Len
from src.natives.range import RangeNative
from src.natives.repr import Repr
from src.natives.str import Str
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
from src.token_type import TokenType
from src.tokens import Token
from src.type_test import matches_type
from src.values import stringify


class Interpreter(ExprVisitor[object], StmtVisitor[None]):
    def __init__(self, reporter: ErrorReporter | None = None) -> None:
        self.reporter: ErrorReporter = reporter if reporter is not None else ErrorReporter()
        self.globals = Environment()
        self.environment = self.globals
        self.locals: dict[Expr, int] = {}
        self.globals.define("len", Len(), mutable=False)
        self.globals.define("range", RangeNative(), mutable=False)
        self.globals.define("repr", Repr(), mutable=False)
        self.globals.define("str", Str(), mutable=False)

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

    def evaluate(self, expr: Expr) -> object:
        """Ponto de avaliação público (usado por defaults de parâmetro)."""
        return self._evaluate(expr)

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

    def _is_equal(
        self,
        a: object,
        b: object,
        seen: set[tuple[int, int]] | None = None,
    ) -> bool:
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False

        if isinstance(a, LoxList) or isinstance(b, LoxList):
            if not isinstance(a, LoxList) or not isinstance(b, LoxList):
                return False
            return self._lists_equal(a, b, set() if seen is None else seen)

        if isinstance(a, LoxMap) or isinstance(b, LoxMap):
            if not isinstance(a, LoxMap) or not isinstance(b, LoxMap):
                return False
            return self._maps_equal(a, b, set() if seen is None else seen)

        if isinstance(a, bool) or isinstance(b, bool):
            return isinstance(a, bool) and isinstance(b, bool) and a == b

        if numeric.is_number(a) and numeric.is_number(b):
            return numeric.equal(a, b)

        return a == b

    def _lists_equal(
        self,
        a: LoxList,
        b: LoxList,
        seen: set[tuple[int, int]],
    ) -> bool:
        if a is b:
            return True

        pair = (id(a), id(b))
        if pair in seen:
            return True

        seen.add(pair)
        if len(a.elements) != len(b.elements):
            return False

        for left, right in zip(a.elements, b.elements, strict=True):
            if not self._is_equal(left, right, seen):
                return False

        return True

    def _maps_equal(
        self,
        a: LoxMap,
        b: LoxMap,
        seen: set[tuple[int, int]],
    ) -> bool:
        if a is b:
            return True

        pair = (id(a), id(b))
        if pair in seen:
            return True

        seen.add(pair)
        if a.size != b.size:
            return False

        for key, value in a.items:
            found, other = b.find(key)
            if not found or not self._is_equal(value, other, seen):
                return False

        return True

    def _check_number_operand(self, operator: Token, operand: object) -> None:
        if not numeric.is_number(operand):
            raise LoxRuntimeError(operator, "Operand must be a number.")

    def _check_number_operands(self, operator: Token, *operands: object) -> None:
        for operand in operands:
            if not numeric.is_number(operand):
                raise LoxRuntimeError(operator, "Operands must be numbers.")

    def _check_int_operand(self, operator: Token, operand: object) -> None:
        if not numeric.is_int(operand):
            raise LoxRuntimeError(operator, "Operand must be an integer.")

    def _check_int_operands(self, operator: Token, *operands: object) -> None:
        for operand in operands:
            if not numeric.is_int(operand):
                raise LoxRuntimeError(operator, "Operands must be integers.")

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

    def visit_list_expr(self, expr: ListLiteral) -> object:
        return LoxList([self._evaluate(element) for element in expr.elements])

    def visit_interpolated_expr(self, expr: InterpolatedString) -> object:
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, str):
                parts.append(part)
            else:
                parts.append(stringify(self._evaluate(part)))

        return "".join(parts)

    def visit_map_expr(self, expr: MapLiteral) -> object:
        result = LoxMap()
        for key, value in expr.entries:
            entry_key = self._evaluate(key)
            if result.has(entry_key, expr.brace):
                raise LoxRuntimeError(expr.brace, "Duplicate key in map literal.")

            entry_value = self._evaluate(value)
            result.set(entry_key, entry_value, expr.brace)

        return result

    def visit_index_expr(self, expr: Index) -> object:
        ob = self._evaluate(expr.object)

        if isinstance(ob, LoxList):
            index = self._evaluate(expr.index)
            return ob.get(index, expr.bracket)

        if isinstance(ob, LoxMap):
            key = self._evaluate(expr.index)
            return ob.get(key, expr.bracket)

        raise LoxRuntimeError(expr.bracket, "Only lists and maps can be indexed.")

    def visit_index_set_expr(self, expr: IndexSet) -> object:
        ob = self._evaluate(expr.object)

        if isinstance(ob, LoxList):
            index = self._evaluate(expr.index)
            value = self._evaluate(expr.value)
            return ob.set(index, value, expr.bracket)

        if isinstance(ob, LoxMap):
            key = self._evaluate(expr.index)
            value = self._evaluate(expr.value)
            return ob.set(key, value, expr.bracket)

        raise LoxRuntimeError(expr.bracket, "Only lists and maps can be indexed.")

    def visit_grouping_expr(self, expr: Grouping) -> object:
        return self._evaluate(expr.expression)

    def visit_is_expr(self, expr: Is) -> object:
        value = self._evaluate(expr.left)
        return matches_type(value, expr.test_type)

    def visit_range_expr(self, expr: Range) -> object:
        start = self._evaluate(expr.start)
        end = self._evaluate(expr.end)

        if not numeric.is_int(start):
            raise LoxRuntimeError(expr.operator, "Range bounds must be integers.")
        if not numeric.is_int(end):
            raise LoxRuntimeError(expr.operator, "Range bounds must be integers.")

        return LoxRange(start, end)

    def visit_unary_expr(self, expr: Unary) -> object:
        right = self._evaluate(expr.right)

        match expr.operator.type:
            case TokenType.BANG:
                return not self._is_truthy(right)
            case TokenType.MINUS:
                self._check_number_operand(expr.operator, right)
                return numeric.negate(right)
            case TokenType.TILDE:
                self._check_int_operand(expr.operator, right)
                return numeric.bit_not(right)

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
            case TokenType.SLASH_SLASH:
                self._check_int_operands(expr.operator, left, right)
                if right == 0:
                    raise LoxRuntimeError(expr.operator, "Division by zero not allowed")
                return numeric.int_divide(left, right)
            case TokenType.PERCENT:
                self._check_number_operands(expr.operator, left, right)
                if right == 0:
                    raise LoxRuntimeError(expr.operator, "Modulo by zero not allowed")
                return numeric.modulo(left, right)
            case TokenType.STAR:
                self._check_number_operands(expr.operator, left, right)
                return numeric.multiply(left, right)
            case TokenType.STAR_STAR:
                self._check_number_operands(expr.operator, left, right)
                if numeric.is_int(left) and numeric.is_int(right) and right < 0:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Negative exponent not allowed for integer power.",
                    )
                try:
                    return numeric.power(left, right)
                except ValueError:
                    raise LoxRuntimeError(
                        expr.operator, "Invalid exponentiation."
                    ) from None
                except OverflowError:
                    raise LoxRuntimeError(
                        expr.operator, "Exponentiation overflow."
                    ) from None
            case TokenType.AMPERSAND:
                self._check_int_operands(expr.operator, left, right)
                return numeric.bit_and(left, right)
            case TokenType.PIPE:
                self._check_int_operands(expr.operator, left, right)
                return numeric.bit_or(left, right)
            case TokenType.CARET:
                self._check_int_operands(expr.operator, left, right)
                return numeric.bit_xor(left, right)
            case TokenType.LESS_LESS:
                return self._shift(expr.operator, left, right, numeric.shift_left)
            case TokenType.GREATER_GREATER:
                return self._shift(expr.operator, left, right, numeric.shift_right)
            case TokenType.GREATER_GREATER_GREATER:
                return self._shift(
                    expr.operator, left, right, numeric.shift_right_logical
                )
            case TokenType.BANG_EQUAL:
                return not self._is_equal(left, right)
            case TokenType.EQUAL_EQUAL:
                return self._is_equal(left, right)

        return None

    def _shift(
        self,
        operator: Token,
        left: object,
        right: object,
        operation: Callable[[object, object], int],
    ) -> int:
        self._check_int_operands(operator, left, right)
        assert numeric.is_int(right)
        if not 0 <= right <= 63:
            raise LoxRuntimeError(operator, "Shift count must be between 0 and 63.")

        return operation(left, right)

    def visit_call_expr(self, expr: Call) -> object:
        callee = self._evaluate(expr.callee)

        if expr.optional and callee is None:
            return None

        arguments: list[object] = []
        for argument in expr.arguments:
            arguments.append(self._evaluate(argument))

        if not isinstance(callee, LoxCallable):
            raise LoxRuntimeError(expr.paren, "Can only call functions and classes.")

        minimum = callee.min_arity()
        maximum = callee.max_arity()
        count = len(arguments)

        if not minimum <= count <= maximum:
            if minimum == maximum:
                message = f"Expected {minimum} arguments but got {count}."
            elif count < minimum:
                message = f"Expected at least {minimum} arguments but got {count}."
            else:
                message = f"Expected {minimum} to {maximum} arguments but got {count}."

            raise LoxRuntimeError(expr.paren, message)

        try:
            return callee.call(self, arguments)
        except NativeError as error:
            raise LoxRuntimeError(expr.paren, str(error)) from error

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

        fields: dict[str, FieldInfo] = {}
        if superclass is not None:
            fields.update(superclass.fields)

        for field in stmt.fields:
            if field.name.lexeme in fields:
                raise LoxRuntimeError(
                    field.name, f"Field '{field.name.lexeme}' already declared."
                )

            fields[field.name.lexeme] = FieldInfo(
                field.name, field.initializer, field.mutable
            )

        klass = LoxClass(stmt.name.lexeme, superclass, methods, fields)

        if stmt.superclass is not None:
            enclosing = self.environment.enclosing
            assert enclosing is not None
            self.environment = enclosing

        self.environment.assign(stmt.name, klass)

    def visit_expression_stmt(self, stmt: Expression) -> None:
        self._evaluate(stmt.expression)

    def visit_get_expr(self, expr: Get) -> object:
        ob = self._evaluate(expr.object)

        if expr.optional and ob is None:
            return None

        if isinstance(ob, LoxInstance):
            return ob.get(expr.name)

        if isinstance(ob, LoxList):
            return ob.get_method(expr.name)

        if isinstance(ob, LoxMap):
            return ob.get_method(expr.name)

        raise LoxRuntimeError(expr.name, "Only instances have properties.")

    def visit_conditional_expr(self, expr: Conditional) -> object:
        if self._is_truthy(self._evaluate(expr.condition)):
            return self._evaluate(expr.then_branch)

        return self._evaluate(expr.else_branch)

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

    def visit_lambda_expr(self, expr: Lambda) -> object:
        return LoxFunction(expr, self.environment, False)

    def visit_for_in_stmt(self, stmt: ForIn) -> None:
        iterable = self._evaluate(stmt.iterable)

        for value in self._iterate(stmt.name, iterable):
            environment = Environment(self.environment)
            environment.define(stmt.name.lexeme, value, mutable=False)
            self.execute_block([stmt.body], environment)

    def _iterate(self, name: Token, iterable: object) -> Iterator[object]:
        if isinstance(iterable, LoxRange):
            return iter(range(iterable.start, iterable.end, iterable.step))
        if isinstance(iterable, str):
            return iter(iterable)
        if isinstance(iterable, LoxList):
            return self._iterate_list(name, iterable)
        if isinstance(iterable, LoxMap):
            return self._iterate_map(name, iterable)

        raise LoxRuntimeError(
            name, "Can only iterate over a range, a list, a map or a string."
        )

    def _iterate_list(self, name: Token, values: LoxList) -> Iterator[object]:
        version = values.version
        index = 0

        while index < len(values.elements):
            if values.version != version:
                raise LoxRuntimeError(
                    name, "Can't modify a list while iterating over it."
                )

            yield values.elements[index]
            index += 1

        if values.version != version:
            raise LoxRuntimeError(
                name, "Can't modify a list while iterating over it."
            )

    def _iterate_map(self, name: Token, values: LoxMap) -> Iterator[object]:
        version = values.version
        keys = values.keys()
        index = 0

        while index < len(keys):
            if values.version != version:
                raise LoxRuntimeError(
                    name, "Can't modify a map while iterating over it."
                )

            yield keys[index]
            index += 1

        if values.version != version:
            raise LoxRuntimeError(
                name, "Can't modify a map while iterating over it."
            )

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

        if expr.operator.type is TokenType.QUESTION_QUESTION:
            return left if left is not None else self._evaluate(expr.right)

        if expr.operator.type == TokenType.OR:
            if self._is_truthy(left):
                return left
        elif not self._is_truthy(left):  # TokenType.AND
            return left

        return self._evaluate(expr.right)

    def visit_while_stmt(self, stmt: While) -> None:
        while self._is_truthy(self._evaluate(stmt.condition)):
            self._execute(stmt.body)
