"""Lowering da AST para IR do LLVM (L2).

Escopo (contrato em [ADR-0031](../../../docs/adr/0031-backend-nativo.md)):
`print`, `Int`, `Float`, `Bool`, `nil`, aritmética com promoção, `/`, `%`, comparações,
igualdade, unários, `if`/`while`/blocos, variáveis (`val`/`var`) e funções de topo com
chamada direta, `return`, recursão e aridade como panic site.

O que ainda não tem representação — `String`, `Any`, closures, funções como valor,
métodos, classes — falha com erro de compilação explícito (exit 65), nunca com lowering
silencioso. Funções usam o tipo **anotado** na assinatura; `return` e argumentos precisam
bater com ele (sem coerção implícita, como no resto do backend).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from src.backend import llvm_ir
from src.frontend.expr import (
    Assign,
    Binary,
    Call,
    Conditional,
    Expr,
    Grouping,
    Literal,
    Logical,
    Unary,
    Variable,
)
from src.frontend.stmt import (
    Block,
    Expression,
    Function,
    If,
    Param,
    Print,
    Return,
    Stmt,
    Var,
    While,
)
from src.frontend.token_type import TokenType
from src.frontend.ty import BOOL as TY_BOOL
from src.frontend.ty import FLOAT as TY_FLOAT
from src.frontend.ty import INT as TY_INT
from src.frontend.ty import NIL as TY_NIL
from src.frontend.ty import STRING as TY_STRING
from src.frontend.ty import Ty

_INT = llvm_ir.int_type(64)
_BOOL = llvm_ir.int_type(1)
_I32 = llvm_ir.int_type(32)
_FLOAT = llvm_ir.float_type()
_VOID = llvm_ir.void_type()
_I8_PTR = llvm_ir.pointer_type()

# Mensagens que o interpretador usa em runtime para operando de tipo errado.
# O checker também reporta esses casos; o backend rebaixa para panic site (ADR-0031).
_OPERAND_MESSAGES: dict[TokenType, str] = {
    TokenType.PLUS: "Operands must be two numbers or two strings.",
    TokenType.MINUS: "Operands must be numbers.",
    TokenType.STAR: "Operands must be numbers.",
    TokenType.PERCENT: "Operands must be numbers.",
    TokenType.SLASH: "Operands must be numbers.",
    TokenType.SLASH_SLASH: "Operands must be integers.",
    TokenType.LESS: "Operands must be numbers.",
    TokenType.LESS_EQUAL: "Operands must be numbers.",
    TokenType.GREATER: "Operands must be numbers.",
    TokenType.GREATER_EQUAL: "Operands must be numbers.",
}


class BackendError(Exception):
    """Erro de compilação do backend (exit 65). `line` é `None` quando o nó não tem."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


class ValueType(Enum):
    INT = auto()
    FLOAT = auto()
    BOOL = auto()
    STRING = auto()
    NIL = auto()


NUMERIC = (ValueType.INT, ValueType.FLOAT)


@dataclass(frozen=True)
class Binding:
    """Variável: slot de memória (`alloca` local ou global) e tipo do binding."""

    storage: Any
    ty: ValueType


@dataclass(frozen=True)
class FunctionInfo:
    """Assinatura já emitida: função LLVM, tipos dos parâmetros e do retorno."""

    ir: Any
    param_types: list[ValueType]
    return_type: ValueType
    params: list[Param]


@dataclass(frozen=True)
class Value:
    """Valor no IR. `NIL` não tem representação em LLVM: `llvm` fica `None`."""

    ty: ValueType
    llvm: Any = None


def _unsupported(what: str, line: int | None) -> BackendError:
    return BackendError(f"{what} is not supported by the backend yet.", line)


