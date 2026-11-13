"""Coordenação do lowering da AST para IR do LLVM.

O lowering é dividido por responsabilidade: `lower_model` (tipos/valores/layouts),
`lower_functions` (ABI de closure), `lower_variables` (slots/células), `lower_optionals`
(`T?`/coerções), `lower_strings`, `lower_classes` (L5) e `lower_calls`. Este módulo fica
com o programa, statements, expressões, aritmética e controle de fluxo.

As ABI/representações são as documentadas no ADR-0048 e permanecem estáveis: funções
`(i8* env, params...)`, métodos `(i8* env, i8* this, params...)`, closure
`{fnptr, env, display}`, instância `{classe, bitmap, slots i64}`. O que não tem
representação falha com 65 explícito, nunca com lowering silencioso.
"""

from __future__ import annotations

from typing import Any

__all__ = ["BackendError", "Lowerer", "lower_program"]

from src.backend import llvm_ir
from src.backend.captures import CaptureAnalysis, analyze_captures
from src.backend.lower_calls import CallLowering
from src.backend.lower_classes import ClassLowering
from src.backend.lower_functions import FunctionLowering
from src.backend.lower_model import (
    _BOOL,
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    _OPERAND_MESSAGES,
    _VOID,
    NUMERIC,
    BackendError,
    Binding,
    ClassLayout,
    FunctionInfo,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.backend.lower_optionals import OptionalLowering
from src.backend.lower_strings import StringLowering
from src.backend.lower_variables import VariableLowering
from src.frontend.expr import (
    As,
    Assign,
    Binary,
    Call,
    Conditional,
    Expr,
    Get,
    Grouping,
    InterpolatedString,
    Is,
    Lambda,
    Literal,
    Logical,
    Set,
    Super,
    This,
    Unary,
    Variable,
)
from src.frontend.stmt import (
    Block,
    Class,
    Expression,
    Function,
    If,
    Print,
    Return,
    Stmt,
    Var,
    While,
)
from src.frontend.token_type import TokenType
from src.frontend.ty import (
    Ty,
)


class Lowerer(
    FunctionLowering,
    VariableLowering,
    StringLowering,
    ClassLowering,
    OptionalLowering,
    CallLowering,
):
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
        self._displays: dict[str, Any] = {}
        self._poison_count = 0
        self._string_count = 0
        self._function_counter = 0
        self._scopes: list[dict[str, Binding]] = [{}]
        self._captures: dict[str, Binding] = {}
        self._globals: dict[str, Binding] = {}
        self._top_level: dict[int, FunctionInfo] = {}
        self._class_names: set[str] = set()
        self._classes: dict[str, ClassLayout] = {}
        self._local_class_counter = 0
        self._function_ir: Any = None
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._in_init = False
        self._method_class: str | None = None
        self._analysis = CaptureAnalysis({}, frozenset())

    # --- programa ---

    def lower(self, statements: list[Stmt]) -> None:
        self._analysis = analyze_captures(statements)
        self._predeclare_classes(statements)
        self._predeclare_functions(statements)

        main = llvm_ir.define_main(self.module)
        self.main = main
        self._function_ir = main
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(main, "entry"))
        self.builder.call(self._function("lox_init", _VOID, []), [])

        for statement in statements:
            if self.builder.block.is_terminated:
                break
            self._stmt(statement)

        if not self.builder.block.is_terminated:
            self.builder.ret(llvm_ir.constant(_I32, 0))
        self._seal_blocks(main)

        for statement in statements:
            if not isinstance(statement, Function):
                continue
            info = self._top_level[id(statement)]
            self._emit_function(info, statement, ())














    # --- opcionais (L2.5) ---







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
            info = self._top_level.get(id(stmt))
            if info is not None:
                self._define_top_level_function(stmt, info)
            else:
                self._local_function(stmt)
        elif isinstance(stmt, Class):
            self._class_declaration(stmt)
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
        if value.optional:
            self._print_optional(value)
        else:
            self._print_value(value)

    def _print_value(self, value: Value) -> None:
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
            case ValueType.FUNCTION:
                self.builder.call(
                    self._function("lox_print_function", _VOID, [_I8_PTR]),
                    [value.llvm],
                )
            case ValueType.CLASS | ValueType.INSTANCE:
                text = (
                    value.class_name or "?"
                    if value.ty is ValueType.CLASS
                    else f"{value.class_name or '?'} instance"
                )
                self.builder.call(
                    self._function("lox_print_str", _VOID, [_I8_PTR]),
                    [self._string_literal(text).llvm],
                )
            case ValueType.NIL:
                self.builder.call(self._function("lox_print_nil", _VOID, []), [])

    def _print_optional(self, value: Value) -> None:
        tag = self._optional_tag(value)
        some = llvm_ir.append_block(self._function_ir, "opt.print.some")
        nothing = llvm_ir.append_block(self._function_ir, "opt.print.nil")
        end = llvm_ir.append_block(self._function_ir, "opt.print.end")
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(nothing)
        self.builder.call(self._function("lox_print_nil", _VOID, []), [])
        self.builder.branch(end)

        self.builder = llvm_ir.builder(some)
        self._print_value(self._optional_payload(value))
        self.builder.branch(end)

        self.builder = llvm_ir.builder(end)

    # --- expressões ---

    def _expr(self, expr: Expr) -> Value:
        if isinstance(expr, Variable):
            return self._variable(expr)
        if isinstance(expr, Assign):
            return self._assign(expr)
        if isinstance(expr, Get):
            return self._get(expr)
        if isinstance(expr, Set):
            return self._set(expr)
        if isinstance(expr, This):
            return self._this(expr)
        if isinstance(expr, Super):
            return self._super_method(expr)
        if isinstance(expr, Is):
            return self._is_expr(expr)
        if isinstance(expr, As):
            return self._as_expr(expr)
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
        if isinstance(expr, InterpolatedString):
            return self._interpolated(expr)
        if isinstance(expr, Lambda):
            return self._lambda(expr)

        raise _unsupported(type(expr).__name__, None)

    # --- funções e closures ---











    # --- células ---







    # --- classes e instâncias ---






























    # --- variáveis ---






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
            return self._string_literal(value)

        raise _unsupported("Literal", None)





    def _unary(self, expr: Unary) -> Value:
        operand = self._expr(expr.right)
        line = expr.operator.line

        match expr.operator.type:
            case TokenType.MINUS:
                operand = self._unwrap_operand(
                    operand, line, "Operand must be a number."
                )
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
        message = _OPERAND_MESSAGES[operator]
        left = self._unwrap_operand(left, line, message)
        right = self._unwrap_operand(right, line, message)

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
        left = self._unwrap_operand(
            left, line, _OPERAND_MESSAGES[TokenType.SLASH]
        )
        right = self._unwrap_operand(
            right, line, _OPERAND_MESSAGES[TokenType.SLASH]
        )
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
        left = self._unwrap_operand(
            left, line, _OPERAND_MESSAGES[TokenType.SLASH_SLASH]
        )
        right = self._unwrap_operand(
            right, line, _OPERAND_MESSAGES[TokenType.SLASH_SLASH]
        )
        if not (left.ty is ValueType.INT and right.ty is ValueType.INT):
            self._poison(line, _OPERAND_MESSAGES[TokenType.SLASH_SLASH])
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

        function = self._function("lox_int_div", _INT, [_INT, _INT, _I32])
        call = self.builder.call(
            function, [left.llvm, right.llvm, llvm_ir.constant(_I32, line)]
        )
        return Value(ValueType.INT, call)

    def _modulo(self, left: Value, right: Value, line: int) -> Value:
        left = self._unwrap_operand(
            left, line, _OPERAND_MESSAGES[TokenType.PERCENT]
        )
        right = self._unwrap_operand(
            right, line, _OPERAND_MESSAGES[TokenType.PERCENT]
        )
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
        left = self._unwrap_operand(left, line, _OPERAND_MESSAGES[operator])
        right = self._unwrap_operand(right, line, _OPERAND_MESSAGES[operator])

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

        if left.ty is ValueType.STRING and right.ty is ValueType.STRING:
            function = self._function("lox_str_compare", _I32, [_I8_PTR, _I8_PTR])
            comparison = self.builder.call(function, [left.llvm, right.llvm])
            result = self.builder.icmp_signed(
                predicates[operator], comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        self._poison(line, _OPERAND_MESSAGES[operator])
        return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))

    def _equality(self, left: Value, right: Value, operator: TokenType) -> Value:
        if left.optional or right.optional:
            return self._optional_equality(left, right, operator)
        return self._plain_equality(left, right, operator)


    def _plain_equality(
        self, left: Value, right: Value, operator: TokenType
    ) -> Value:
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
            if left.ty is ValueType.FUNCTION and left.sig != right.sig:
                return Value(
                    ValueType.BOOL, llvm_ir.constant(_BOOL, int(not equal))
                )
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
            if self._return_type_desc.ty is ValueType.NIL:
                self.builder.ret_void()
                return
            if self._return_type_desc.optional:
                self.builder.ret(self._zero_desc(self._return_type_desc).llvm)
                return
            raise BackendError(
                "Returning nil from a non-Nil function is not supported "
                "by the backend yet.",
                stmt.keyword.line,
            )

        value = self._coerce(
            self._expr(stmt.value), self._return_type_desc, stmt.keyword.line
        )
        if self._return_type_desc.ty is ValueType.NIL:
            self.builder.ret_void()
            return

        self.builder.ret(value.llvm)





    def _conditional(self, expr: Conditional) -> Value:
        condition = self._truthy(self._expr(expr.condition))
        then_block = llvm_ir.append_block(self._function_ir, "cond.then")
        else_block = llvm_ir.append_block(self._function_ir, "cond.else")
        end_block = llvm_ir.append_block(self._function_ir, "cond.end")
        self.builder.cbranch(condition, then_block, else_block)

        self.builder = llvm_ir.builder(then_block)
        then_value = self._expr(expr.then_branch)
        then_end = self.builder.block
        then_open = not then_end.is_terminated

        self.builder = llvm_ir.builder(else_block)
        else_value = self._expr(expr.else_branch)
        else_end = self.builder.block
        else_open = not else_end.is_terminated

        common = self._merge_branches(then_value, else_value, None)

        if then_open:
            self.builder = llvm_ir.builder(then_end)
            then_value = self._coerce(then_value, common, None)
            then_end = self.builder.block
            self.builder.branch(end_block)

        if else_open:
            self.builder = llvm_ir.builder(else_end)
            else_value = self._coerce(else_value, common, None)
            else_end = self.builder.block
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if common.ty is ValueType.NIL:
            if not (then_open or else_open):
                self.builder.unreachable()
                return self._zero(ValueType.INT)
            return Value(ValueType.NIL)

        if then_open and else_open:
            merged = self.builder.phi(
                self._storage_llvm_type(common), "cond.value"
            )
            merged.add_incoming(then_value.llvm, then_end)
            merged.add_incoming(else_value.llvm, else_end)
            return Value(common.ty, merged, common.fn, common.optional)

        if then_open:
            return then_value
        if else_open:
            return else_value

        self.builder.unreachable()
        return self._zero_desc(common)

    def _merge_branches(
        self, left: Value, right: Value, line: int | None
    ) -> TypeDesc:
        left_desc = left.desc
        right_desc = right.desc
        if left_desc.same_as(right_desc):
            return left_desc

        left_nil = left.ty is ValueType.NIL
        right_nil = right.ty is ValueType.NIL
        if left_nil and right_nil:
            return left_desc
        if left_nil:
            if right.optional:
                return right_desc
            return TypeDesc(right.ty, right.sig, True)
        if right_nil:
            if left.optional:
                return left_desc
            return TypeDesc(left.ty, left.sig, True)

        if (
            left.optional
            and not right.optional
            and TypeDesc(left.ty, left.sig).same_as(right_desc)
        ):
            return left_desc
        if (
            right.optional
            and not left.optional
            and TypeDesc(right.ty, right.sig).same_as(left_desc)
        ):
            return right_desc

        raise BackendError(
            f"Ternary branches are {left.ty.name} and {right.ty.name}; "
            "union types are not supported by the backend yet.",
            line,
        )

    def _logical(self, expr: Logical) -> Value:
        operator = expr.operator.type

        if operator is TokenType.QUESTION_QUESTION:
            left = self._expr(expr.left)
            if not left.optional:
                # No L4 um valor não-nil é sempre não-nil: o lado direito é morto.
                if left.ty is not ValueType.NIL:
                    return left
                return self._expr(expr.right)

            some = llvm_ir.append_block(self._function_ir, "coalesce.some")
            nothing = llvm_ir.append_block(self._function_ir, "coalesce.nil")
            end = llvm_ir.append_block(self._function_ir, "coalesce.end")
            tag = self._optional_tag(left)
            self.builder.cbranch(tag, some, nothing)

            self.builder = llvm_ir.builder(some)
            payload = self._optional_payload(left)
            self.builder.branch(end)
            some_end = self.builder.block

            self.builder = llvm_ir.builder(nothing)
            inner = TypeDesc(left.ty, left.sig, False, left.class_name)
            try:
                right = self._coerce(
                    self._expr(expr.right),
                    inner,
                    expr.operator.line,
                )
            except BackendError:
                raise _unsupported(
                    "Coalesce with different types",
                    expr.operator.line,
                ) from None
            self.builder.branch(end)
            nothing_end = self.builder.block

            self.builder = llvm_ir.builder(end)
            merged = self.builder.phi(
                self._storage_llvm_type(inner),
                "coalesce.value",
            )
            merged.add_incoming(payload.llvm, some_end)
            merged.add_incoming(right.llvm, nothing_end)
            return Value(
                left.ty,
                merged,
                left.sig,
                class_name=left.class_name,
            )

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

        common: TypeDesc | None
        if left.optional:
            common = left.desc
            right = self._coerce(right, common, expr.operator.line)
        elif left.desc.same_as(right.desc):
            common = left.desc
        else:
            common = None

        right_end = self.builder.block
        right_open = not right_end.is_terminated
        if right_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if common is None:
            raise BackendError(
                f"Operands of '{expr.operator.lexeme}' are {left.ty.name} and "
                f"{right.ty.name}; union types are not supported by the backend "
                "yet.",
                expr.operator.line,
            )

        if not right_open:
            return left

        merged = self.builder.phi(
            self._storage_llvm_type(common), "logical.value"
        )
        merged.add_incoming(left.llvm, short_block)
        merged.add_incoming(right.llvm, right_end)
        return Value(common.ty, merged, common.fn, common.optional)






    def _truthy(self, value: Value) -> Any:
        if value.optional:
            tag = self._optional_tag(value)
            if value.ty is ValueType.BOOL:
                payload = self._optional_payload(value).llvm
                return self.builder.and_(tag, payload)
            return tag

        match value.ty:
            case ValueType.BOOL:
                return value.llvm
            case (
                ValueType.INT
                | ValueType.FLOAT
                | ValueType.STRING
                | ValueType.FUNCTION
                | ValueType.CLASS
                | ValueType.INSTANCE
            ):
                # Só nil e false são falsy: `0`, `0.0`, `""` e funções são truthy.
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