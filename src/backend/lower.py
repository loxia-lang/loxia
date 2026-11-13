"""Lowering da AST para IR do LLVM (L0-L4).

Escopo (contrato em [ADR-0031](../../../docs/adr/0031-backend-nativo.md) e
[ADR-0046](../../../docs/adr/0046-closures-celulas-l4.md)):
`print`, `Int`, `Float`, `Bool`, `nil`, aritmética com promoção, `/`, `%`, comparações,
igualdade, unários, `if`/`while`/blocos, variáveis (`val`/`var`), funções de topo com
chamada, `return`, recursão, aridade como panic site, strings e closures.

Funções de usuário têm ABI `(i8* env, params...)`; uma closure é um ponteiro para
`{ fnptr, env, display }` na arena. Variáveis capturadas viram células no heap; as não
capturadas continuam em `alloca`. O que ainda não tem representação — `Any`, `List`/`Map`,
classes, função com defaults como valor, função genérica como valor — falha com erro de
compilação explícito (exit 65), nunca com lowering silencioso.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from src.backend import llvm_ir
from src.backend.captures import CaptureAnalysis, analyze_captures
from src.frontend.expr import (
    Assign,
    Binary,
    Call,
    Conditional,
    Expr,
    Grouping,
    InterpolatedString,
    Lambda,
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
from src.frontend.ty import FnTy, GenericFnTy, Ty

_INT = llvm_ir.int_type(64)
_BOOL = llvm_ir.int_type(1)
_I32 = llvm_ir.int_type(32)
_FLOAT = llvm_ir.float_type()
_VOID = llvm_ir.void_type()
_I8_PTR = llvm_ir.pointer_type()
_CLOSURE = llvm_ir.literal_struct([_I8_PTR, _I8_PTR, _I8_PTR])

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
    FUNCTION = auto()


NUMERIC = (ValueType.INT, ValueType.FLOAT)


@dataclass(frozen=True)
class FnSig:
    """Assinatura de um valor de função, derivada do `FnTy` do checker."""

    params: tuple[TypeDesc, ...]
    ret: TypeDesc
    min_params: int


@dataclass(frozen=True)
class TypeDesc:
    """Tipo representável no backend; `fn` só existe para `ValueType.FUNCTION`."""

    ty: ValueType
    fn: FnSig | None = None

    def same_as(self, other: TypeDesc) -> bool:
        return self.ty is other.ty and self.fn == other.fn


@dataclass(frozen=True)
class Binding:
    """Variável: slot de memória (`alloca`/global) ou célula, e seu tipo."""

    storage: Any
    ty: ValueType
    sig: FnSig | None = None
    cell: bool = False
    function: FunctionInfo | None = None


@dataclass(frozen=True)
class FunctionInfo:
    """Assinatura já emitida: função LLVM, tipos e parâmetros declarados."""

    ir: Any
    param_types: list[ValueType]
    param_sigs: list[FnSig | None]
    return_type: ValueType
    return_sig: FnSig | None
    params: list[Param]
    fn_sig: FnSig


@dataclass(frozen=True)
class Value:
    """Valor no IR. `NIL` não tem representação em LLVM: `llvm` fica `None`."""

    ty: ValueType
    llvm: Any = None
    sig: FnSig | None = None


@dataclass(frozen=True)
class CaptureBinding:
    """Uma captura já resolvida: nome e binding (célula) do escopo externo."""

    name: str
    binding: Binding


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
        self._displays: dict[str, Any] = {}
        self._poison_count = 0
        self._string_count = 0
        self._function_counter = 0
        self._scopes: list[dict[str, Binding]] = [{}]
        self._captures: dict[str, Binding] = {}
        self._globals: dict[str, Binding] = {}
        self._top_level: dict[int, FunctionInfo] = {}
        self._function_ir: Any = None
        self._return_type: ValueType = ValueType.NIL
        self._return_sig: FnSig | None = None
        self._analysis = CaptureAnalysis({}, frozenset())

    # --- programa ---

    def lower(self, statements: list[Stmt]) -> None:
        self._analysis = analyze_captures(statements)
        self._predeclare_functions(statements)

        main = llvm_ir.define_main(self.module)
        self.main = main
        self._function_ir = main
        self._return_type = ValueType.NIL
        self._return_sig = None
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

    def _predeclare_functions(self, statements: list[Stmt]) -> None:
        for statement in statements:
            if not isinstance(statement, Function):
                continue

            info = self._function_info(
                statement, llvm_name=f"lox.{statement.name.lexeme}"
            )
            self._top_level[id(statement)] = info

            slot = llvm_ir.global_variable(
                self.module, f"g.{statement.name.lexeme}", _I8_PTR
            )
            self._globals[statement.name.lexeme] = Binding(
                slot,
                ValueType.FUNCTION,
                info.fn_sig,
                function=info,
            )

    def _function_info(
        self, stmt: Function, *, llvm_name: str | None = None
    ) -> FunctionInfo:
        if stmt.type_params:
            raise _unsupported("Generic functions", stmt.name.line)

        params: list[TypeDesc] = []
        minimum = 0
        for param in stmt.params:
            desc = self._param_desc(param)
            params.append(desc)
            if param.default is None:
                minimum += 1

        return_desc = self._return_desc(
            stmt.return_type, stmt.name.line, stmt.name.lexeme
        )
        sig = FnSig(tuple(params), return_desc, minimum)

        if llvm_name is None:
            self._function_counter += 1
            llvm_name = f"lox.{stmt.name.lexeme}.{self._function_counter}"

        result = (
            _VOID
            if return_desc.ty is ValueType.NIL
            else self._llvm_type(return_desc.ty)
        )
        signature = llvm_ir.declare(
            self.module,
            llvm_name,
            result,
            [_I8_PTR, *[self._llvm_type(param.ty) for param in params]],
        )
        return FunctionInfo(
            signature,
            [param.ty for param in params],
            [param.fn for param in params],
            return_desc.ty,
            return_desc.fn,
            stmt.params,
            sig,
        )

    def _param_desc(self, param: Param) -> TypeDesc:
        if param.type_annotation is None:
            raise BackendError(
                f"Parameter '{param.name.lexeme}' needs a type annotation "
                "for the backend.",
                param.name.line,
            )
        return self._type_desc(param.type_annotation, param.name.line)

    def _return_desc(self, ty: Ty | None, line: int, name: str) -> TypeDesc:
        if ty is None:
            raise BackendError(
                f"Function '{name}' needs a return type annotation for the backend.",
                line,
            )
        return self._type_desc(ty, line)

    def _type_desc(self, ty: Ty, line: int | None) -> TypeDesc:
        if ty is TY_INT:
            return TypeDesc(ValueType.INT)
        if ty is TY_FLOAT:
            return TypeDesc(ValueType.FLOAT)
        if ty is TY_BOOL:
            return TypeDesc(ValueType.BOOL)
        if ty is TY_STRING:
            return TypeDesc(ValueType.STRING)
        if ty is TY_NIL:
            return TypeDesc(ValueType.NIL)
        if isinstance(ty, FnTy):
            params = tuple(self._type_desc(param, line) for param in ty.params)
            for param in params:
                if param.ty is ValueType.NIL:
                    raise _unsupported("A Nil parameter", line)
            ret = self._type_desc(ty.ret, line)
            return TypeDesc(ValueType.FUNCTION, FnSig(params, ret, ty.min_params))
        if isinstance(ty, GenericFnTy):
            raise _unsupported("Generic function value", line)

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
            case ValueType.FUNCTION:
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
            case ValueType.FUNCTION:
                return Value(ValueType.FUNCTION, llvm_ir.null_pointer())
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
            info = self._top_level.get(id(stmt))
            if info is not None:
                self._define_top_level_function(stmt, info)
            else:
                self._local_function(stmt)
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
            case ValueType.FUNCTION:
                self.builder.call(
                    self._function("lox_print_function", _VOID, [_I8_PTR]),
                    [value.llvm],
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
        if isinstance(expr, InterpolatedString):
            return self._interpolated(expr)
        if isinstance(expr, Lambda):
            return self._lambda(expr)

        raise _unsupported(type(expr).__name__, None)

    # --- funções e closures ---

    def _define_top_level_function(self, stmt: Function, info: FunctionInfo) -> None:
        binding = self._globals.get(stmt.name.lexeme)
        if binding is None or binding.ty is not ValueType.FUNCTION:
            raise BackendError(
                f"Global '{stmt.name.lexeme}' was redefined as a non-function.",
                stmt.name.line,
            )

        closure = self._build_closure(info, (), f"<fn {stmt.name.lexeme}>")
        self.builder.store(closure.llvm, binding.storage)

    def _local_function(self, stmt: Function) -> None:
        info = self._function_info(stmt)
        captured = self._analysis.is_captured(stmt)

        if captured:
            cell = self._alloc_cell()
            self._store_null_cell(cell)
            binding = Binding(
                cell,
                ValueType.FUNCTION,
                info.fn_sig,
                cell=True,
                function=info,
            )
        else:
            slot = self.builder.alloca(_I8_PTR, name=stmt.name.lexeme)
            binding = Binding(
                slot,
                ValueType.FUNCTION,
                info.fn_sig,
                function=info,
            )

        self._scopes[-1][stmt.name.lexeme] = binding

        captures = self._make_captures(stmt)
        closure = self._build_closure(info, captures, f"<fn {stmt.name.lexeme}>")
        self._store_binding(binding, closure)

        self._emit_function(info, stmt, captures)

    def _lambda(self, expr: Lambda) -> Value:
        info = self._lambda_info(expr)
        captures = self._make_captures(expr)
        closure = self._build_closure(info, captures, "<lambda>")
        self._emit_function(info, expr, captures)
        return closure

    def _lambda_info(self, expr: Lambda) -> FunctionInfo:
        ty = self.types.get(expr)
        if isinstance(ty, GenericFnTy):
            raise _unsupported("Generic function value", expr.keyword.line)
        if not isinstance(ty, FnTy):
            raise _unsupported(
                "Lambda without a concrete function type", expr.keyword.line
            )

        desc = self._type_desc(ty, expr.keyword.line)
        assert desc.fn is not None
        sig = desc.fn

        self._function_counter += 1
        llvm_name = f"lox.lambda.{self._function_counter}"
        result = _VOID if sig.ret.ty is ValueType.NIL else self._llvm_type(sig.ret.ty)
        signature = llvm_ir.declare(
            self.module,
            llvm_name,
            result,
            [_I8_PTR, *[self._llvm_type(param.ty) for param in sig.params]],
        )
        return FunctionInfo(
            signature,
            [param.ty for param in sig.params],
            [param.fn for param in sig.params],
            sig.ret.ty,
            sig.ret.fn,
            expr.params,
            sig,
        )

    def _make_captures(self, node: Function | Lambda) -> tuple[CaptureBinding, ...]:
        result: list[CaptureBinding] = []
        for capture in self._analysis.captures_of(node):
            binding = self._find_binding(capture.name)
            if binding is None:
                raise BackendError(
                    f"Internal capture error for '{capture.name}'.", None
                )
            if not binding.cell:
                raise BackendError(
                    f"Captured variable '{capture.name}' was not boxed.", None
                )
            result.append(CaptureBinding(capture.name, binding))

        return tuple(result)

    def _find_binding(self, name: str) -> Binding | None:
        for scope in reversed(self._scopes):
            binding = scope.get(name)
            if binding is not None:
                return binding

        return self._captures.get(name)

    def _build_closure(
        self,
        info: FunctionInfo,
        captures: tuple[CaptureBinding, ...],
        display: str,
    ) -> Value:
        env: Any = llvm_ir.null_pointer()
        if captures:
            raw_env = self.builder.call(
                self._function("lox_alloc_env", _I8_PTR, [_INT]),
                [llvm_ir.constant(_INT, len(captures))],
            )
            env_type = llvm_ir.literal_struct([_I8_PTR] * len(captures))
            env_struct = self.builder.bitcast(raw_env, env_type.as_pointer())
            for index, capture in enumerate(captures):
                field = self.builder.gep(
                    env_struct,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
                )
                self.builder.store(capture.binding.storage, field)
            env = raw_env

        raw_closure = self.builder.call(
            self._function("lox_alloc_closure", _I8_PTR, []), []
        )
        closure = self.builder.bitcast(raw_closure, _CLOSURE.as_pointer())
        fn_slot = self.builder.gep(
            closure, [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)]
        )
        env_slot = self.builder.gep(
            closure, [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)]
        )
        name_slot = self.builder.gep(
            closure, [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 2)]
        )
        self.builder.store(self.builder.bitcast(info.ir, _I8_PTR), fn_slot)
        self.builder.store(env, env_slot)
        self.builder.store(self._display_pointer(display), name_slot)

        return Value(ValueType.FUNCTION, raw_closure, info.fn_sig)

    def _display_pointer(self, display: str) -> Any:
        global_ = self._displays.get(display)
        if global_ is None:
            global_ = llvm_ir.cstring(
                self.module, display, f"display.{len(self._displays)}"
            )
            self._displays[display] = global_

        return llvm_ir.cstring_pointer(self.builder, global_)

    def _emit_function(
        self,
        info: FunctionInfo,
        stmt: Function | Lambda,
        captures: tuple[CaptureBinding, ...],
    ) -> None:
        saved_builder = self.builder
        saved_scopes = self._scopes
        saved_captures = self._captures
        saved_function = self._function_ir
        saved_return = self._return_type
        saved_return_sig = self._return_sig

        self._function_ir = info.ir
        self._return_type = info.return_type
        self._return_sig = info.return_sig
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(info.ir, "entry"))

        env_arg = info.ir.args[0]
        if captures:
            env_type = llvm_ir.literal_struct([_I8_PTR] * len(captures))
            env_struct = self.builder.bitcast(env_arg, env_type.as_pointer())
            for index, capture in enumerate(captures):
                field = self.builder.gep(
                    env_struct,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
                )
                cell = self.builder.load(field)
                self._captures[capture.name] = Binding(
                    cell,
                    capture.binding.ty,
                    capture.binding.sig,
                    cell=True,
                    function=capture.binding.function,
                )

        for index, param in enumerate(info.params):
            desc = TypeDesc(info.param_types[index], info.param_sigs[index])
            argument = info.ir.args[index + 1]
            if self._analysis.is_captured(param):
                cell = self._alloc_cell()
                typed = self._cell_pointer(cell, desc.ty)
                self.builder.store(argument, typed)
                binding = Binding(cell, desc.ty, desc.fn, cell=True)
            else:
                slot = self.builder.alloca(
                    self._llvm_type(desc.ty), name=param.name.lexeme
                )
                self.builder.store(argument, slot)
                binding = Binding(slot, desc.ty, desc.fn)

            self._scopes[-1][param.name.lexeme] = binding

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
        self._seal_blocks(info.ir)

        self.builder = saved_builder
        self._scopes = saved_scopes
        self._captures = saved_captures
        self._function_ir = saved_function
        self._return_type = saved_return
        self._return_sig = saved_return_sig

    def _seal_blocks(self, function: Any) -> None:
        """Todo bloco precisa de terminador; continuações de panic ficam `unreachable`."""
        for block in function.blocks:
            if not block.is_terminated:
                llvm_ir.builder(block).unreachable()

    # --- células ---

    def _alloc_cell(self) -> Any:
        return self.builder.call(self._function("lox_alloc_cell", _I8_PTR, []), [])

    def _cell_pointer(self, cell: Any, ty: ValueType) -> Any:
        return self.builder.bitcast(cell, self._llvm_type(ty).as_pointer())

    def _store_null_cell(self, cell: Any) -> None:
        pointer = self.builder.bitcast(cell, _I8_PTR.as_pointer())
        self.builder.store(llvm_ir.null_pointer(), pointer)

    def _load_binding(self, binding: Binding) -> Value:
        if binding.cell:
            pointer = self._cell_pointer(binding.storage, binding.ty)
            loaded = self.builder.load(pointer)
        else:
            loaded = self.builder.load(binding.storage)

        return Value(binding.ty, loaded, binding.sig)

    def _store_binding(self, binding: Binding, value: Value) -> None:
        if binding.cell:
            pointer = self._cell_pointer(binding.storage, value.ty)
            self.builder.store(value.llvm, pointer)
        else:
            self.builder.store(value.llvm, binding.storage)

    def _guard_closure(self, value: Value, name: str, line: int) -> Value:
        is_null = self.builder.icmp_signed(
            "==", value.llvm, llvm_ir.null_pointer()
        )
        ok = llvm_ir.append_block(self._function_ir, "fn.ok")
        bad = llvm_ir.append_block(self._function_ir, "fn.null")
        self.builder.cbranch(is_null, bad, ok)

        self.builder = llvm_ir.builder(bad)
        self._poison(line, f"Undefined variable '{name}'.")

        self.builder = llvm_ir.builder(ok)
        return value

    # --- variáveis ---

    def _var(self, stmt: Var) -> None:
        if stmt.initializer is None:
            raise BackendError(
                "Uninitialized variables are not supported by the backend yet.",
                stmt.name.line,
            )

        value = self._expr(stmt.initializer)
        declared = value.ty
        sig = value.sig
        if declared is ValueType.NIL:
            raise BackendError(
                "Variables of type Nil are not supported by the backend yet.",
                stmt.name.line,
            )

        if self._function_ir is self.main and len(self._scopes) == 1:
            existing = self._globals.get(stmt.name.lexeme)
            if existing is not None:
                # Redeclaração de global (`var x = 1; var x = 2;`): o interpretador
                # mantém um único binding e sobrescreve o valor; reusar o slot é o
                # que preserva a leitura dinâmica em funções já compiladas.
                if existing.ty is not declared:
                    raise BackendError(
                        f"Global '{stmt.name.lexeme}' was already declared as "
                        f"{existing.ty.name}; redeclaring it as {declared.name} "
                        "is not supported by the backend yet.",
                        stmt.name.line,
                    )
                # `var f = ...` depois de `fn f` deixa de ser uma chamada direta.
                binding = Binding(existing.storage, declared, sig)
                self._globals[stmt.name.lexeme] = binding
                self.builder.store(value.llvm, binding.storage)
                return

            name = f"g.{stmt.name.lexeme}"
            global_ = llvm_ir.global_variable(
                self.module, name, self._llvm_type(declared)
            )
            binding = Binding(global_, declared, sig)
            self._globals[stmt.name.lexeme] = binding
            self.builder.store(value.llvm, global_)
            return

        if self._analysis.is_captured(stmt):
            cell = self._alloc_cell()
            cell_pointer = self._cell_pointer(cell, declared)
            self.builder.store(value.llvm, cell_pointer)
            self._scopes[-1][stmt.name.lexeme] = Binding(
                cell, declared, sig, cell=True
            )
            return

        slot = self.builder.alloca(self._llvm_type(declared), name=stmt.name.lexeme)
        self.builder.store(value.llvm, slot)
        self._scopes[-1][stmt.name.lexeme] = Binding(slot, declared, sig)

    def _variable(self, expr: Variable) -> Value:
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(expr.name.line, f"Undefined variable '{expr.name.lexeme}'.")
            return self._zero(ValueType.INT)

        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        if (
            binding.function is not None
            and binding.function.fn_sig.min_params
            < len(binding.function.fn_sig.params)
        ):
            raise BackendError(
                "Functions with default parameters as values are not supported by the "
                "backend yet.",
                expr.name.line,
            )

        value = self._load_binding(binding)
        if value.ty is ValueType.FUNCTION:
            return self._guard_closure(value, expr.name.lexeme, expr.name.line)
        return value

    def _assign(self, expr: Assign) -> Value:
        value = self._expr(expr.value)
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(expr.name.line, f"Undefined variable '{expr.name.lexeme}'.")
            return value

        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        if not TypeDesc(binding.ty, binding.sig).same_as(
            TypeDesc(value.ty, value.sig)
        ):
            raise BackendError(
                f"Can't assign {value.ty.name} to a {binding.ty.name} variable "
                "for the backend yet.",
                expr.name.line,
            )
        if (
            binding.function is not None
            and binding.function.fn_sig.min_params
            < len(binding.function.fn_sig.params)
        ):
            raise BackendError(
                "Functions with default parameters as values are not supported by the "
                "backend yet.",
                expr.name.line,
            )

        self._store_binding(binding, value)

        if binding.function is not None:
            # O binding agora aponta para outra função: chamadas seguintes são
            # indiretas (o corpo pode ter mudado).
            replacement = Binding(
                binding.storage, value.ty, value.sig, binding.cell
            )
            self._replace_binding(expr, expr.name.lexeme, replacement)

        return value

    def _replace_binding(self, expr: Expr, name: str, binding: Binding) -> None:
        depth = self.depths.get(expr)
        if depth is None:
            self._globals[name] = binding
        elif depth < len(self._scopes):
            self._scopes[-1 - depth][name] = binding
        else:
            self._captures[name] = binding

    def _lookup(self, expr: Expr, name: str, line: int) -> Binding:
        depth = self.depths.get(expr)
        if depth is None:
            binding = self._globals.get(name)
            if binding is None:
                raise BackendError(f"Undefined variable '{name}'.", line)
            return binding

        if depth < len(self._scopes):
            return self._scopes[-1 - depth][name]

        binding = self._captures.get(name)
        if binding is None:
            raise BackendError(f"Undefined variable '{name}'.", line)
        return binding

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

    def _string_literal(self, value: str) -> Value:
        global_ = llvm_ir.string_literal(self.module, value, self._string_count)
        self._string_count += 1
        return Value(ValueType.STRING, self.builder.bitcast(global_, _I8_PTR))

    def _interpolated(self, expr: InterpolatedString) -> Value:
        pieces: list[Value] = []
        for part in expr.parts:
            if isinstance(part, str):
                if part:
                    pieces.append(self._string_literal(part))
            else:
                pieces.append(self._to_string(self._expr(part)))

        if not pieces:
            return self._string_literal("")

        result = pieces[0]
        for piece in pieces[1:]:
            result = self._concat(result, piece)

        return result

    def _to_string(self, value: Value) -> Value:
        match value.ty:
            case ValueType.STRING:
                return value
            case ValueType.INT:
                function = self._function("lox_str_from_int", _I8_PTR, [_INT])
                return Value(
                    ValueType.STRING, self.builder.call(function, [value.llvm])
                )
            case ValueType.FLOAT:
                function = self._function("lox_str_from_double", _I8_PTR, [_FLOAT])
                return Value(
                    ValueType.STRING, self.builder.call(function, [value.llvm])
                )
            case ValueType.BOOL:
                function = self._function("lox_str_from_bool", _I8_PTR, [_I32])
                widened = self.builder.zext(value.llvm, _I32)
                return Value(
                    ValueType.STRING, self.builder.call(function, [widened])
                )
            case ValueType.FUNCTION:
                function = self._function(
                    "lox_str_from_function", _I8_PTR, [_I8_PTR]
                )
                return Value(
                    ValueType.STRING, self.builder.call(function, [value.llvm])
                )
            case ValueType.NIL:
                function = self._function("lox_str_nil", _I8_PTR, [])
                return Value(ValueType.STRING, self.builder.call(function, []))

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
            if self._return_type is not ValueType.NIL:
                raise BackendError(
                    "Returning nil from a non-Nil function is not supported "
                    "by the backend yet.",
                    stmt.keyword.line,
                )
            self.builder.ret_void()
            return

        value = self._expr(stmt.value)
        if not TypeDesc(value.ty, value.sig).same_as(
            TypeDesc(self._return_type, self._return_sig)
        ):
            raise BackendError(
                f"Expected {self._return_type.name}, found {value.ty.name} "
                "in this return for the backend yet.",
                stmt.keyword.line,
            )

        if value.ty is ValueType.NIL:
            self.builder.ret_void()
            return

        self.builder.ret(value.llvm)

    def _call(self, expr: Call) -> Value:
        if isinstance(expr.callee, Variable):
            name = expr.callee.name.lexeme
            if name == "len":
                return self._len(expr)
            if name == "str":
                return self._str(expr)
            if name == "repr":
                return self._repr(expr)

        info: FunctionInfo | None = None
        binding: Binding | None = None
        if isinstance(expr.callee, Variable):
            depth = self.depths.get(expr.callee)
            if depth is not None or expr.callee.name.lexeme in self._globals:
                binding = self._lookup(
                    expr.callee, expr.callee.name.lexeme, expr.callee.name.line
                )
                if binding.function is not None:
                    info = binding.function

        if info is not None:
            assert binding is not None
            assert isinstance(expr.callee, Variable)
            callee = self._load_binding(binding)
            callee = self._guard_closure(
                callee, expr.callee.name.lexeme, expr.callee.name.line
            )
        else:
            callee = self._expr(expr.callee)

        if callee.ty is not ValueType.FUNCTION or callee.sig is None:
            self._poison(expr.paren.line, "Can only call functions and classes.")
            return self._zero(ValueType.INT)

        arguments = [self._expr(argument) for argument in expr.arguments]
        sig = info.fn_sig if info is not None else callee.sig
        count = len(arguments)

        minimum = sig.min_params
        maximum = len(sig.params)
        if not minimum <= count <= maximum:
            self._poison(expr.paren.line, self._arity_message(minimum, maximum, count))
            return self._zero(sig.ret.ty)

        if info is not None:
            for index in range(count, maximum):
                default = info.params[index].default
                assert default is not None
                arguments.append(self._expr(default))

        for index, (argument, expected) in enumerate(
            zip(arguments, sig.params, strict=True), start=1
        ):
            if not TypeDesc(argument.ty, argument.sig).same_as(expected):
                name = (
                    expr.callee.name.lexeme
                    if isinstance(expr.callee, Variable)
                    else "function"
                )
                raise BackendError(
                    f"Argument {index} of '{name}' is {argument.ty.name}, "
                    f"expected {expected.ty.name}, for the backend yet.",
                    expr.paren.line,
                )

        fnptr = self._closure_field(callee, 0)
        env = self._closure_field(callee, 1)
        function_type = llvm_ir.function_pointer(
            _VOID if sig.ret.ty is ValueType.NIL else self._llvm_type(sig.ret.ty),
            [_I8_PTR, *[self._llvm_type(param.ty) for param in sig.params]],
        )
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [env, *[argument.llvm for argument in arguments]],
        )
        if sig.ret.ty is ValueType.NIL:
            return Value(ValueType.NIL)
        return Value(sig.ret.ty, call, sig.ret.fn)

    def _closure_field(self, closure: Value, index: int) -> Any:
        struct_ = self.builder.bitcast(closure.llvm, _CLOSURE.as_pointer())
        field = self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
        )
        return self.builder.load(field)

    def _conditional(self, expr: Conditional) -> Value:
        condition = self._truthy(self._expr(expr.condition))
        then_block = llvm_ir.append_block(self._function_ir, "cond.then")
        else_block = llvm_ir.append_block(self._function_ir, "cond.else")
        end_block = llvm_ir.append_block(self._function_ir, "cond.end")
        self.builder.cbranch(condition, then_block, else_block)

        self.builder = llvm_ir.builder(then_block)
        then_value = self._expr(expr.then_branch)
        # O predecessor do merge é o bloco em que o branch para `end_block` é emitido,
        # não o bloco inicial do ramo: um ternário aninhado termina em outro bloco.
        then_end = self.builder.block
        then_open = not then_end.is_terminated
        if then_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(else_block)
        else_value = self._expr(expr.else_branch)
        else_end = self.builder.block
        else_open = not else_end.is_terminated
        if else_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if not TypeDesc(then_value.ty, then_value.sig).same_as(
            TypeDesc(else_value.ty, else_value.sig)
        ):
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
            merged.add_incoming(then_value.llvm, then_end)
            merged.add_incoming(else_value.llvm, else_end)
            return Value(then_value.ty, merged, then_value.sig)

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
            # No L4 um valor não-nil é sempre não-nil: o lado direito é código morto.
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
        right_end = self.builder.block
        right_open = not right_end.is_terminated
        if right_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if not TypeDesc(left.ty, left.sig).same_as(TypeDesc(right.ty, right.sig)):
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
        merged.add_incoming(right.llvm, right_end)
        return Value(left.ty, merged, left.sig)

    def _arity_message(self, minimum: int, maximum: int, count: int) -> str:
        if minimum == maximum:
            return f"Expected {minimum} arguments but got {count}."
        if count < minimum:
            return f"Expected at least {minimum} arguments but got {count}."
        return f"Expected {minimum} to {maximum} arguments but got {count}."

    def _concat(self, left: Value, right: Value) -> Value:
        function = self._function("lox_str_concat", _I8_PTR, [_I8_PTR, _I8_PTR])
        return Value(
            ValueType.STRING, self.builder.call(function, [left.llvm, right.llvm])
        )

    def _repr(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1:
            self._poison(
                expr.paren.line,
                f"Expected 1 arguments but got {len(arguments)}.",
            )
            return self._zero(ValueType.STRING)

        argument = arguments[0]
        if argument.ty is not ValueType.STRING:
            return self._to_string(argument)

        function = self._function("lox_str_quote", _I8_PTR, [_I8_PTR])
        return Value(ValueType.STRING, self.builder.call(function, [argument.llvm]))

    def _str(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1:
            self._poison(
                expr.paren.line,
                f"Expected 1 arguments but got {len(arguments)}.",
            )
            return self._zero(ValueType.STRING)

        return self._to_string(arguments[0])

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
            case (
                ValueType.INT
                | ValueType.FLOAT
                | ValueType.STRING
                | ValueType.FUNCTION
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
