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

from src.diagnostics.codes import Code

__all__ = ["BackendError", "Lowerer", "lower_program"]

from src.backend import llvm_ir
from src.backend.captures import CaptureAnalysis, analyze_captures
from src.backend.lower_calls import CallLowering
from src.backend.lower_class_codegen import ClassCodegenLowering
from src.backend.lower_class_layout import ClassLayoutLowering
from src.backend.lower_containers import ContainerLowering
from src.backend.lower_enums import EnumLowering
from src.backend.lower_exceptions import ExceptionLowering
from src.backend.lower_functions import FunctionLowering
from src.backend.lower_generics import GenericLowering
from src.backend.lower_instances import InstanceLowering
from src.backend.lower_math import MathLowering
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
from src.backend.lower_range import RangeLowering
from src.backend.lower_strings import StringLowering
from src.backend.lower_tuples import TupleLowering
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
)
from src.frontend.stmt import (
    Block,
    Class,
    Destructure,
    EnumDecl,
    Expression,
    ForIn,
    Function,
    If,
    Print,
    Raise,
    Return,
    Stmt,
    Try,
    Var,
    While,
)
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token
from src.frontend.ty import (
    Ty,
)


class Lowerer(
    ExceptionLowering,
    EnumLowering,
    GenericLowering,
    MathLowering,
    TupleLowering,
    ContainerLowering,
    RangeLowering,
    FunctionLowering,
    VariableLowering,
    StringLowering,
    ClassLayoutLowering,
    ClassCodegenLowering,
    InstanceLowering,
    OptionalLowering,
    CallLowering,
):
    def __init__(
        self,
        module: Any,
        *,
        types: dict[Expr, Ty],
        depths: dict[Expr, int],
        generic_instances: Any = None,
        generic_classes: Any = None,
        generic_class_sites: Any = None,
        source_path: str = "<lox>",
    ) -> None:
        self.module: Any = module
        self.source_path: str = source_path
        self.types = types
        self.depths = depths
        self.generic_instances = generic_instances or {}
        self.generic_classes = generic_classes or set()
        self.generic_class_sites = generic_class_sites or {}
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
        self._type_subst: dict[str, Ty] = {}
        self._enum_layouts: dict[str, Any] = {}
        self._enum_names: dict[str, Any] = {}
        self._finally_stack: list[list[Any]] = []
        self._list_expected_element: Ty | None = None
        self._map_expected_key: Ty | None = None
        self._map_expected_value: Ty | None = None
        self._generic_fns: dict[str, Function] = {}
        self._generic_fn_cache: dict[tuple[str, tuple[str, ...]], FunctionInfo] = {}
        self._generic_class_layouts: dict[str, ClassLayout] = {}
        self._generic_class_by_source: dict[str, list[ClassLayout]] = {}
        self._generic_class_nodes: dict[str, Class] = {}
        self._generic_descriptors: dict[str, Any] = {}

    # --- programa ---

    def lower(self, statements: list[Stmt]) -> None:
        self._analysis = analyze_captures(statements)
        self._prepare_generics(statements)
        self._prepare_enums(statements)
        self._prepare_exception_classes()
        self._predeclare_classes(statements)
        self._prepare_generic_classes(statements)
        self._predeclare_functions(statements)

        main = llvm_ir.define_main(self.module)
        self.main = main
        self._function_ir = main
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(main, "entry"))
        init_path = llvm_ir.cstring_pointer(
            self.builder, self._cstring(self.source_path)
        )
        self.builder.call(
            self._function(
                "lox_init", _VOID, [_I8_PTR, _I32, llvm_ir.pointer_pointer()]
            ),
            [init_path, main.args[0], main.args[1]],
        )
        self._emit_exception_classes()

        for statement in statements:
            if self.builder.block.is_terminated:
                break
            self._stmt(statement)

        if not self.builder.block.is_terminated:
            self.builder.ret(llvm_ir.constant(_I32, 0))
        self._seal_blocks(main)

        for statement in statements:
            if not isinstance(statement, Function) or statement.type_params:
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
            if stmt.type_params:
                return
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
        elif isinstance(stmt, ForIn):
            self._for_in(stmt)
        elif isinstance(stmt, Destructure):
            self._destructure(stmt)
        elif isinstance(stmt, EnumDecl):
            self._enum_decl(stmt)
        elif isinstance(stmt, Try):
            self._try(stmt)
        elif isinstance(stmt, Raise):
            self._raise(stmt)
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
            case ValueType.RANGE:
                self.builder.call(
                    self._function("lox_print_range", _VOID, [_I8_PTR]), [value.llvm]
                )
            case ValueType.LIST:
                self.builder.call(
                    self._function("lox_print_list", _VOID, [_I8_PTR]), [value.llvm]
                )
            case ValueType.MAP:
                self.builder.call(
                    self._function("lox_print_map", _VOID, [_I8_PTR]), [value.llvm]
                )
            case ValueType.TUPLE:
                self.builder.call(
                    self._function("lox_print_tuple", _VOID, [_I8_PTR]), [value.llvm]
                )
            case ValueType.ENUM:
                self.builder.call(
                    self._function("lox_print_enum", _VOID, [_I8_PTR]), [value.llvm]
                )
            case ValueType.FUNCTION:
                self.builder.call(
                    self._function("lox_print_function", _VOID, [_I8_PTR]),
                    [value.llvm],
                )
            case ValueType.CLASS | ValueType.INSTANCE:
                display = self._class_display(value.class_name or "?")
                text = (
                    display
                    if value.ty is ValueType.CLASS
                    else f"{display} instance"
                )
                self.builder.call(
                    self._function("lox_print_str", _VOID, [_I8_PTR]),
                    [self._string_literal(text).llvm],
                )
            case ValueType.ANY:
                tag = self.builder.extract_value(value.llvm, 0)
                payload = self.builder.extract_value(value.llvm, 1)
                self.builder.call(
                    self._function(
                        "lox_print_any", _VOID, [_INT, _INT]
                    ),
                    [tag, payload],
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
        if isinstance(expr, Range):
            return self._range_expr(expr)
        if isinstance(expr, ListLiteral):
            return self._list_literal(expr)
        if isinstance(expr, MapLiteral):
            return self._map_literal(expr)
        if isinstance(expr, TupleLiteral):
            return self._tuple_literal(expr)
        if isinstance(expr, Match):
            return self._match(expr)
        if isinstance(expr, Index):
            return self._list_get(expr)
        if isinstance(expr, IndexSet):
            return self._list_set(expr)

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
        column = expr.operator.column

        match expr.operator.type:
            case TokenType.MINUS:
                operand = self._unwrap_operand(
                    operand,
                    line,
                    "Operand must be a number.",
                    column=column,
                    code=Code.RUNTIME_OPERANDS,
                )
                if operand.ty is ValueType.INT:
                    zero = llvm_ir.constant(_INT, 0)
                    return Value(ValueType.INT, self.builder.sub(zero, operand.llvm))
                if operand.ty is ValueType.FLOAT:
                    return Value(ValueType.FLOAT, self.builder.fneg(operand.llvm))
                self._poison(
                    line,
                    "Operand must be a number.",
                    column=column,
                    code=Code.RUNTIME_OPERANDS,
                )
                return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
            case TokenType.NOT:
                truth = self._truthy(operand)
                return Value(ValueType.BOOL, self.builder.not_(truth))
            case TokenType.TILDE:
                operand = self._unwrap_operand(
                    operand,
                    line,
                    "Operand must be an integer.",
                    column=column,
                    code=Code.RUNTIME_OPERANDS,
                )
                if operand.ty is not ValueType.INT:
                    self._poison(
                        line,
                        "Operand must be an integer.",
                        column=column,
                        code=Code.RUNTIME_OPERANDS,
                    )
                    return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
                return Value(
                    ValueType.INT,
                    self.builder.xor(operand.llvm, llvm_ir.constant(_INT, -1)),
                )

        raise _unsupported(f"Unary operator '{expr.operator.lexeme}'", line)

    def _binary(self, expr: Binary) -> Value:
        left = self._expr(expr.left)
        right = self._expr(expr.right)
        operator = expr.operator
        line = operator.line

        match operator.type:
            case TokenType.PLUS:
                return self._arithmetic(
                    left, right, "add", "fadd", operator.type, operator
                )
            case TokenType.MINUS:
                return self._arithmetic(
                    left, right, "sub", "fsub", operator.type, operator
                )
            case TokenType.STAR:
                return self._arithmetic(
                    left, right, "mul", "fmul", operator.type, operator
                )
            case TokenType.SLASH:
                return self._float_division(left, right, operator)
            case TokenType.SLASH_SLASH:
                return self._integer_division(left, right, operator)
            case TokenType.PERCENT:
                return self._modulo(left, right, operator)
            case (
                TokenType.LESS
                | TokenType.LESS_EQUAL
                | TokenType.GREATER
                | TokenType.GREATER_EQUAL
            ):
                return self._comparison(left, right, operator.type, operator)
            case TokenType.EQUAL_EQUAL | TokenType.NOT_EQUAL:
                return self._equality(left, right, operator.type)
            case TokenType.STAR_STAR:
                return self._power(left, right, operator)
            case TokenType.AMPERSAND:
                return self._bitwise(left, right, "and", operator)
            case TokenType.PIPE:
                return self._bitwise(left, right, "or", operator)
            case TokenType.CARET:
                return self._bitwise(left, right, "xor", operator)
            case TokenType.LESS_LESS:
                return self._shift(left, right, 0, operator)
            case TokenType.GREATER_GREATER:
                return self._shift(left, right, 1, operator)
            case TokenType.GREATER_GREATER_GREATER:
                return self._shift(left, right, 2, operator)

        raise _unsupported(f"Binary operator '{operator.lexeme}'", line)

    def _power(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            "Operands must be numbers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            "Operands must be numbers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            call = self.builder.call(
                self._function("lox_int_pow", _INT, [_INT, _INT, _I32, _I32]),
                [
                    left.llvm,
                    right.llvm,
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(ValueType.INT, call)
        if left.ty in NUMERIC and right.ty in NUMERIC:
            call = self.builder.call(
                self._function("pow", _FLOAT, [_FLOAT, _FLOAT]),
                [self._to_float(left), self._to_float(right)],
            )
            return Value(ValueType.FLOAT, call)
        self._poison(
            line,
            "Operands must be numbers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _bitwise(self, left: Value, right: Value, op: str, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is not ValueType.INT or right.ty is not ValueType.INT:
            self._poison(
                line,
                "Operands must be integers.",
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
        operation = {
            "and": self.builder.and_,
            "or": self.builder.or_,
            "xor": self.builder.xor,
        }[op]
        return Value(ValueType.INT, operation(left.llvm, right.llvm))

    def _shift(self, left: Value, right: Value, kind: int, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is not ValueType.INT or right.ty is not ValueType.INT:
            self._poison(
                line,
                "Operands must be integers.",
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
        call = self.builder.call(
            self._function("lox_shift", _INT, [_INT, _INT, _I32, _I32, _I32]),
            [
                left.llvm,
                right.llvm,
                llvm_ir.constant(_I32, kind),
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        return Value(ValueType.INT, call)

    def _arithmetic(
        self,
        left: Value,
        right: Value,
        integer_op: str,
        float_op: str,
        operator: TokenType,
        token: Token,
    ) -> Value:
        line = token.line
        column = token.column
        message = _OPERAND_MESSAGES[operator]
        left = self._unwrap_operand(
            left, line, message, column=column, code=Code.RUNTIME_OPERANDS
        )
        right = self._unwrap_operand(
            right, line, message, column=column, code=Code.RUNTIME_OPERANDS
        )

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

        self._poison(
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _float_division(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty not in NUMERIC or right.ty not in NUMERIC:
            self._poison(
                line,
                _OPERAND_MESSAGES[TokenType.SLASH],
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.FLOAT, llvm_ir.float_constant(0.0))

        function = self._function(
            "lox_float_div", _FLOAT, [_FLOAT, _FLOAT, _I32, _I32]
        )
        call = self.builder.call(
            function,
            [
                self._to_float(left),
                self._to_float(right),
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        return Value(ValueType.FLOAT, call)

    def _integer_division(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH_SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH_SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if not (left.ty is ValueType.INT and right.ty is ValueType.INT):
            self._poison(
                line,
                _OPERAND_MESSAGES[TokenType.SLASH_SLASH],
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

        function = self._function("lox_int_div", _INT, [_INT, _INT, _I32, _I32])
        call = self.builder.call(
            function,
            [
                left.llvm,
                right.llvm,
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        return Value(ValueType.INT, call)

    def _modulo(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[TokenType.PERCENT],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[TokenType.PERCENT],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            function = self._function("lox_int_mod", _INT, [_INT, _INT, _I32, _I32])
            call = self.builder.call(
                function,
                [
                    left.llvm,
                    right.llvm,
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(ValueType.INT, call)

        if left.ty in NUMERIC and right.ty in NUMERIC:
            function = self._function(
                "lox_float_mod", _FLOAT, [_FLOAT, _FLOAT, _I32, _I32]
            )
            call = self.builder.call(
                function,
                [
                    self._to_float(left),
                    self._to_float(right),
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(ValueType.FLOAT, call)

        self._poison(
            line,
            _OPERAND_MESSAGES[TokenType.PERCENT],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _comparison(
        self, left: Value, right: Value, operator: TokenType, token: Token
    ) -> Value:
        line = token.line
        column = token.column
        predicates = {
            TokenType.LESS: "<",
            TokenType.LESS_EQUAL: "<=",
            TokenType.GREATER: ">",
            TokenType.GREATER_EQUAL: ">=",
        }
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )

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

        self._poison(
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))

    def _equality(self, left: Value, right: Value, operator: TokenType) -> Value:
        if left.optional or right.optional:
            return self._optional_equality(left, right, operator)
        return self._plain_equality(left, right, operator)


    def _plain_equality(
        self, left: Value, right: Value, operator: TokenType
    ) -> Value:
        equal = operator is TokenType.EQUAL_EQUAL

        if left.ty is ValueType.ANY or right.ty is ValueType.ANY:
            left_boxed = self._box_value(left, None)
            right_boxed = self._box_value(right, None)
            left_tag = self.builder.extract_value(left_boxed.llvm, 0)
            left_payload = self.builder.extract_value(left_boxed.llvm, 1)
            right_tag = self.builder.extract_value(right_boxed.llvm, 0)
            right_payload = self.builder.extract_value(right_boxed.llvm, 1)
            result = self.builder.call(
                self._function("lox_any_equal", _I32, [_INT, _INT, _INT, _INT]),
                [left_tag, left_payload, right_tag, right_payload],
            )
            compared = self.builder.icmp_signed(
                "!=", result, llvm_ir.constant(_I32, 0)
            )
            if not equal:
                compared = self.builder.not_(compared)
            return Value(ValueType.BOOL, compared)

        if left.ty is ValueType.ENUM and right.ty is ValueType.ENUM:
            equal_value = self.builder.call(
                self._function("lox_enum_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed(
                "!=", equal_value, llvm_ir.constant(_I32, 0)
            )
            if not equal:
                result = self.builder.not_(result)
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.TUPLE and right.ty is ValueType.TUPLE:
            equal_value = self._tuple_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.MAP and right.ty is ValueType.MAP:
            equal_value = self._map_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.LIST and right.ty is ValueType.LIST:
            equal_value = self._list_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.RANGE and right.ty is ValueType.RANGE:
            comparison = self.builder.call(
                self._function("lox_range_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed(
                "!=" if equal else "==", comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.NIL or right.ty is ValueType.NIL:
            both_nil = left.ty is right.ty
            return Value(
                ValueType.BOOL, llvm_ir.constant(_BOOL, int(both_nil == equal))
            )

        if left.ty is ValueType.ENUM and right.ty is ValueType.ENUM:
            equal_value = self.builder.call(
                self._function("lox_enum_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed(
                "!=", equal_value, llvm_ir.constant(_I32, 0)
            )
            if not equal:
                result = self.builder.not_(result)
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.TUPLE and right.ty is ValueType.TUPLE:
            equal_value = self._tuple_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.MAP and right.ty is ValueType.MAP:
            equal_value = self._map_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.LIST and right.ty is ValueType.LIST:
            equal_value = self._list_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.RANGE and right.ty is ValueType.RANGE:
            comparison = self.builder.call(
                self._function("lox_range_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed(
                "!=" if equal else "==", comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

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
                code=Code.BACKEND_UNSUPPORTED,
            )

        if self._finally_stack:
            saved = self._finally_stack.pop()
            try:
                self._scopes.append({})
                try:
                    for statement in saved:
                        if self.builder.block.is_terminated:
                            break
                        self._stmt(statement)
                finally:
                    self._scopes.pop()
            finally:
                self._finally_stack = self._finally_stack
            if self.builder.block.is_terminated:
                return

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
            code=Code.BACKEND_UNSUPPORTED,
        )

    def _logical(self, expr: Logical) -> Value:
        if expr.operator.type is TokenType.QUESTION_QUESTION:
            return self._coalesce(expr)
        return self._short_circuit(expr)

    def _coalesce(self, expr: Logical) -> Value:
        left = self._expr(expr.left)
        if not left.optional:
            # Um valor não-nil é sempre não-nil: o lado direito é morto.
            if left.ty is not ValueType.NIL:
                return left
            return self._expr(expr.right)

        coalesced = self.types.get(expr)
        if coalesced is not None and self._type_desc(coalesced, expr.operator.line).ty is ValueType.ANY:
            return self._coalesce_any(left, expr)

        some = llvm_ir.append_block(self._function_ir, "coalesce.some")
        nothing = llvm_ir.append_block(self._function_ir, "coalesce.nil")
        end = llvm_ir.append_block(self._function_ir, "coalesce.end")
        self.builder.cbranch(self._optional_tag(left), some, nothing)

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

    def _coalesce_any(self, left: Value, expr: Logical) -> Value:
        some = llvm_ir.append_block(self._function_ir, "coalesce.some")
        nothing = llvm_ir.append_block(self._function_ir, "coalesce.nil")
        end = llvm_ir.append_block(self._function_ir, "coalesce.end")
        self.builder.cbranch(self._optional_tag(left), some, nothing)

        self.builder = llvm_ir.builder(some)
        some_value = self._box_value(
            self._optional_payload(left), expr.operator.line
        )
        self.builder.branch(end)
        some_end = self.builder.block

        self.builder = llvm_ir.builder(nothing)
        right = self._box_value(
            self._expr(expr.right), expr.operator.line
        )
        self.builder.branch(end)
        nothing_end = self.builder.block

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(
            self._storage_llvm_type(TypeDesc(ValueType.ANY)),
            "coalesce.any",
        )
        merged.add_incoming(some_value.llvm, some_end)
        merged.add_incoming(right.llvm, nothing_end)
        return Value(ValueType.ANY, merged)

    def _short_circuit(self, expr: Logical) -> Value:
        operator = expr.operator.type
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
            case ValueType.ANY:
                tag = self.builder.extract_value(value.llvm, 0)
                payload = self.builder.extract_value(value.llvm, 1)
                is_nil = self.builder.icmp_signed(
                    "==", tag, llvm_ir.constant(_INT, 0)
                )
                is_false = self.builder.and_(
                    self.builder.icmp_signed(
                        "==", tag, llvm_ir.constant(_INT, 3)
                    ),
                    self.builder.icmp_signed(
                        "==", payload, llvm_ir.constant(_INT, 0)
                    ),
                )
                return self.builder.not_(
                    self.builder.or_(is_nil, is_false)
                )
            case (
                ValueType.INT
                | ValueType.FLOAT
                | ValueType.STRING
                | ValueType.FUNCTION
                | ValueType.CLASS
                | ValueType.INSTANCE
                | ValueType.RANGE
            ):
                # Só nil e false são falsy: `0`, `0.0`, `""` e funções são truthy.
                return llvm_ir.constant(_BOOL, 1)
            case ValueType.NIL:
                return llvm_ir.constant(_BOOL, 0)

    def _poison(
        self,
        target: Token | int,
        message: str,
        *,
        column: int = 0,
        code: Code = Code.RUNTIME_ERROR,
    ) -> None:
        """Rebaixa erro estático a `lox_panic` e continua num bloco inalcançável.

        `target` é o token do erro (leva linha e coluna) ou só a linha. `code` deve
        espelhar o erro que o tree-walk levantaria em runtime (mesmo ponto, mesma
        família), senão o stderr do binário diverge do interpretado e o I1 quebra.
        """
        if isinstance(target, Token):
            line = target.line
            column = target.column
        else:
            line = target
        function = self._panic_function()
        text = self._cstring(message)
        pointer = llvm_ir.cstring_pointer(self.builder, text)
        code_pointer = llvm_ir.cstring_pointer(
            self.builder, self._cstring(code.value)
        )
        self.builder.call(
            function,
            [
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
                code_pointer,
                pointer,
            ],
        )
        self.builder.unreachable()

        block = llvm_ir.append_block(self._function_ir, f"poison{self._poison_count}")
        self._poison_count += 1
        self.builder = llvm_ir.builder(block)

    def _panic_function(self) -> Any:
        function = self._runtime.get("lox_panic")
        if function is None:
            function = llvm_ir.declare_noreturn(
                self.module, "lox_panic", [_I32, _I32, _I8_PTR, _I8_PTR]
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
    generic_instances: Any = None,
    generic_classes: Any = None,
    generic_class_sites: Any = None,
    source_path: str = "<lox>",
) -> Any:
    module = llvm_ir.new_module()
    Lowerer(
        module,
        types=types,
        depths=depths,
        generic_instances=generic_instances,
        generic_classes=generic_classes,
        generic_class_sites=generic_class_sites,
        source_path=source_path,
    ).lower(statements)
    return module