class Lowerer:
    def __init__(
        self,
        module: Any,
        *,
        types: dict[Expr, Ty],
        depths: dict[Expr, int],
    ) -> None:
        self.module: Any = module
        self.types = types
        self.depths = depths
        self.main: Any = None
        self.builder: Any = None
        self._runtime: dict[str, Any] = {}
        self._messages: dict[str, Any] = {}
        self._poison_count = 0
        self._string_count = 0
        self._scopes: list[dict[str, Binding]] = [{}]
        self._globals: dict[str, Binding] = {}
        self._functions: dict[str, FunctionInfo] = {}
        self._function_ir: Any = None
        self._return_type: ValueType = ValueType.NIL

    # --- programa ---

    def lower(self, statements: list[Stmt]) -> None:
        self._predeclare_functions(statements)

        main = llvm_ir.define_main(self.module)
        self.main = main
        self._function_ir = main
        self._return_type = ValueType.NIL
        self.builder = llvm_ir.builder(llvm_ir.block_of(main, "entry"))
        self.builder.call(self._function("lox_init", _VOID, []), [])

        for statement in statements:
            if isinstance(statement, Function):
                continue
            if self.builder.block.is_terminated:
                break
            self._stmt(statement)

        if not self.builder.block.is_terminated:
            self.builder.ret(llvm_ir.constant(_I32, 0))

        for statement in statements:
            if isinstance(statement, Function):
                self._lower_function(statement)

    def _predeclare_functions(self, statements: list[Stmt]) -> None:
        for statement in statements:
            if not isinstance(statement, Function):
                continue

            param_types = [self._param_type(param, statement.name) for param in statement.params]
            return_type = self._return_type_of(statement)
            result = (
                _VOID
                if return_type is ValueType.NIL
                else self._llvm_type(return_type)
            )
            signature = llvm_ir.declare(
                self.module,
                f"lox.{statement.name.lexeme}",
                result,
                [self._llvm_type(param) for param in param_types],
            )
            self._functions[statement.name.lexeme] = FunctionInfo(
                signature, param_types, return_type, statement.params
            )

    def _lower_function(self, stmt: Function) -> None:
        info = self._functions[stmt.name.lexeme]

        saved_builder = self.builder
        saved_scopes = self._scopes
        saved_function = self._function_ir
        saved_return = self._return_type

        self._function_ir = info.ir
        self._return_type = info.return_type
        self._scopes = [{}]
        self.builder = llvm_ir.builder(llvm_ir.block_of(info.ir, "entry"))

        self._scopes.append({})
        for index, (param, param_type) in enumerate(
            zip(stmt.params, info.param_types, strict=True)
        ):
            slot = self.builder.alloca(
                self._llvm_type(param_type), name=param.name.lexeme
            )
            self.builder.store(info.ir.args[index], slot)
            self._scopes[-1][param.name.lexeme] = Binding(slot, param_type)

        for inner in stmt.body:
            if self.builder.block.is_terminated:
                break
            self._stmt(inner)

        if not self.builder.block.is_terminated:
            if info.return_type is ValueType.NIL:
                self.builder.ret_void()
            else:
                # O checker garante `return` em todos os caminhos.
                self.builder.unreachable()

        self.builder = saved_builder
        self._scopes = saved_scopes
        self._function_ir = saved_function
        self._return_type = saved_return

    def _param_type(self, param: Param, token: object) -> ValueType:
        if param.type_annotation is None:
            raise BackendError(
                f"Parameter '{param.name.lexeme}' needs a type annotation "
                "for the backend.",
                param.name.line,
            )
        return self._value_type(param.type_annotation, param.name.line)

    def _return_type_of(self, stmt: Function) -> ValueType:
        if stmt.return_type is None:
            raise BackendError(
                f"Function '{stmt.name.lexeme}' needs a return type annotation "
                "for the backend.",
                stmt.name.line,
            )
        return self._value_type(stmt.return_type, stmt.name.line)

    def _value_type(self, ty: Ty, line: int | None) -> ValueType:
        if ty is TY_INT:
            return ValueType.INT
        if ty is TY_FLOAT:
            return ValueType.FLOAT
        if ty is TY_BOOL:
            return ValueType.BOOL
        if ty is TY_STRING:
            return ValueType.STRING
        if ty is TY_NIL:
            return ValueType.NIL

        raise _unsupported(f"Type '{ty}'", line)

    def _llvm_type(self, ty: ValueType) -> Any:
        match ty:
            case ValueType.INT:
                return _INT
            case ValueType.FLOAT:
                return _FLOAT
            case ValueType.BOOL:
                return _BOOL
            case ValueType.STRING:
                return _I8_PTR
            case ValueType.NIL:
                return _VOID

    def _zero(self, ty: ValueType) -> Value:
        match ty:
            case ValueType.INT:
                return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
            case ValueType.FLOAT:
                return Value(ValueType.FLOAT, llvm_ir.float_constant(0.0))
            case ValueType.BOOL:
                return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))
            case ValueType.STRING:
                return Value(ValueType.STRING, llvm_ir.null_pointer())
            case ValueType.NIL:
                return Value(ValueType.NIL)

    # --- statements ---

    def _stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, Block):
            self._scopes.append({})
            try:
                for inner in stmt.statements:
                    if self.builder.block.is_terminated:
                        break
                    self._stmt(inner)
            finally:
                self._scopes.pop()
        elif isinstance(stmt, Return):
            self._return(stmt)
        elif isinstance(stmt, Function):
            raise _unsupported("Local functions", stmt.name.line)
        elif isinstance(stmt, Var):
            self._var(stmt)
        elif isinstance(stmt, If):
            self._if(stmt)
        elif isinstance(stmt, While):
            self._while(stmt)
        elif isinstance(stmt, Print):
            self._print(stmt)
        elif isinstance(stmt, Expression):
            self._expr(stmt.expression)
        else:
            raise _unsupported(type(stmt).__name__, None)

    def _if(self, stmt: If) -> None:
        condition = self._truthy(self._expr(stmt.condition))
        then_block = llvm_ir.append_block(self._function_ir, "if.then")
        end_block = llvm_ir.append_block(self._function_ir, "if.end")

        if stmt.else_branch is None:
            else_block = end_block
        else:
            else_block = llvm_ir.append_block(self._function_ir, "if.else")

        self.builder.cbranch(condition, then_block, else_block)

        self.builder = llvm_ir.builder(then_block)
        self._stmt(stmt.then_branch)
        if not self.builder.block.is_terminated:
            self.builder.branch(end_block)

        if stmt.else_branch is not None:
            self.builder = llvm_ir.builder(else_block)
            self._stmt(stmt.else_branch)
            if not self.builder.block.is_terminated:
                self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

    def _while(self, stmt: While) -> None:
        header = llvm_ir.append_block(self._function_ir, "while.cond")
        body = llvm_ir.append_block(self._function_ir, "while.body")
        end = llvm_ir.append_block(self._function_ir, "while.end")

        self.builder.branch(header)
        self.builder = llvm_ir.builder(header)
        condition = self._truthy(self._expr(stmt.condition))
        self.builder.cbranch(condition, body, end)

        self.builder = llvm_ir.builder(body)
        self._stmt(stmt.body)
        if not self.builder.block.is_terminated:
            self.builder.branch(header)

        self.builder = llvm_ir.builder(end)

    def _print(self, stmt: Print) -> None:
        value = self._expr(stmt.expression)

        match value.ty:
            case ValueType.INT:
                self.builder.call(
                    self._function("lox_print_int", _VOID, [_INT]), [value.llvm]
                )
            case ValueType.FLOAT:
                self.builder.call(
                    self._function("lox_print_float", _VOID, [_FLOAT]), [value.llvm]
                )
            case ValueType.BOOL:
                widened = self.builder.zext(value.llvm, _I32)
                self.builder.call(
                    self._function("lox_print_bool", _VOID, [_I32]), [widened]
                )
            case ValueType.STRING:
                self.builder.call(
                    self._function("lox_print_str", _VOID, [_I8_PTR]), [value.llvm]
                )
            case ValueType.NIL:
                self.builder.call(self._function("lox_print_nil", _VOID, []), [])

    # --- expressões ---

    def _expr(self, expr: Expr) -> Value:
        if isinstance(expr, Variable):
            return self._variable(expr)
        if isinstance(expr, Assign):
            return self._assign(expr)
        if isinstance(expr, Literal):
            return self._literal(expr)
        if isinstance(expr, Grouping):
            return self._expr(expr.expression)
        if isinstance(expr, Unary):
            return self._unary(expr)
        if isinstance(expr, Binary):
            return self._binary(expr)
        if isinstance(expr, Call):
            return self._call(expr)
        if isinstance(expr, Conditional):
            return self._conditional(expr)
        if isinstance(expr, Logical):
            return self._logical(expr)

        raise _unsupported(type(expr).__name__, None)

    def _var(self, stmt: Var) -> None:
        if stmt.initializer is None:
            raise BackendError(
                "Uninitialized variables are not supported by the backend yet.",
                stmt.name.line,
            )

        value = self._expr(stmt.initializer)
        # O tipo é o do valor em runtime, não o da anotação: tipos são apagados e
        # `val f: Float = 2` guarda um `Int` (o interpretador imprime `3`, não `3.0`).
        declared = value.ty
        if declared is ValueType.NIL:
            raise BackendError(
                "Variables of type Nil are not supported by the backend yet.",
                stmt.name.line,
            )

        if len(self._scopes) == 1:
            name = f"g.{stmt.name.lexeme}"
            global_ = llvm_ir.global_variable(self.module, name, self._llvm_type(declared))
            self._globals[stmt.name.lexeme] = Binding(global_, declared)
            self.builder.store(value.llvm, global_)
            return

        slot = self.builder.alloca(
            self._llvm_type(declared), name=stmt.name.lexeme
        )
        self.builder.store(value.llvm, slot)
        self._scopes[-1][stmt.name.lexeme] = Binding(slot, declared)

    def _variable(self, expr: Variable) -> Value:
        if expr.name.lexeme in self._functions:
            raise _unsupported("Function values", expr.name.line)

        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(expr.name.line, f"Undefined variable '{expr.name.lexeme}'.")
            return self._zero(ValueType.INT)

        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        return Value(binding.ty, self.builder.load(binding.storage))

    def _assign(self, expr: Assign) -> Value:
        value = self._expr(expr.value)
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(expr.name.line, f"Undefined variable '{expr.name.lexeme}'.")
            return value
        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        if value.ty is not binding.ty:
            raise BackendError(
                f"Can't assign {value.ty.name} to a {binding.ty.name} variable "
                "for the backend yet.",
                expr.name.line,
            )
        self.builder.store(value.llvm, binding.storage)
        return value

    def _lookup(self, expr: Expr, name: str, line: int) -> Binding:
        depth = self.depths.get(expr)
        if depth is None:
            binding = self._globals.get(name)
            if binding is None:
                raise BackendError(f"Undefined variable '{name}'.", line)
            return binding

        return self._scopes[-1 - depth][name]

    def _literal(self, expr: Literal) -> Value:
        value = expr.value

        if value is None:
            return Value(ValueType.NIL)
        if isinstance(value, bool):
            return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, int(value)))
        if isinstance(value, int):
            return Value(ValueType.INT, llvm_ir.constant(_INT, value))
        if isinstance(value, float):
            return Value(ValueType.FLOAT, llvm_ir.float_constant(value))
        if isinstance(value, str):
            global_ = llvm_ir.string_literal(self.module, value, self._string_count)
            self._string_count += 1
            return Value(ValueType.STRING, self.builder.bitcast(global_, _I8_PTR))

        raise _unsupported("Literal", None)

    def _unary(self, expr: Unary) -> Value:
        operand = self._expr(expr.right)
        line = expr.operator.line

        match expr.operator.type:
            case TokenType.MINUS:
                if operand.ty is ValueType.INT:
                    zero = llvm_ir.constant(_INT, 0)
                    return Value(ValueType.INT, self.builder.sub(zero, operand.llvm))
                if operand.ty is ValueType.FLOAT:
                    return Value(ValueType.FLOAT, self.builder.fneg(operand.llvm))
                self._poison(line, "Operand must be a number.")
                return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
            case TokenType.BANG:
                truth = self._truthy(operand)
                return Value(ValueType.BOOL, self.builder.not_(truth))

        raise _unsupported(f"Unary operator '{expr.operator.lexeme}'", line)

    def _binary(self, expr: Binary) -> Value:
        left = self._expr(expr.left)
        right = self._expr(expr.right)
        operator = expr.operator
        line = operator.line

        match operator.type:
            case TokenType.PLUS:
                return self._arithmetic(left, right, "add", "fadd", operator.type, line)
            case TokenType.MINUS:
                return self._arithmetic(left, right, "sub", "fsub", operator.type, line)
            case TokenType.STAR:
                return self._arithmetic(left, right, "mul", "fmul", operator.type, line)
            case TokenType.SLASH:
                return self._float_division(left, right, line)
            case TokenType.SLASH_SLASH:
                return self._integer_division(left, right, line)
            case TokenType.PERCENT:
                return self._modulo(left, right, line)
            case (
                TokenType.LESS
                | TokenType.LESS_EQUAL
                | TokenType.GREATER
                | TokenType.GREATER_EQUAL
            ):
                return self._comparison(left, right, operator.type, line)
            case TokenType.EQUAL_EQUAL | TokenType.BANG_EQUAL:
                return self._equality(left, right, operator.type)
            case TokenType.STAR_STAR:
                raise _unsupported("'**'", line)

        raise _unsupported(f"Binary operator '{operator.lexeme}'", line)

    def _arithmetic(
        self,
        left: Value,
        right: Value,
        integer_op: str,
        float_op: str,
        operator: TokenType,
        line: int,
    ) -> Value:
        if operator is TokenType.PLUS and (
            left.ty is ValueType.STRING and right.ty is ValueType.STRING
        ):
            return self._concat(left, right)

        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            operation = getattr(self.builder, integer_op)
            return Value(ValueType.INT, operation(left.llvm, right.llvm))

        if left.ty in NUMERIC and right.ty in NUMERIC:
            operation = getattr(self.builder, float_op)
            return Value(
                ValueType.FLOAT,
                operation(self._to_float(left), self._to_float(right)),
            )

        self._poison(line, _OPERAND_MESSAGES[operator])
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _float_division(self, left: Value, right: Value, line: int) -> Value:
        if left.ty not in NUMERIC or right.ty not in NUMERIC:
            self._poison(line, _OPERAND_MESSAGES[TokenType.SLASH])
            return Value(ValueType.FLOAT, llvm_ir.float_constant(0.0))

        function = self._function("lox_float_div", _FLOAT, [_FLOAT, _FLOAT, _I32])
        call = self.builder.call(
            function,
            [self._to_float(left), self._to_float(right), llvm_ir.constant(_I32, line)],
        )
        return Value(ValueType.FLOAT, call)

    def _integer_division(self, left: Value, right: Value, line: int) -> Value:
        if not (left.ty is ValueType.INT and right.ty is ValueType.INT):
            self._poison(line, _OPERAND_MESSAGES[TokenType.SLASH_SLASH])
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

        function = self._function("lox_int_div", _INT, [_INT, _INT, _I32])
        call = self.builder.call(
            function, [left.llvm, right.llvm, llvm_ir.constant(_I32, line)]
        )
        return Value(ValueType.INT, call)

    def _modulo(self, left: Value, right: Value, line: int) -> Value:
        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            function = self._function("lox_int_mod", _INT, [_INT, _INT, _I32])
            call = self.builder.call(
                function, [left.llvm, right.llvm, llvm_ir.constant(_I32, line)]
            )
            return Value(ValueType.INT, call)

        if left.ty in NUMERIC and right.ty in NUMERIC:
            function = self._function("lox_float_mod", _FLOAT, [_FLOAT, _FLOAT, _I32])
            call = self.builder.call(
                function,
                [
                    self._to_float(left),
                    self._to_float(right),
                    llvm_ir.constant(_I32, line),
                ],
            )
            return Value(ValueType.FLOAT, call)

        self._poison(line, _OPERAND_MESSAGES[TokenType.PERCENT])
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _comparison(
        self, left: Value, right: Value, operator: TokenType, line: int
    ) -> Value:
        predicates = {
            TokenType.LESS: "<",
            TokenType.LESS_EQUAL: "<=",
            TokenType.GREATER: ">",
            TokenType.GREATER_EQUAL: ">=",
        }

        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            result = self.builder.icmp_signed(
                predicates[operator], left.llvm, right.llvm
            )
            return Value(ValueType.BOOL, result)

        if left.ty in NUMERIC and right.ty in NUMERIC:
            # `fcmp ordered`: NaN torna a comparação falsa, como `numeric.compare`.
            result = self.builder.fcmp_ordered(
                predicates[operator], self._to_float(left), self._to_float(right)
            )
            return Value(ValueType.BOOL, result)

        self._poison(line, _OPERAND_MESSAGES[operator])
        return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))

    def _equality(self, left: Value, right: Value, operator: TokenType) -> Value:
        equal = operator is TokenType.EQUAL_EQUAL

        if left.ty is ValueType.NIL or right.ty is ValueType.NIL:
            both_nil = left.ty is right.ty
            return Value(
                ValueType.BOOL, llvm_ir.constant(_BOOL, int(both_nil == equal))
            )

        if left.ty is ValueType.STRING and right.ty is ValueType.STRING:
            function = self._function("lox_str_equal", _I32, [_I8_PTR, _I8_PTR])
            comparison = self.builder.call(function, [left.llvm, right.llvm])
            result = self.builder.icmp_signed(
                "!=" if equal else "==", comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            result = self.builder.icmp_signed(
                "==" if equal else "!=", left.llvm, right.llvm
            )
            return Value(ValueType.BOOL, result)

        if left.ty in NUMERIC and right.ty in NUMERIC:
            # `fcmp ordered` mantém `NaN != NaN` verdadeiro e `NaN == NaN` falso.
            result = self.builder.fcmp_ordered(
                "==" if equal else "!=", self._to_float(left), self._to_float(right)
            )
            return Value(ValueType.BOOL, result)

        if left.ty is right.ty:
            result = self.builder.icmp_signed(
                "==" if equal else "!=", left.llvm, right.llvm
            )
            return Value(ValueType.BOOL, result)

        # Tipos diferentes nunca são iguais (I2): constante, sem comparação.
        return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, int(not equal)))

    def _to_float(self, value: Value) -> Any:
        if value.ty is ValueType.FLOAT:
            return value.llvm
        return self.builder.sitofp(value.llvm, _FLOAT)

    def _return(self, stmt: Return) -> None:
        if stmt.value is None:
            if self._return_type is not ValueType.NIL:
                raise BackendError(
                    "Returning nil from a non-Nil function is not supported "
                    "by the backend yet.",
                    stmt.keyword.line,
                )
            self.builder.ret_void()
            return

        value = self._expr(stmt.value)
        if value.ty is not self._return_type:
            raise BackendError(
                f"Expected {self._return_type.name}, found {value.ty.name} "
                "in this return for the backend yet.",
                stmt.keyword.line,
            )

        self.builder.ret(value.llvm)

    def _call(self, expr: Call) -> Value:
        if not isinstance(expr.callee, Variable):
            raise _unsupported("Indirect calls", expr.paren.line)

        name = expr.callee.name.lexeme
        if name == "len":
            return self._len(expr)

        info = self._functions.get(name)
        if info is None:
            raise _unsupported(f"Call to '{name}'", expr.paren.line)

        arguments = [self._expr(argument) for argument in expr.arguments]
        minimum = sum(1 for param in info.params if param.default is None)
        maximum = len(info.params)
        count = len(arguments)

        if not minimum <= count <= maximum:
            self._poison(expr.paren.line, self._arity_message(minimum, maximum, count))
            return self._zero(info.return_type)

        for index in range(count, maximum):
            default = info.params[index].default
            assert default is not None
            arguments.append(self._expr(default))

        for index, (argument, param_type) in enumerate(
            zip(arguments, info.param_types, strict=True), start=1
        ):
            if argument.ty is not param_type:
                raise BackendError(
                    f"Argument {index} of '{name}' is {argument.ty.name}, "
                    f"expected {param_type.name}, for the backend yet.",
                    expr.paren.line,
                )

        call = self.builder.call(info.ir, [argument.llvm for argument in arguments])
        if info.return_type is ValueType.NIL:
            return Value(ValueType.NIL)
        return Value(info.return_type, call)

    def _conditional(self, expr: Conditional) -> Value:
        condition = self._truthy(self._expr(expr.condition))
        then_block = llvm_ir.append_block(self._function_ir, "cond.then")
        else_block = llvm_ir.append_block(self._function_ir, "cond.else")
        end_block = llvm_ir.append_block(self._function_ir, "cond.end")
        self.builder.cbranch(condition, then_block, else_block)

        self.builder = llvm_ir.builder(then_block)
        then_value = self._expr(expr.then_branch)
        then_open = not self.builder.block.is_terminated
        if then_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(else_block)
        else_value = self._expr(expr.else_branch)
        else_open = not self.builder.block.is_terminated
        if else_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if then_value.ty is not else_value.ty:
            raise BackendError(
                f"Ternary branches are {then_value.ty.name} and "
                f"{else_value.ty.name}; union types are not supported by the "
                "backend yet.",
                None,
            )

        if then_value.ty is ValueType.NIL:
            if not (then_open or else_open):
                self.builder.unreachable()
                return self._zero(ValueType.INT)
            return Value(ValueType.NIL)

        if then_open and else_open:
            merged = self.builder.phi(self._llvm_type(then_value.ty), "cond.value")
            merged.add_incoming(then_value.llvm, then_block)
            merged.add_incoming(else_value.llvm, else_block)
            return Value(then_value.ty, merged)

        if then_open:
            return then_value
        if else_open:
            return else_value

        self.builder.unreachable()
        return self._zero(then_value.ty)

    def _logical(self, expr: Logical) -> Value:
        operator = expr.operator.type

        if operator is TokenType.QUESTION_QUESTION:
            left = self._expr(expr.left)
            # No L2 um valor não-nil é sempre não-nil: o lado direito é código morto.
            if left.ty is not ValueType.NIL:
                return left
            return self._expr(expr.right)

        left = self._expr(expr.left)
        if left.ty is ValueType.NIL:
            # Só `nil` é falsy: `nil and x` é nil; `nil or x` é x.
            if operator is TokenType.AND:
                return Value(ValueType.NIL)
            return self._expr(expr.right)

        if isinstance(expr.left, Literal) and isinstance(expr.left.value, bool):
            # `false and x` e `true or x` não avaliam x; `true and x` e `false or x`
            # são exatamente x. Evita a união `Bool | T` no caminho comum.
            evaluate_right = (operator is TokenType.AND and expr.left.value) or (
                operator is TokenType.OR and not expr.left.value
            )
            if evaluate_right:
                return self._expr(expr.right)
            return left

        condition = self._truthy(left)
        short_block = self.builder.block
        right_block = llvm_ir.append_block(self._function_ir, "logical.right")
        end_block = llvm_ir.append_block(self._function_ir, "logical.end")

        if operator is TokenType.AND:
            self.builder.cbranch(condition, right_block, end_block)
        else:
            self.builder.cbranch(condition, end_block, right_block)

        self.builder = llvm_ir.builder(right_block)
        right = self._expr(expr.right)
        right_open = not self.builder.block.is_terminated
        if right_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if left.ty is not right.ty:
            raise BackendError(
                f"Operands of '{expr.operator.lexeme}' are {left.ty.name} and "
                f"{right.ty.name}; union types are not supported by the backend "
                "yet.",
                expr.operator.line,
            )

        if not right_open:
            return left

        merged = self.builder.phi(self._llvm_type(left.ty), "logical.value")
        merged.add_incoming(left.llvm, short_block)
        merged.add_incoming(right.llvm, right_block)
        return Value(left.ty, merged)

    def _arity_message(self, minimum: int, maximum: int, count: int) -> str:
        if minimum == maximum:
            return f"Expected {minimum} arguments but got {count}."
        if count < minimum:
            return f"Expected at least {minimum} arguments but got {count}."
        return f"Expected {minimum} to {maximum} arguments but got {count}."

    def _concat(self, left: Value, right: Value) -> Value:
        function = self._function("lox_str_concat", _I8_PTR, [_I8_PTR, _I8_PTR])
        return Value(ValueType.STRING, self.builder.call(function, [left.llvm, right.llvm]))

    def _len(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1:
            self._poison(
                expr.paren.line,
                f"Expected 1 arguments but got {len(arguments)}.",
            )
            return self._zero(ValueType.INT)

        argument = arguments[0]
        if argument.ty is not ValueType.STRING:
            raise _unsupported("len of non-String", expr.paren.line)

        function = self._function("lox_str_len", _INT, [_I8_PTR])
        return Value(ValueType.INT, self.builder.call(function, [argument.llvm]))

    def _truthy(self, value: Value) -> Any:
        match value.ty:
            case ValueType.BOOL:
                return value.llvm
            case ValueType.INT | ValueType.FLOAT | ValueType.STRING:
                # Só nil e false são falsy: `0`, `0.0` e `""` são truthy (ADR-0006).
                return llvm_ir.constant(_BOOL, 1)
            case ValueType.NIL:
                return llvm_ir.constant(_BOOL, 0)

    def _poison(self, line: int, message: str) -> None:
        """Rebaixa erro estático a `lox_panic` e continua num bloco inalcançável."""
        function = self._panic_function()
        text = self._cstring(message)
        pointer = llvm_ir.cstring_pointer(self.builder, text)
        self.builder.call(function, [llvm_ir.constant(_I32, line), pointer])
        self.builder.unreachable()

        block = llvm_ir.append_block(self._function_ir, f"poison{self._poison_count}")
        self._poison_count += 1
        self.builder = llvm_ir.builder(block)

    def _panic_function(self) -> Any:
        function = self._runtime.get("lox_panic")
        if function is None:
            function = llvm_ir.declare_noreturn(
                self.module, "lox_panic", [_I32, _I8_PTR]
            )
            self._runtime["lox_panic"] = function
        return function

    def _cstring(self, message: str) -> Any:
        global_ = self._messages.get(message)
        if global_ is None:
            global_ = llvm_ir.cstring(
                self.module, message, f"msg.{len(self._messages)}"
            )
            self._messages[message] = global_
        return global_

    def _function(self, name: str, result: Any, params: list[Any]) -> Any:
        function = self._runtime.get(name)
        if function is None:
            function = llvm_ir.declare(self.module, name, result, params)
            self._runtime[name] = function
        return function


def lower_program(
    statements: list[Stmt],
    *,
    types: dict[Expr, Ty],
    depths: dict[Expr, int],
) -> Any:
    module = llvm_ir.new_module()
    Lowerer(module, types=types, depths=depths).lower(statements)
    return module
