# SPDX-License-Identifier: MIT OR Apache-2.0
from collections.abc import Callable, Iterator
from typing import Any

from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.diagnostic import Frame, Trace
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.errors import (
    LoxRaise,
    LoxRuntimeError,
    NativeError,
    ReturnSignal,
    immutable_redeclare_message,
)
from loxia_core.execution import numeric
from loxia_core.execution.environment import Environment
from loxia_core.execution.limits import (
    MAX_CALL_DEPTH,
    TRACE_HEAD,
    TRACE_TAIL,
    ensure_recursion_budget,
)
from loxia_core.execution.lox_callable import LoxCallable
from loxia_core.execution.lox_class import FieldInfo, LoxClass
from loxia_core.execution.lox_enum import LoxEnumObject, LoxEnumValue
from loxia_core.execution.lox_exception import (
    LoxExceptionClass,
    LoxExceptionValue,
    format_site,
)
from loxia_core.execution.lox_function import LoxFunction
from loxia_core.execution.lox_instance import LoxInstance
from loxia_core.execution.lox_interface import LoxInterface
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.lox_map import LoxMap
from loxia_core.execution.lox_range import LoxRange
from loxia_core.execution.lox_tuple import LoxTuple
from loxia_core.execution.native_module import NativeModule
from loxia_core.execution.natives.chars import Chars
from loxia_core.execution.natives.len import Len
from loxia_core.execution.natives.modules import float_module, int_module, math_module
from loxia_core.execution.natives.print import Print
from loxia_core.execution.natives.range import RangeNative
from loxia_core.execution.natives.repr import Repr
from loxia_core.execution.natives.str import Str
from loxia_core.execution.primitives import (
    PRIMITIVES,
    PrimitiveCallable,
    is_sandbox_denied,
)
from loxia_core.execution.type_test import matches_type
from loxia_core.execution.values import stringify
from loxia_core.frontend.destructuring import (
    DestructurePattern,
    NamePattern,
    first_token,
)
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
    WildcardPattern,
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
from loxia_core.frontend.ty import (
    ANY,
    FLOAT,
    INT,
    ClassTy,
    EnumTy,
    FnTy,
    ListTy,
    MapTy,
    TupleTy,
    Ty,
    TyVar,
    UnionTy,
    display,
)

_RELATIONAL = frozenset(
    {
        TokenType.GREATER,
        TokenType.GREATER_EQUAL,
        TokenType.LESS,
        TokenType.LESS_EQUAL,
    }
)


class Interpreter(ExprVisitor[object], StmtVisitor[None]):
    def __init__(
        self,
        reporter: ErrorReporter | None = None,
        *,
        checked_overflow: bool = False,
        argv: list[str] | None = None,
        sandbox: bool = False,
    ) -> None:
        ensure_recursion_budget()
        self.reporter: ErrorReporter = reporter if reporter is not None else ErrorReporter()
        self.checked_overflow = checked_overflow
        self.argv = list(argv or [])
        self.sandbox = sandbox
        self._call_depth = 0
        # Tuplas leves no caminho feliz; `Frame` só é materializado ao capturar o trace.
        self._frames: list[tuple[str, str, int, int]] = []
        self._call_site: Token | None = None
        self.globals = Environment()
        self.environment = self.globals
        self._type_aliases: dict[str, Ty] = {}
        self.locals: dict[Expr, int] = {}
        self.interfaces: dict[str, LoxInterface] = {}
        self._current_exception: object | None = None
        self.globals.define("chars", Chars(), mutable=False)
        self.globals.define("len", Len(), mutable=False)
        self.globals.define("print", Print(), mutable=False)
        self.globals.define("range", RangeNative(), mutable=False)
        self.globals.define("repr", Repr(), mutable=False)
        self.globals.define("str", Str(), mutable=False)
        primitive_modules: dict[str, dict[str, object]] = {}
        for primitive in PRIMITIVES:
            callable_ = PrimitiveCallable(
                primitive,
                sandboxed=sandbox and is_sandbox_denied(primitive.lox),
            )
            if "." in primitive.lox:
                module, member = primitive.lox.split(".", 1)
                primitive_modules.setdefault(module, {})[member] = callable_
            else:
                self.globals.define(primitive.lox, callable_, mutable=False)
        for module, members in primitive_modules.items():
            self.globals.define(module, NativeModule(module, members), mutable=False)
        self.globals.define("Int", int_module(), mutable=False)
        self.globals.define("Float", float_module(), mutable=False)
        self.globals.define("math", math_module(), mutable=False)
        self.globals.define(
            "Result",
            LoxEnumObject("Result", {"Ok": 1, "Err": 1}),
            mutable=False,
        )
        exception_class = LoxExceptionClass("Exception", None)
        self.globals.define("Exception", exception_class, mutable=False)
        self.globals.define(
            "RuntimeError",
            LoxExceptionClass("RuntimeError", exception_class),
            mutable=False,
        )

    def interpret(self, statements: list[Stmt]) -> None:
        self._call_depth = 0
        self._frames.clear()
        self._call_site = None
        for statement in statements:
            if isinstance(statement, TypeAlias):
                self._type_aliases[statement.name.lexeme] = statement.target
        try:
            for statement in statements:
                self._execute(statement)
        except LoxRaise as raised:
            error = LoxRuntimeError(
                raised.token,
                f"Unhandled exception: {stringify(raised.value)}",
                code=Code.UNHANDLED_EXCEPTION,
            )
            error.trace = raised.trace
            self._capture_trace(error)
            self.reporter.runtime_error(error)
        except LoxRuntimeError as e:
            self._capture_trace(e)
            self.reporter.runtime_error(e)
        finally:
            self.close_handles()

    def close_handles(self) -> None:
        """Fecha handles ambientais de uma execução (I3/ADR-0119)."""
        for attribute in ("fs_handles", "proc_handles"):
            table: Any = getattr(self, attribute, None)
            if table is not None:
                table.close_all()

    def _enter_call(self, name: str, token: Token | None) -> None:
        """Registra uma ativação Lox (ADR-0077) e o frame para o stack trace.

        A posição do frame é o call site (onde o chamado foi chamado); para R1015 a
        posição do erro é a declaração do chamado (o topo do estouro).
        """
        declaration = token or Token(TokenType.EOF, "", None, 0)
        if self._call_depth >= MAX_CALL_DEPTH:
            raise LoxRuntimeError(
                declaration,
                "Stack overflow.",
                code=Code.RUNTIME_STACK_OVERFLOW,
            )
        site = self._call_site or declaration
        self._frames.append(
            (
                name,
                site.file or self.reporter.file,
                site.line,
                site.column or 1,
            )
        )
        self._call_depth += 1

    def _leave_call(self) -> None:
        if self._call_depth > 0:
            self._call_depth -= 1
            if self._frames:
                self._frames.pop()

    def _capture_trace(self, error: LoxRuntimeError | LoxRaise) -> None:
        """Congela o trace no ponto mais interno; o `finally` desempilha os frames."""
        if error.trace is None:
            error.trace = self._build_trace()

    def _build_trace(self) -> Trace | None:
        if not self._frames:
            return None

        frames = [Frame(*item) for item in reversed(self._frames)]
        if len(frames) <= TRACE_HEAD + TRACE_TAIL:
            return Trace(tuple(frames))

        omitted = len(frames) - TRACE_HEAD - TRACE_TAIL
        kept = frames[:TRACE_HEAD] + frames[-TRACE_TAIL:]
        return Trace(tuple(kept), omitted=omitted, head=TRACE_HEAD)

    def current_site(self) -> str:
        """`arquivo:linha:coluna` do call site do frame atual (ADR-0120).

        Para `t.expect(1).toBe(2)` o frame atual é `toBe` e o call site é a linha do
        `expect` no teste; sem frame (topo), usa o call site da chamada em curso.
        """
        if self._frames:
            _name, file, line, column = self._frames[-1]
            return format_site(file, line, column)
        return ""

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

        if name.lexeme in self.environment.values and not self.environment.is_mutable(name.lexeme):
            raise LoxRuntimeError(
                name,
                immutable_redeclare_message(name.lexeme),
                code=Code.RUNTIME_IMMUTABLE,
            )

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

        if isinstance(a, LoxTuple) or isinstance(b, LoxTuple):
            if not isinstance(a, LoxTuple) or not isinstance(b, LoxTuple):
                return False
            return self._tuples_equal(a, b, set() if seen is None else seen)

        if isinstance(a, LoxEnumValue) or isinstance(b, LoxEnumValue):
            if not isinstance(a, LoxEnumValue) or not isinstance(b, LoxEnumValue):
                return False
            return self._enum_values_equal(a, b, set() if seen is None else seen)

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

    def _enum_values_equal(
        self,
        a: LoxEnumValue,
        b: LoxEnumValue,
        seen: set[tuple[int, int]],
    ) -> bool:
        if a is b:
            return True
        if a.enum != b.enum or a.key != b.key or a.variant != b.variant:
            return False
        if len(a.payload) != len(b.payload):
            return False

        pair = (id(a), id(b))
        if pair in seen:
            return True
        seen.add(pair)
        return all(
            self._is_equal(left, right, seen)
            for left, right in zip(a.payload, b.payload, strict=True)
        )

    def _tuples_equal(
        self,
        a: LoxTuple,
        b: LoxTuple,
        seen: set[tuple[int, int]],
    ) -> bool:
        if a is b:
            return True

        pair = (id(a), id(b))
        if pair in seen:
            return True

        seen.add(pair)
        if len(a.items) != len(b.items):
            return False

        for left, right in zip(a.items, b.items, strict=True):
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
            raise LoxRuntimeError(operator, "Operand must be a number.", code=Code.RUNTIME_OPERANDS)

    def _relational(self, operator: Token, left: object, right: object) -> bool:
        """Ordem numérica ou lexicográfica (code points), nunca misturada."""
        if isinstance(left, str) and isinstance(right, str):
            comparison = (left > right) - (left < right)
        else:
            self._check_number_operands(operator, left, right)
            numeric_comparison = numeric.compare(left, right)
            if numeric_comparison is None:  # NaN: toda comparação é falsa
                return False
            comparison = numeric_comparison

        match operator.type:
            case TokenType.GREATER:
                return comparison > 0
            case TokenType.GREATER_EQUAL:
                return comparison >= 0
            case TokenType.LESS:
                return comparison < 0
            case _:  # TokenType.LESS_EQUAL
                return comparison <= 0

    def _check_number_operands(self, operator: Token, *operands: object) -> None:
        for operand in operands:
            if not numeric.is_number(operand):
                raise LoxRuntimeError(
                    operator, "Operands must be numbers.", code=Code.RUNTIME_OPERANDS
                )

    def _check_int_operand(self, operator: Token, operand: object) -> None:
        if not numeric.is_int(operand):
            raise LoxRuntimeError(
                operator, "Operand must be an integer.", code=Code.RUNTIME_OPERANDS
            )

    def _check_int_operands(self, operator: Token, *operands: object) -> None:
        for operand in operands:
            if not numeric.is_int(operand):
                raise LoxRuntimeError(
                    operator, "Operands must be integers.", code=Code.RUNTIME_OPERANDS
                )

    def _numeric_op(
        self,
        operation: Callable[..., object],
        token: Token,
        *arguments: object,
    ) -> object:
        if not self.checked_overflow:
            return operation(*arguments)

        try:
            return operation(*arguments, checked=True)
        except numeric.NumericOverflow:
            raise LoxRuntimeError(token, "Integer overflow.", code=Code.INVALID_VALUE) from None
        except numeric.NumericConversionError:
            raise LoxRuntimeError(
                token, "Numeric conversion failed.", code=Code.RUNTIME_CAST
            ) from None

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
                raise LoxRuntimeError(
                    expr.brace,
                    "Duplicate key in map literal.",
                    code=Code.INVALID_VALUE,
                )

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

        if isinstance(ob, LoxTuple):
            index = self._evaluate(expr.index)
            if not numeric.is_int(index):
                raise LoxRuntimeError(
                    expr.bracket,
                    "Tuple index must be an integer.",
                    code=Code.RUNTIME_OPERANDS,
                )
            if not 0 <= index < len(ob.items):
                raise LoxRuntimeError(
                    expr.bracket,
                    f"Tuple index {index} out of bounds for length {len(ob.items)}.",
                    code=Code.INDEX_OUT_OF_BOUNDS,
                )
            return ob.items[index]

        raise LoxRuntimeError(
            expr.bracket,
            "Only lists and maps can be indexed.",
            code=Code.RUNTIME_OPERANDS,
        )

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

        raise LoxRuntimeError(
            expr.bracket,
            "Only lists and maps can be indexed.",
            code=Code.RUNTIME_OPERANDS,
        )

    def visit_grouping_expr(self, expr: Grouping) -> object:
        return self._evaluate(expr.expression)

    def _expand_type_aliases(self, ty: Ty, seen: frozenset[str] = frozenset()) -> Ty:
        if isinstance(ty, ClassTy):
            if ty.name in self._type_aliases and ty.name not in seen:
                return self._expand_type_aliases(self._type_aliases[ty.name], seen | {ty.name})
            return ClassTy(
                ty.name,
                tuple(self._expand_type_aliases(arg, seen) for arg in ty.args),
            )
        if isinstance(ty, EnumTy):
            return EnumTy(
                ty.name,
                tuple(self._expand_type_aliases(arg, seen) for arg in ty.args),
            )
        if isinstance(ty, ListTy):
            return ListTy(self._expand_type_aliases(ty.element, seen))
        if isinstance(ty, MapTy):
            return MapTy(
                self._expand_type_aliases(ty.key, seen),
                self._expand_type_aliases(ty.value, seen),
            )
        if isinstance(ty, TupleTy):
            return TupleTy(tuple(self._expand_type_aliases(item, seen) for item in ty.items))
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self._expand_type_aliases(item, seen) for item in ty.params),
                self._expand_type_aliases(ty.ret, seen),
                ty.min_params,
                ty.variadic,
            )
        if isinstance(ty, UnionTy):
            return UnionTy(tuple(self._expand_type_aliases(item, seen) for item in ty.members))

        return ty

    def visit_type_alias_stmt(self, stmt: TypeAlias) -> None:
        self._type_aliases[stmt.name.lexeme] = stmt.target

    def visit_is_expr(self, expr: Is) -> object:
        test_type = self._expand_type_aliases(expr.test_type)
        if isinstance(test_type, ClassTy) and test_type.args:
            raise LoxRuntimeError(
                expr.operator,
                "is doesn't support type arguments on classes yet.",
                code=Code.INVALID_VALUE,
            )
        if isinstance(test_type, EnumTy) and test_type.args:
            raise LoxRuntimeError(
                expr.operator,
                "is doesn't support type arguments on enums yet.",
                code=Code.INVALID_VALUE,
            )

        value = self._evaluate(expr.left)
        return matches_type(value, test_type, self._class_for_type)

    def visit_as_expr(self, expr: As) -> object:
        value = self._evaluate(expr.left)
        target = self._expand_type_aliases(expr.target_type)

        if isinstance(target, ClassTy) and target.args:
            raise LoxRuntimeError(
                expr.operator,
                "as doesn't support type arguments on classes yet.",
                code=Code.RUNTIME_CAST,
            )
        if isinstance(target, EnumTy) and target.args:
            raise LoxRuntimeError(
                expr.operator,
                "as doesn't support type arguments on enums yet.",
                code=Code.RUNTIME_CAST,
            )
        if isinstance(target, TyVar) or (
            isinstance(target, ClassTy) and self._class_for_type(target.name) is None
        ):
            # Tipos apagados: o cast dinâmico para um parâmetro de tipo é
            # identidade no tree-walk; o backend o resolve na monomorfização.
            # Um nome de classe sem binding também é um parâmetro apagado
            # (o checker já validou o alvo).
            return value

        if target is INT:
            if numeric.is_int(value):
                return value
            if numeric.is_float(value):
                try:
                    return numeric.float_to_int(value)
                except numeric.NumericConversionError:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Can't cast this Float to Int.",
                        code=Code.RUNTIME_CAST,
                    ) from None
        elif target is FLOAT:
            if numeric.is_float(value):
                return value
            if numeric.is_int(value):
                return numeric.int_to_float(value)
        elif target is ANY:
            return value
        elif isinstance(target, UnionTy):
            raise LoxRuntimeError(
                expr.operator,
                "as doesn't support union types yet; narrow first.",
                code=Code.RUNTIME_CAST,
            )
        elif matches_type(value, target, self._class_for_type):
            return value

        raise LoxRuntimeError(
            expr.operator,
            f"Can't cast value to {display(target)}.",
            code=Code.RUNTIME_CAST,
        )

    def visit_range_expr(self, expr: Range) -> object:
        start = self._evaluate(expr.start)
        end = self._evaluate(expr.end)

        if not numeric.is_int(start):
            raise LoxRuntimeError(
                expr.operator, "Range bounds must be integers.", code=Code.RUNTIME_OPERANDS
            )
        if not numeric.is_int(end):
            raise LoxRuntimeError(
                expr.operator, "Range bounds must be integers.", code=Code.RUNTIME_OPERANDS
            )

        return LoxRange(start, end, inclusive=expr.inclusive)

    def visit_unary_expr(self, expr: Unary) -> object:
        right = self._evaluate(expr.right)

        match expr.operator.type:
            case TokenType.NOT:
                return not self._is_truthy(right)
            case TokenType.MINUS:
                self._check_number_operand(expr.operator, right)
                return self._numeric_op(numeric.negate, expr.operator, right)
            case TokenType.TILDE:
                self._check_int_operand(expr.operator, right)
                return numeric.bit_not(right)

        return None

    def visit_binary_expr(self, expr: Binary) -> object:
        left = self._evaluate(expr.left)
        right = self._evaluate(expr.right)

        if expr.operator.type in _RELATIONAL:
            return self._relational(expr.operator, left, right)

        match expr.operator.type:
            case TokenType.MINUS:
                self._check_number_operands(expr.operator, left, right)
                return self._numeric_op(numeric.subtract, expr.operator, left, right)
            case TokenType.PLUS:
                if numeric.is_number(left) and numeric.is_number(right):
                    return self._numeric_op(numeric.add, expr.operator, left, right)
                if isinstance(left, str) and isinstance(right, str):
                    return str(left) + str(right)
                raise LoxRuntimeError(
                    expr.operator,
                    "Operands must be two numbers or two strings.",
                    code=Code.RUNTIME_OPERANDS,
                )
            case TokenType.SLASH:
                self._check_number_operands(expr.operator, left, right)
                if right == 0:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Division by zero not allowed",
                        code=Code.DIVISION_BY_ZERO,
                    )
                return numeric.divide(left, right)
            case TokenType.SLASH_SLASH:
                self._check_int_operands(expr.operator, left, right)
                if right == 0:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Division by zero not allowed",
                        code=Code.DIVISION_BY_ZERO,
                    )
                return self._numeric_op(numeric.int_divide, expr.operator, left, right)
            case TokenType.PERCENT:
                self._check_number_operands(expr.operator, left, right)
                if right == 0:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Modulo by zero not allowed",
                        code=Code.DIVISION_BY_ZERO,
                    )
                return self._numeric_op(numeric.modulo, expr.operator, left, right)
            case TokenType.STAR:
                self._check_number_operands(expr.operator, left, right)
                return self._numeric_op(numeric.multiply, expr.operator, left, right)
            case TokenType.STAR_STAR:
                self._check_number_operands(expr.operator, left, right)
                if numeric.is_int(left) and numeric.is_int(right) and right < 0:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Negative exponent not allowed for integer power.",
                        code=Code.RUNTIME_OPERANDS,
                    )
                try:
                    return self._numeric_op(numeric.power, expr.operator, left, right)
                except ValueError:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Invalid exponentiation.",
                        code=Code.RUNTIME_OPERANDS,
                    ) from None
                except OverflowError:
                    raise LoxRuntimeError(
                        expr.operator,
                        "Exponentiation overflow.",
                        code=Code.INVALID_VALUE,
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
                return self._shift(expr.operator, left, right, numeric.shift_right_logical)
            case TokenType.NOT_EQUAL:
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
            raise LoxRuntimeError(
                operator,
                "Shift count must be between 0 and 63.",
                code=Code.RUNTIME_OPERANDS,
            )

        return operation(left, right)

    def visit_call_expr(self, expr: Call) -> object:
        callee = self._evaluate(expr.callee)

        if expr.optional and callee is None:
            return None

        arguments: list[object] = []
        fixed_arguments = expr.arguments[:-1] if expr.spread else expr.arguments
        for argument in fixed_arguments:
            arguments.append(self._evaluate(argument))
        if expr.spread:
            spread = self._evaluate(expr.arguments[-1])
            if not isinstance(spread, LoxList):
                raise LoxRuntimeError(
                    expr.paren,
                    "Spread argument must be a list.",
                    code=Code.RUNTIME_OPERANDS,
                )
            arguments.extend(spread.elements)

        if not isinstance(callee, LoxCallable):
            raise LoxRuntimeError(
                expr.paren,
                "Can only call functions and classes.",
                code=Code.RUNTIME_NOT_CALLABLE,
            )

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

            raise LoxRuntimeError(expr.paren, message, code=Code.RUNTIME_ARITY)

        previous_site = self._call_site
        self._call_site = expr.paren
        try:
            try:
                return callee.call(self, arguments)
            except NativeError as error:
                raise LoxRuntimeError(expr.paren, str(error)) from error
            except numeric.NumericOverflow:
                raise LoxRuntimeError(expr.paren, "Integer overflow.") from None
            except numeric.NumericConversionError:
                raise LoxRuntimeError(expr.paren, "Numeric conversion failed.") from None
        finally:
            self._call_site = previous_site

    def visit_try_stmt(self, stmt: Try) -> None:
        try:
            try:
                self.execute_block(stmt.body, Environment(self.environment))
            except LoxRaise as raised:
                if not self._run_handlers(stmt, raised.value):
                    raise
            except LoxRuntimeError as runtime:
                value = LoxExceptionValue(
                    "RuntimeError",
                    runtime.message,
                    format_site(
                        runtime.token.file or self.reporter.file,
                        runtime.token.line,
                        runtime.token.column,
                    ),
                )
                if not self._run_handlers(stmt, value):
                    raise
        finally:
            if stmt.finally_body is not None:
                self.execute_block(stmt.finally_body, Environment(self.environment))

    def _run_handlers(self, stmt: Try, value: object) -> bool:
        for clause in stmt.handlers:
            exception_class = self.environment.get(clause.type_name)
            if not isinstance(exception_class, LoxClass):
                raise LoxRuntimeError(
                    clause.type_name,
                    "Exception type must be a class.",
                    code=Code.INVALID_VALUE,
                )
            if not self._matches_exception(value, exception_class):
                continue

            environment = Environment(self.environment)
            environment.define(clause.binding.lexeme, value, mutable=False)
            previous = self._current_exception
            self._current_exception = value
            try:
                self.execute_block(clause.body, environment)
            finally:
                self._current_exception = previous
            return True

        return False

    def _matches_exception(self, value: object, klass: LoxClass) -> bool:
        if isinstance(value, LoxInstance):
            return value.is_instance_of_class(klass)
        if isinstance(value, LoxExceptionValue):
            return value.is_instance_of(klass.name)
        return False

    def _class_for_type(self, name: str) -> LoxClass | None:
        """Resolve o nome de um tipo-classe no ambiente léxico (ADR-0044)."""
        environment: Environment | None = self.environment
        while environment is not None:
            if name in environment.values:
                value = environment.values[name]
                return value if isinstance(value, LoxClass) else None
            environment = environment.enclosing

        return None

    def visit_raise_stmt(self, stmt: Raise) -> None:
        value = self._current_exception if stmt.value is None else self._evaluate(stmt.value)
        if value is None:
            raise LoxRuntimeError(
                stmt.keyword,
                "No exception to re-raise.",
                code=Code.INVALID_VALUE,
            )
        site = self.current_site() or format_site(
            stmt.keyword.file or self.reporter.file,
            stmt.keyword.line,
            stmt.keyword.column,
        )
        if isinstance(value, LoxExceptionValue):
            raise LoxRaise(
                stmt.keyword,
                LoxExceptionValue(value.type_name, value.message, site or value.site),
            )
        if isinstance(value, LoxInstance) and value.is_instance_of("Exception"):
            value.set_exception_site(site)
            raise LoxRaise(stmt.keyword, value)

        raise LoxRuntimeError(
            stmt.keyword,
            "Can only raise exceptions.",
            code=Code.INVALID_VALUE,
        )

    def visit_import_stmt(self, stmt: Import) -> None:
        raise LoxRuntimeError(stmt.path[0], "Imports must be resolved before execution.")

    def visit_enum_stmt(self, stmt: EnumDecl) -> None:
        self._reject_immutable_redeclaration(stmt.name)
        variants = {variant.name.lexeme: len(variant.payload) for variant in stmt.variants}
        self.environment.define(
            stmt.name.lexeme,
            LoxEnumObject(
                stmt.display_name or stmt.name.lexeme,
                variants,
                key=stmt.name.lexeme,
            ),
            mutable=False,
        )

    def visit_match_expr(self, expr: Match) -> object:
        value = self._evaluate(expr.scrutinee)
        if not isinstance(value, LoxEnumValue):
            raise LoxRuntimeError(
                expr.keyword,
                "match requires an enum value.",
                code=Code.INVALID_VALUE,
            )

        for arm in expr.arms:
            pattern = arm.pattern
            if isinstance(pattern, WildcardPattern):
                return self._evaluate(arm.body)
            assert isinstance(pattern, VariantPattern)
            if value.key != pattern.enum.lexeme or value.variant != pattern.variant.lexeme:
                continue

            previous = self.environment
            self.environment = Environment(previous)
            try:
                for name, item in zip(pattern.bindings, value.payload, strict=False):
                    self.environment.define(name.lexeme, item, mutable=False)
                return self._evaluate(arm.body)
            finally:
                self.environment = previous

        raise LoxRuntimeError(expr.keyword, "No match arm matched.", code=Code.INVALID_VALUE)

    def visit_interface_stmt(self, stmt: Interface) -> None:
        defaults: dict[str, LoxFunction] = {}
        for method in stmt.methods:
            if method.abstract:
                continue
            defaults[method.name.lexeme] = LoxFunction(method, self.environment, False)

        self.interfaces[stmt.name.lexeme] = LoxInterface(
            stmt.display_name or stmt.name.lexeme, defaults
        )

    def visit_class_stmt(self, stmt: Class) -> None:
        self._reject_immutable_redeclaration(stmt.name)

        superclass: LoxClass | None = None
        if stmt.superclass is not None:
            candidate = self._evaluate(stmt.superclass)
            if not isinstance(candidate, LoxClass):
                raise LoxRuntimeError(
                    stmt.superclass.name,
                    "Superclass must be a class.",
                    code=Code.INVALID_VALUE,
                )

            superclass = candidate

        interfaces: list[LoxInterface] = []
        for token in stmt.implements:
            interface = self.interfaces.get(token.lexeme)
            if interface is None:
                raise LoxRuntimeError(
                    token,
                    f"Unknown interface '{token.lexeme}'.",
                    code=Code.INVALID_VALUE,
                )
            interfaces.append(interface)

        self.environment.define(stmt.name.lexeme, None)

        if stmt.superclass is not None:
            self.environment = Environment(self.environment)
            self.environment.define("super", superclass)

        methods: dict[str, LoxFunction] = {}
        for method in stmt.methods:
            function = LoxFunction(method, self.environment, method.name.lexeme == "init")
            methods[method.name.lexeme] = function

        fields: dict[str, FieldInfo] = {}
        if superclass is not None:
            fields.update(superclass.fields)

        for field in stmt.fields:
            if field.name.lexeme in fields:
                raise LoxRuntimeError(
                    field.name,
                    f"Field '{field.name.lexeme}' already declared.",
                    code=Code.INVALID_VALUE,
                )

            fields[field.name.lexeme] = FieldInfo(field.name, field.initializer, field.mutable)

        klass = LoxClass(
            stmt.display_name or stmt.name.lexeme,
            superclass,
            methods,
            fields,
            interfaces,
            declaration=stmt.name,
        )

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
            if expr.name.lexeme == "site" and ob.is_instance_of("Exception"):
                return ob.exception_site()
            return ob.get(expr.name)

        if isinstance(ob, LoxList):
            return ob.get_method(expr.name)

        if isinstance(ob, LoxMap):
            return ob.get_method(expr.name)

        if isinstance(ob, LoxExceptionValue):
            if expr.name.lexeme == "message":
                return ob.message
            if expr.name.lexeme == "site":
                return ob.site
            raise LoxRuntimeError(
                expr.name,
                f"Undefined property '{expr.name.lexeme}'.",
                code=Code.UNDEFINED_PROPERTY,
            )

        if isinstance(ob, LoxEnumObject):
            value = ob.get(expr.name.lexeme)
            if value is None:
                raise LoxRuntimeError(
                    expr.name,
                    f"Undefined variant '{expr.name.lexeme}'.",
                    code=Code.UNDEFINED_PROPERTY,
                )
            return value

        if isinstance(ob, NativeModule):
            value = ob.get(expr.name.lexeme)
            if value is None:
                raise LoxRuntimeError(
                    expr.name,
                    f"Undefined property '{expr.name.lexeme}'.",
                    code=Code.UNDEFINED_PROPERTY,
                )
            return value

        raise LoxRuntimeError(
            expr.name,
            "Only instances have properties.",
            code=Code.INVALID_VALUE,
        )

    def visit_conditional_expr(self, expr: Conditional) -> object:
        if self._is_truthy(self._evaluate(expr.condition)):
            return self._evaluate(expr.then_branch)

        return self._evaluate(expr.else_branch)

    def visit_set_expr(self, expr: Set) -> object:
        ob = self._evaluate(expr.object)

        if not isinstance(ob, LoxInstance):
            raise LoxRuntimeError(
                expr.name,
                "Only instances have fields.",
                code=Code.INVALID_VALUE,
            )

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
                expr.method,
                f"Undefined property '{expr.method.lexeme}'.",
                code=Code.UNDEFINED_PROPERTY,
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
            if iterable.inclusive:
                stop = iterable.end + 1 if iterable.step > 0 else iterable.end - 1
            else:
                stop = iterable.end
            return iter(range(iterable.start, stop, iterable.step))
        if isinstance(iterable, str):
            return iter(iterable)
        if isinstance(iterable, LoxList):
            return self._iterate_list(name, iterable)
        if isinstance(iterable, LoxMap):
            return self._iterate_map(name, iterable)
        if isinstance(iterable, LoxTuple):
            return iter(iterable.items)
        if isinstance(iterable, LoxInstance):
            return self._iterate_instance(name, iterable)

        raise LoxRuntimeError(
            name,
            "Can only iterate over a range, a list, a map or a string.",
            code=Code.RUNTIME_ITERATION,
        )

    def _iterate_instance(self, name: Token, instance: LoxInstance) -> Iterator[object]:
        iterator = self._iterator_method(instance, "iter", name)
        if not isinstance(iterator, LoxInstance):
            raise LoxRuntimeError(
                name,
                "iter() must return an instance with next() -> T?.",
                code=Code.RUNTIME_ITERATION,
            )

        while True:
            value = self._iterator_method(iterator, "next", name)
            if value is None:
                return
            yield value

    def _iterator_method(self, instance: LoxInstance, method_name: str, token: Token) -> object:
        method = instance.get(Token(TokenType.IDENTIFIER, method_name, None, token.line))
        if not isinstance(method, LoxCallable) or method.min_arity() != 0:
            raise LoxRuntimeError(
                token,
                f"{method_name}() must take no arguments.",
                code=Code.RUNTIME_ITERATION,
            )
        previous_site = self._call_site
        self._call_site = token
        try:
            return method.call(self, [])
        finally:
            self._call_site = previous_site

    def _iterate_list(self, name: Token, values: LoxList) -> Iterator[object]:
        version = values.version
        index = 0

        while index < len(values.elements):
            if values.version != version:
                raise LoxRuntimeError(
                    name,
                    "Can't modify a list while iterating over it.",
                    code=Code.RUNTIME_ITERATION,
                )

            yield values.elements[index]
            index += 1

        if values.version != version:
            raise LoxRuntimeError(
                name,
                "Can't modify a list while iterating over it.",
                code=Code.RUNTIME_ITERATION,
            )

    def _iterate_map(self, name: Token, values: LoxMap) -> Iterator[object]:
        version = values.version
        keys = values.keys()
        index = 0

        while index < len(keys):
            if values.version != version:
                raise LoxRuntimeError(
                    name,
                    "Can't modify a map while iterating over it.",
                    code=Code.RUNTIME_ITERATION,
                )

            yield keys[index]
            index += 1

        if values.version != version:
            raise LoxRuntimeError(
                name,
                "Can't modify a map while iterating over it.",
                code=Code.RUNTIME_ITERATION,
            )

    def visit_return_stmt(self, stmt: Return) -> None:
        value: object = None
        if stmt.value is not None:
            value = self._evaluate(stmt.value)

        raise ReturnSignal(stmt.keyword, value)

    def visit_destructure_stmt(self, stmt: Destructure) -> None:
        value = self._evaluate(stmt.initializer)
        self._bind_pattern(stmt.pattern, value, stmt.mutable)

    def _bind_pattern(self, pattern: DestructurePattern, value: object, mutable: bool) -> None:
        if isinstance(pattern, NamePattern):
            self._reject_immutable_redeclaration(pattern.name)
            self.environment.define(pattern.name.lexeme, value, mutable)
            return

        token = first_token(pattern)
        if not isinstance(value, LoxTuple):
            raise LoxRuntimeError(token, "Can only destructure a tuple.", code=Code.INVALID_VALUE)
        if len(value.items) != len(pattern.elements):
            raise LoxRuntimeError(
                token,
                f"Destructuring expects {len(pattern.elements)} values, found {len(value.items)}.",
                code=Code.RUNTIME_ARITY,
            )

        for element, item in zip(pattern.elements, value.items, strict=True):
            self._bind_pattern(element, item, mutable)

    def visit_tuple_expr(self, expr: TupleLiteral) -> object:
        return LoxTuple(tuple(self._evaluate(element) for element in expr.elements))

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
