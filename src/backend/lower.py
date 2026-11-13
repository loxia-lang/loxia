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
    Get,
    Grouping,
    InterpolatedString,
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
    Field,
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
from src.frontend.ty import (
    ClassObjectTy,
    ClassTy,
    FnTy,
    GenericFnTy,
    Ty,
    UnionTy,
)

_INT = llvm_ir.int_type(64)
_BOOL = llvm_ir.int_type(1)
_I32 = llvm_ir.int_type(32)
_FLOAT = llvm_ir.float_type()
_VOID = llvm_ir.void_type()
_I8_PTR = llvm_ir.pointer_type()
_CLOSURE = llvm_ir.literal_struct([_I8_PTR, _I8_PTR, _I8_PTR])
_CLASS_DESC = llvm_ir.literal_struct(
    [_I8_PTR, _INT, _I8_PTR, _I8_PTR, _INT, _I8_PTR, _INT, _INT]
)

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
    CLASS = auto()
    INSTANCE = auto()


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
    optional: bool = False
    class_name: str | None = None

    def same_as(self, other: TypeDesc) -> bool:
        return (
            self.ty is other.ty
            and self.fn == other.fn
            and self.optional == other.optional
            and self.class_name == other.class_name
        )


@dataclass(frozen=True)
class Binding:
    """Variável: slot de memória (`alloca`/global) ou célula, e seu tipo."""

    storage: Any
    ty: ValueType
    sig: FnSig | None = None
    optional: bool = False
    cell: bool = False
    function: FunctionInfo | None = None
    class_name: str | None = None

    @property
    def desc(self) -> TypeDesc:
        return TypeDesc(self.ty, self.sig, self.optional, self.class_name)


@dataclass(frozen=True)
class FunctionInfo:
    """Assinatura já emitida: função LLVM e assinatura do checker."""

    ir: Any
    params: list[Param]
    fn_sig: FnSig
    this_class: str | None = None
    is_init: bool = False


@dataclass(frozen=True)
class Value:
    """Valor no IR. `NIL` não tem representação em LLVM: `llvm` fica `None`."""

    ty: ValueType
    llvm: Any = None
    sig: FnSig | None = None
    optional: bool = False
    class_name: str | None = None

    @property
    def desc(self) -> TypeDesc:
        return TypeDesc(self.ty, self.sig, self.optional, self.class_name)


@dataclass(frozen=True)
class CaptureBinding:
    """Uma captura já resolvida: nome e binding (célula) do escopo externo."""

    name: str
    binding: Binding


@dataclass(frozen=True)
class FieldLayout:
    name: str
    ty: TypeDesc
    mutable: bool
    initializer: Expr | None
    index: int
    line: int


@dataclass
class MethodLayout:
    name: str
    info: FunctionInfo
    index: int
    node: Function | None = None
    thunk: Any = None


@dataclass
class ClassLayout:
    name: str
    id: int
    fields: list[FieldLayout]
    methods: list[MethodLayout]
    init: FunctionInfo | None
    init_node: Function | None = None
    super_name: str | None = None
    super_layout: ClassLayout | None = None
    init_method: MethodLayout | None = None
    vtable_size: int = 0
    descriptor: Any = None
    vtable: Any = None
    ctor: Any = None
    instance_type: Any = None

    def field(self, name: str) -> FieldLayout | None:
        for field in self.fields:
            if field.name == name:
                return field
        if self.super_layout is not None:
            return self.super_layout.field(name)
        return None

    def method(self, name: str) -> MethodLayout | None:
        for method in self.methods:
            if method.name == name:
                return method
        if self.super_layout is not None:
            return self.super_layout.method(name)
        return None

    def effective_init(self) -> FunctionInfo | None:
        if self.init is not None:
            return self.init
        if self.super_layout is not None:
            return self.super_layout.effective_init()
        return None

    def init_node_for_emit(self) -> Function | None:
        if self.init_node is not None:
            return self.init_node
        if self.super_layout is not None:
            return self.super_layout.init_node_for_emit()
        return None

    def field_count(self) -> int:
        base = 0 if self.super_layout is None else self.super_layout.field_count()
        return base + len(self.fields)

    def all_fields(self) -> list[FieldLayout]:
        base = [] if self.super_layout is None else self.super_layout.all_fields()
        return [*base, *self.fields]


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
        self._class_names: set[str] = set()
        self._classes: dict[str, ClassLayout] = {}
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

    def _predeclare_classes(self, statements: list[Stmt]) -> None:
        classes = [stmt for stmt in statements if isinstance(stmt, Class)]
        self._class_names = {stmt.name.lexeme for stmt in classes}

        for index, stmt in enumerate(classes, start=1):
            name = stmt.name.lexeme
            if stmt.type_params:
                raise _unsupported("Generic class", stmt.name.line)
            if len(stmt.fields) > 64:
                raise BackendError(
                    "Classes with more than 64 fields are not supported by the "
                    "backend yet.",
                    stmt.name.line,
                )

            super_layout: ClassLayout | None = None
            super_name: str | None = None
            if stmt.superclass is not None:
                super_name = stmt.superclass.name.lexeme
                super_layout = self._classes.get(super_name)
                if super_layout is None:
                    raise _unsupported(
                        f"Inheritance from '{super_name}'",
                        stmt.superclass.name.line,
                    )

            base_fields = 0 if super_layout is None else super_layout.field_count()
            base_methods = 0 if super_layout is None else super_layout.vtable_size

            fields: list[FieldLayout] = []
            for local_index, field in enumerate(stmt.fields):
                desc = self._field_desc(field)
                fields.append(
                    FieldLayout(
                        field.name.lexeme,
                        desc,
                        field.mutable,
                        field.initializer,
                        base_fields + local_index,
                        field.name.line,
                    )
                )

            methods: list[MethodLayout] = []
            init: FunctionInfo | None = None
            init_method: MethodLayout | None = None
            new_methods = 0

            for method in stmt.methods:
                if method.type_params:
                    raise _unsupported("Generic method", method.name.line)
                is_init = method.name.lexeme == "init"
                info = self._function_info(
                    method,
                    llvm_name=f"lox.{name}.{method.name.lexeme}",
                    this_class=name,
                    is_init=is_init,
                )
                if not is_init and any(
                    param.default is not None for param in method.params
                ):
                    raise _unsupported(
                        "Default parameters in methods", method.name.line
                    )
                if is_init:
                    init = info
                    init_method = MethodLayout("init", info, -1, node=method)
                    continue

                inherited = (
                    super_layout.method(method.name.lexeme)
                    if super_layout is not None
                    else None
                )
                slot = (
                    inherited.index
                    if inherited is not None
                    else base_methods + new_methods
                )
                if inherited is None:
                    new_methods += 1
                methods.append(
                    MethodLayout(
                        method.name.lexeme,
                        info,
                        slot,
                        node=method,
                    )
                )

            if init_method is None and super_layout is not None:
                init_method = super_layout.init_method

            effective = init
            if effective is None and super_layout is not None:
                effective = super_layout.effective_init()

            instance_type = llvm_ir.literal_struct(
                [_I8_PTR, _INT, *([_INT] * (base_fields + len(fields)))]
            )
            layout = ClassLayout(
                name,
                index,
                fields,
                methods,
                init,
                init_node=next(
                    (
                        method
                        for method in stmt.methods
                        if method.name.lexeme == "init"
                    ),
                    None,
                ),
                super_name=super_name,
                super_layout=super_layout,
                init_method=init_method,
                vtable_size=base_methods + new_methods,
                instance_type=instance_type,
            )
            ctor_params = (
                []
                if effective is None
                else [
                    self._storage_llvm_type(param)
                    for param in effective.fn_sig.params
                ]
            )
            layout.ctor = llvm_ir.declare(
                self.module,
                f"lox.ctor.{name}",
                _I8_PTR,
                ctor_params,
            )
            self._classes[name] = layout

            slot = llvm_ir.global_variable(
                self.module, f"g.{name}", _I8_PTR
            )
            self._globals[name] = Binding(
                slot,
                ValueType.CLASS,
                class_name=name,
            )

    def _field_desc(self, field: Field) -> TypeDesc:
        annotated: TypeDesc | None = None
        if field.type_annotation is not None:
            annotated = self._type_desc(field.type_annotation, field.name.line)

        if field.initializer is not None:
            initial = self._const_desc(field.initializer, field.name.line)
            desc = (
                annotated
                if annotated is not None and annotated.optional
                else initial
            )
        elif annotated is not None:
            desc = annotated
        else:
            raise BackendError(
                f"Field '{field.name.lexeme}' needs a type annotation "
                "for the backend.",
                field.name.line,
            )

        if desc.ty is ValueType.NIL:
            raise BackendError(
                "Fields of type Nil are not supported by the backend yet.",
                field.name.line,
            )
        if desc.optional and desc.ty not in (
            ValueType.STRING,
            ValueType.INSTANCE,
            ValueType.CLASS,
        ):
            raise _unsupported("Optional scalar fields", field.name.line)
        return desc

    def _const_desc(self, expr: Expr, line: int) -> TypeDesc:
        if isinstance(expr, Literal):
            value = expr.value
            if value is None:
                return TypeDesc(ValueType.NIL)
            if isinstance(value, bool):
                return TypeDesc(ValueType.BOOL)
            if isinstance(value, int):
                return TypeDesc(ValueType.INT)
            if isinstance(value, float):
                return TypeDesc(ValueType.FLOAT)
            if isinstance(value, str):
                return TypeDesc(ValueType.STRING)
        if isinstance(expr, Grouping):
            return self._const_desc(expr.expression, line)
        if isinstance(expr, Unary) and expr.operator.type is TokenType.MINUS:
            inner = self._const_desc(expr.right, line)
            if inner.ty in NUMERIC:
                return inner

        raise BackendError(
            "Field initializer must be a constant for the backend.", line
        )

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
        self,
        stmt: Function,
        *,
        llvm_name: str | None = None,
        this_class: str | None = None,
        is_init: bool = False,
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

        if is_init:
            return_desc = TypeDesc(ValueType.NIL)
        else:
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
            else self._storage_llvm_type(return_desc)
        )
        prefix = [_I8_PTR, *([_I8_PTR] if this_class is not None else [])]
        signature = llvm_ir.declare(
            self.module,
            llvm_name,
            result,
            [*prefix, *[self._storage_llvm_type(param) for param in params]],
        )
        return FunctionInfo(
            signature,
            stmt.params,
            sig,
            this_class=this_class,
            is_init=is_init,
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
        if isinstance(ty, UnionTy):
            members = ty.members
            non_nil = [member for member in members if member is not TY_NIL]
            if len(members) == 2 and len(non_nil) == 1:
                inner = self._type_desc(non_nil[0], line)
                if inner.ty is ValueType.FUNCTION:
                    raise _unsupported("Optional function types", line)
                if inner.ty is ValueType.NIL or inner.optional:
                    raise _unsupported("Nested optionals", line)
                return TypeDesc(inner.ty, inner.fn, True, inner.class_name)

            raise _unsupported("Union types with more than one non-Nil member", line)

        if isinstance(ty, ClassTy):
            if ty.args:
                raise _unsupported("Generic class instances", line)
            if ty.name not in self._class_names:
                raise _unsupported(f"Class '{ty.name}'", line)
            return TypeDesc(ValueType.INSTANCE, class_name=ty.name)
        if isinstance(ty, ClassObjectTy):
            if ty.name not in self._class_names:
                raise _unsupported(f"Class '{ty.name}'", line)
            return TypeDesc(ValueType.CLASS, class_name=ty.name)

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
            case ValueType.CLASS | ValueType.INSTANCE:
                return _I8_PTR
            case ValueType.NIL:
                return _VOID

    def _storage_llvm_type(self, desc: TypeDesc) -> Any:
        if not desc.optional:
            return self._llvm_type(desc.ty)
        if desc.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return llvm_ir.literal_struct([_BOOL, self._llvm_type(desc.ty)])
        # Referências opcionais são ponteiro nulo; o L2.5 só habilita escalares.
        return self._llvm_type(desc.ty)

    def _zero_desc(self, desc: TypeDesc) -> Value:
        if not desc.optional:
            return self._zero(desc.ty)
        if desc.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            ty = self._storage_llvm_type(desc)
            return Value(desc.ty, llvm_ir.zero_value(ty), desc.fn, True)
        return Value(desc.ty, llvm_ir.null_pointer(), desc.fn, True)

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
            case ValueType.CLASS | ValueType.INSTANCE:
                return Value(ty, llvm_ir.null_pointer())
            case ValueType.NIL:
                return Value(ValueType.NIL)

    # --- opcionais (L2.5) ---

    def _some(self, desc: TypeDesc, value: Value) -> Value:
        """Constrói `{1, payload}` (escalar) ou devolve o ponteiro não nulo."""
        if not desc.optional:
            raise BackendError("Invalid optional construction.", None)
        if desc.ty not in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return Value(
                desc.ty,
                value.llvm,
                desc.fn,
                True,
                desc.class_name,
            )

        aggregate = llvm_ir.zero_value(self._storage_llvm_type(desc))
        tagged = self.builder.insert_value(
            aggregate, llvm_ir.constant(_BOOL, 1), 0
        )
        return Value(
            desc.ty,
            self.builder.insert_value(tagged, value.llvm, 1),
            desc.fn,
            True,
            desc.class_name,
        )

    def _optional_tag(self, value: Value) -> Any:
        if value.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return self.builder.extract_value(value.llvm, 0)
        return self.builder.icmp_signed(
            "!=", value.llvm, llvm_ir.null_pointer()
        )

    def _optional_payload(self, value: Value) -> Value:
        if value.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return Value(
                value.ty,
                self.builder.extract_value(value.llvm, 1),
                value.sig,
                False,
                value.class_name,
            )
        return Value(
            value.ty,
            value.llvm,
            value.sig,
            False,
            value.class_name,
        )

    def _unwrap(self, value: Value, line: int, message: str) -> Value:
        """Extrai o payload de um `T?`; tag 0 vira `lox_panic` no ponto."""
        if not value.optional:
            return value

        tag = self._optional_tag(value)
        ok = llvm_ir.append_block(self._function_ir, "opt.ok")
        bad = llvm_ir.append_block(self._function_ir, "opt.nil")
        self.builder.cbranch(tag, ok, bad)

        self.builder = llvm_ir.builder(bad)
        self._poison(line, message)

        self.builder = llvm_ir.builder(ok)
        return self._optional_payload(value)

    def _unwrap_operand(self, value: Value, line: int, message: str) -> Value:
        if value.optional:
            return self._unwrap(value, line, message)
        if value.ty is ValueType.NIL:
            self._poison(line, message)
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
        return value

    def _coerce(self, value: Value, expected: TypeDesc, line: int | None) -> Value:
        """Converte `nil`/`T` para `T?` e faz unwrap checado de `T?` para `T`."""
        if expected.ty is ValueType.NIL:
            if value.ty is ValueType.NIL:
                return value
            raise BackendError(
                f"Can't use {value.ty.name} where Nil is expected.", line
            )

        if expected.optional:
            if value.ty is ValueType.NIL:
                return self._zero_desc(expected)
            if value.optional:
                inner = TypeDesc(value.ty, value.sig, False, value.class_name)
                if not inner.same_as(TypeDesc(expected.ty, expected.fn, False, expected.class_name)):
                    raise BackendError(
                        f"Can't use {value.ty.name}? where "
                        f"{expected.ty.name}? is expected.",
                        line,
                    )
                return value

            actual = value.desc
            if not actual.same_as(
                TypeDesc(expected.ty, expected.fn, False, expected.class_name)
            ):
                raise BackendError(
                    f"Can't use {value.ty.name} where {expected.ty.name}? "
                    "is expected.",
                    line,
                )
            return self._some(expected, value)

        if value.ty is ValueType.NIL:
            raise BackendError(
                f"Can't use nil where {expected.ty.name} is expected.", line
            )

        if value.optional:
            inner = TypeDesc(value.ty, value.sig, False, value.class_name)
            if not inner.same_as(expected):
                raise BackendError(
                    f"Can't use {value.ty.name}? where {expected.ty.name} "
                    "is expected.",
                    line,
                )
            return self._unwrap(value, line or 0, "Can't use nil value.")

        if not value.desc.same_as(expected):
            raise BackendError(
                f"Can't use {value.ty.name} where {expected.ty.name} is expected.",
                line,
            )
        return value

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
        result = (
            _VOID
            if sig.ret.ty is ValueType.NIL
            else self._storage_llvm_type(sig.ret)
        )
        signature = llvm_ir.declare(
            self.module,
            llvm_name,
            result,
            [_I8_PTR, *[self._storage_llvm_type(param) for param in sig.params]],
        )
        return FunctionInfo(signature, expr.params, sig)

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
        saved_return = self._return_type_desc
        saved_in_init = self._in_init
        saved_method_class = self._method_class

        self._function_ir = info.ir
        self._return_type_desc = info.fn_sig.ret
        self._in_init = info.is_init
        self._method_class = info.this_class
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
                    capture.binding.optional,
                    cell=True,
                    function=capture.binding.function,
                    class_name=capture.binding.class_name,
                )

        offset = 1
        if info.this_class is not None:
            this_slot = self.builder.alloca(_I8_PTR, name="this")
            self.builder.store(info.ir.args[1], this_slot)
            self._scopes[-1]["this"] = Binding(
                this_slot,
                ValueType.INSTANCE,
                class_name=info.this_class,
            )
            offset = 2

        for index, param in enumerate(info.params):
            desc = info.fn_sig.params[index]
            argument = info.ir.args[offset + index]
            if self._analysis.is_captured(param):
                cell = self._alloc_cell()
                typed = self._cell_pointer(cell, desc)
                self.builder.store(argument, typed)
                binding = Binding(
                    cell,
                    desc.ty,
                    desc.fn,
                    desc.optional,
                    cell=True,
                    class_name=desc.class_name,
                )
            else:
                slot = self.builder.alloca(
                    self._storage_llvm_type(desc), name=param.name.lexeme
                )
                self.builder.store(argument, slot)
                binding = Binding(
                    slot,
                    desc.ty,
                    desc.fn,
                    desc.optional,
                    class_name=desc.class_name,
                )

            self._scopes[-1][param.name.lexeme] = binding

        for inner in stmt.body:
            if self.builder.block.is_terminated:
                break
            self._stmt(inner)

        if not self.builder.block.is_terminated:
            if info.fn_sig.ret.ty is ValueType.NIL:
                self.builder.ret_void()
            elif info.fn_sig.ret.optional:
                self.builder.ret(self._zero_desc(info.fn_sig.ret).llvm)
            else:
                # O checker garante `return` em todos os caminhos.
                self.builder.unreachable()
        self._seal_blocks(info.ir)

        self.builder = saved_builder
        self._scopes = saved_scopes
        self._captures = saved_captures
        self._function_ir = saved_function
        self._return_type_desc = saved_return
        self._in_init = saved_in_init
        self._method_class = saved_method_class

    def _seal_blocks(self, function: Any) -> None:
        """Todo bloco precisa de terminador; continuações de panic ficam `unreachable`."""
        for block in function.blocks:
            if not block.is_terminated:
                llvm_ir.builder(block).unreachable()

    # --- células ---

    def _alloc_cell(self) -> Any:
        return self.builder.call(self._function("lox_alloc_cell", _I8_PTR, []), [])

    def _cell_pointer(self, cell: Any, desc: TypeDesc) -> Any:
        return self.builder.bitcast(
            cell, self._storage_llvm_type(desc).as_pointer()
        )

    def _store_null_cell(self, cell: Any) -> None:
        pointer = self.builder.bitcast(cell, _I8_PTR.as_pointer())
        self.builder.store(llvm_ir.null_pointer(), pointer)

    def _load_binding(self, binding: Binding) -> Value:
        if binding.cell:
            pointer = self._cell_pointer(binding.storage, binding.desc)
            loaded = self.builder.load(pointer)
        else:
            loaded = self.builder.load(binding.storage)

        return Value(
            binding.ty,
            loaded,
            binding.sig,
            binding.optional,
            binding.class_name,
        )

    def _store_binding(self, binding: Binding, value: Value) -> None:
        if binding.cell:
            pointer = self._cell_pointer(binding.storage, binding.desc)
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

    # --- classes e instâncias ---

    def _class_declaration(self, stmt: Class) -> None:
        if not (self._function_ir is self.main and len(self._scopes) == 1):
            raise _unsupported("Local classes", stmt.name.line)

        layout = self._classes[stmt.name.lexeme]
        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, 64)],
        )
        descriptor = self.builder.bitcast(raw, _CLASS_DESC.as_pointer())

        super_ptr: Any = llvm_ir.null_pointer()
        if layout.super_name is not None:
            super_ptr = self.builder.load(
                self._globals[layout.super_name].storage
            )

        vtable_raw: Any = llvm_ir.null_pointer()
        vtable: Any = llvm_ir.null_pointer()
        if layout.vtable_size:
            vtable_raw = self.builder.call(
                self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
                [llvm_ir.constant(_INT, 8 * layout.vtable_size)],
            )
            vtable = self.builder.bitcast(vtable_raw, _I8_PTR.as_pointer())
            if layout.super_layout is not None:
                base_desc = self.builder.bitcast(
                    super_ptr, _CLASS_DESC.as_pointer()
                )
                base_vtable = self.builder.bitcast(
                    self.builder.load(
                        self.builder.gep(
                            base_desc,
                            [
                                llvm_ir.constant(_I32, 0),
                                llvm_ir.constant(_I32, 3),
                            ],
                        )
                    ),
                    _I8_PTR.as_pointer(),
                )
                for slot_index in range(layout.super_layout.vtable_size):
                    slot = self.builder.gep(
                        vtable, [llvm_ir.constant(_I32, slot_index)]
                    )
                    self.builder.store(
                        self.builder.load(
                            self.builder.gep(
                                base_vtable,
                                [llvm_ir.constant(_I32, slot_index)],
                            )
                        ),
                        slot,
                    )

            for method in layout.methods:
                closure = self._make_raw_closure(
                    method.info.ir,
                    llvm_ir.null_pointer(),
                    f"<fn {method.name}>",
                    method.info.fn_sig,
                )
                slot = self.builder.gep(
                    vtable, [llvm_ir.constant(_I32, method.index)]
                )
                self.builder.store(closure.llvm, slot)

        init_closure: Any = llvm_ir.null_pointer()
        if layout.init is not None:
            init_closure = self._make_raw_closure(
                layout.init.ir,
                llvm_ir.null_pointer(),
                "<fn init>",
                layout.init.fn_sig,
            ).llvm
        elif layout.super_name is not None:
            base_desc = self.builder.bitcast(super_ptr, _CLASS_DESC.as_pointer())
            init_closure = self.builder.load(
                self.builder.gep(
                    base_desc,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 5)],
                )
            )

        effective = layout.effective_init()
        name_value = self._string_literal(layout.name)
        init_min = 0 if effective is None else effective.fn_sig.min_params
        init_max = 0 if effective is None else len(effective.fn_sig.params)
        values = [
            super_ptr,
            llvm_ir.constant(_INT, layout.id),
            name_value.llvm,
            vtable_raw,
            llvm_ir.constant(_INT, layout.field_count()),
            init_closure,
            llvm_ir.constant(_INT, init_min),
            llvm_ir.constant(_INT, init_max),
        ]
        for index, value in enumerate(values):
            slot = self.builder.gep(
                descriptor,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
            )
            self.builder.store(value, slot)

        binding = self._globals[layout.name]
        self.builder.store(raw, binding.storage)

        for method in layout.methods:
            assert method.node is not None
            self._emit_function(method.info, method.node, ())
        if layout.init is not None and layout.init_node is not None:
            self._emit_function(layout.init, layout.init_node, ())

        self._emit_ctor(layout)

    def _emit_ctor(self, layout: ClassLayout) -> None:
        ctor = layout.ctor
        assert ctor is not None
        assert layout.instance_type is not None

        saved_builder = self.builder
        saved_function = self._function_ir
        saved_return = self._return_type_desc
        saved_in_init = self._in_init
        saved_method_class = self._method_class
        saved_scopes = self._scopes
        saved_captures = self._captures

        self._function_ir = ctor
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._in_init = True
        self._method_class = None
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(ctor, "entry"))

        size = 16 + 8 * layout.field_count()
        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, size)],
        )
        instance = Value(ValueType.INSTANCE, raw, class_name=layout.name)
        struct_ = self.builder.bitcast(raw, layout.instance_type.as_pointer())
        descriptor = self.builder.load(self._globals[layout.name].storage)
        self.builder.store(
            descriptor,
            self.builder.gep(
                struct_,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            ),
        )
        self.builder.store(
            llvm_ir.constant(_INT, 0),
            self.builder.gep(
                struct_,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            ),
        )

        for field in layout.all_fields():
            if field.initializer is None:
                continue
            value = self._coerce(
                self._expr(field.initializer), field.ty, field.line
            )
            self._store_field(instance, field, value)

        effective = layout.effective_init()
        if effective is not None:
            init_args = [ctor.args[index] for index in range(len(ctor.args))]
            self.builder.call(
                effective.ir,
                [
                    llvm_ir.null_pointer(),
                    raw,
                    *init_args,
                ],
            )

        for field in layout.all_fields():
            bitmap = self.builder.load(self._bitmap_slot(instance, field.line))
            mask = llvm_ir.constant(_INT, 1 << field.index)
            present = self.builder.icmp_signed(
                "!=",
                self.builder.and_(bitmap, mask),
                llvm_ir.constant(_INT, 0),
            )
            ok = llvm_ir.append_block(self._function_ir, "init.ok")
            bad = llvm_ir.append_block(self._function_ir, "init.bad")
            self.builder.cbranch(present, ok, bad)

            self.builder = llvm_ir.builder(bad)
            self._poison(
                field.line, f"Field '{field.name}' must be initialized."
            )
            self.builder = llvm_ir.builder(ok)

        self.builder.ret(raw)
        self._seal_blocks(ctor)

        self.builder = saved_builder
        self._function_ir = saved_function
        self._return_type_desc = saved_return
        self._in_init = saved_in_init
        self._method_class = saved_method_class
        self._scopes = saved_scopes
        self._captures = saved_captures

    def _this(self, expr: This) -> Value:
        binding = self._find_binding("this")
        if binding is None:
            raise BackendError("'this' outside a method.", expr.keyword.line)
        return self._load_binding(binding)

    def _layout_for(self, value: Value, line: int) -> ClassLayout:
        layout = self._classes.get(value.class_name or "")
        if layout is None:
            raise _unsupported("Class instance", line)
        return layout

    def _instance_struct(self, value: Value, line: int) -> Any:
        layout = self._layout_for(value, line)
        assert layout.instance_type is not None
        return self.builder.bitcast(value.llvm, layout.instance_type.as_pointer())

    def _field_slot(self, value: Value, field: FieldLayout) -> Any:
        struct_ = self._instance_struct(value, field.line)
        return self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, field.index + 2)],
        )

    def _bitmap_slot(self, value: Value, line: int) -> Any:
        struct_ = self._instance_struct(value, line)
        return self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
        )

    def _check_bitmap(
        self, value: Value, field: FieldLayout, line: int, message: str
    ) -> None:
        bitmap = self.builder.load(self._bitmap_slot(value, line))
        mask = llvm_ir.constant(_INT, 1 << field.index)
        present = self.builder.icmp_signed(
            "!=", self.builder.and_(bitmap, mask), llvm_ir.constant(_INT, 0)
        )
        ok = llvm_ir.append_block(self._function_ir, "field.ok")
        bad = llvm_ir.append_block(self._function_ir, "field.nil")
        self.builder.cbranch(present, ok, bad)

        self.builder = llvm_ir.builder(bad)
        self._poison(line, message)

        self.builder = llvm_ir.builder(ok)

    def _set_bitmap(self, value: Value, field: FieldLayout) -> None:
        slot = self._bitmap_slot(value, field.line)
        bitmap = self.builder.load(slot)
        mask = llvm_ir.constant(_INT, 1 << field.index)
        self.builder.store(self.builder.or_(bitmap, mask), slot)

    def _slot_to_value(self, slot: Any, desc: TypeDesc) -> Value:
        raw = self.builder.load(slot)
        match desc.ty:
            case ValueType.INT:
                return Value(ValueType.INT, raw)
            case ValueType.FLOAT:
                return Value(
                    ValueType.FLOAT, self.builder.bitcast(raw, _FLOAT)
                )
            case ValueType.BOOL:
                return Value(ValueType.BOOL, self.builder.trunc(raw, _BOOL))
            case ValueType.STRING:
                return Value(
                    ValueType.STRING,
                    self.builder.inttoptr(raw, _I8_PTR),
                    optional=desc.optional,
                )
            case ValueType.FUNCTION:
                return Value(
                    ValueType.FUNCTION,
                    self.builder.inttoptr(raw, _I8_PTR),
                    desc.fn,
                    desc.optional,
                )
            case ValueType.CLASS | ValueType.INSTANCE:
                return Value(
                    desc.ty,
                    self.builder.inttoptr(raw, _I8_PTR),
                    optional=desc.optional,
                    class_name=desc.class_name,
                )
            case ValueType.NIL:
                return Value(ValueType.NIL)
        raise _unsupported(f"Field type '{desc.ty.name}'", None)

    def _value_to_slot(self, value: Value) -> Any:
        match value.ty:
            case ValueType.INT:
                return value.llvm
            case ValueType.FLOAT:
                return self.builder.bitcast(value.llvm, _INT)
            case ValueType.BOOL:
                return self.builder.zext(value.llvm, _INT)
            case ValueType.STRING | ValueType.FUNCTION | ValueType.CLASS | ValueType.INSTANCE:
                return self.builder.ptrtoint(value.llvm, _INT)
            case ValueType.NIL:
                return llvm_ir.constant(_INT, 0)
        raise _unsupported(f"Field value '{value.ty.name}'", None)

    def _load_field(
        self, instance: Value, field: FieldLayout, line: int
    ) -> Value:
        self._check_bitmap(
            instance,
            field,
            line,
            f"Undefined property '{field.name}'.",
        )
        return self._slot_to_value(self._field_slot(instance, field), field.ty)

    def _store_field(self, instance: Value, field: FieldLayout, value: Value) -> None:
        self.builder.store(
            self._value_to_slot(value), self._field_slot(instance, field)
        )
        self._set_bitmap(instance, field)

    def _make_raw_closure(
        self,
        fnptr: Any,
        env: Any,
        display: str,
        sig: FnSig,
    ) -> Value:
        raw = self.builder.call(
            self._function("lox_alloc_closure", _I8_PTR, []), []
        )
        closure = self.builder.bitcast(raw, _CLOSURE.as_pointer())
        self.builder.store(
            self.builder.bitcast(fnptr, _I8_PTR),
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            ),
        )
        self.builder.store(
            env,
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            ),
        )
        self.builder.store(
            self._display_pointer(display),
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 2)],
            ),
        )
        return Value(ValueType.FUNCTION, raw, sig)

    def _method_thunk(self, layout: ClassLayout, method: MethodLayout) -> Any:
        if method.thunk is not None:
            return method.thunk

        sig = method.info.fn_sig
        result = (
            _VOID
            if sig.ret.ty is ValueType.NIL
            else self._storage_llvm_type(sig.ret)
        )
        thunk = llvm_ir.declare(
            self.module,
            f"lox.bound.{layout.name}.{method.name}",
            result,
            [_I8_PTR, *[self._storage_llvm_type(param) for param in sig.params]],
        )

        saved_builder = self.builder
        saved_function = self._function_ir
        saved_return = self._return_type_desc
        saved_in_init = self._in_init
        saved_scopes = self._scopes
        saved_captures = self._captures

        self._function_ir = thunk
        self._return_type_desc = sig.ret
        self._in_init = False
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(thunk, "entry"))

        bound_type = llvm_ir.literal_struct([_I8_PTR, _I8_PTR])
        bound = self.builder.bitcast(thunk.args[0], bound_type.as_pointer())
        closure_ptr = self.builder.load(
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            )
        )
        this_ptr = self.builder.load(
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            )
        )
        closure = self.builder.bitcast(closure_ptr, _CLOSURE.as_pointer())
        fnptr = self.builder.load(
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            )
        )
        method_env = self.builder.load(
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            )
        )
        function_type = llvm_ir.function_pointer(
            result,
            [
                _I8_PTR,
                _I8_PTR,
                *[self._storage_llvm_type(param) for param in sig.params],
            ],
        )
        args = [thunk.args[index + 1] for index in range(len(sig.params))]
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [method_env, this_ptr, *args],
        )
        if sig.ret.ty is ValueType.NIL:
            self.builder.ret_void()
        else:
            self.builder.ret(call)
        self._seal_blocks(thunk)
        method.thunk = thunk

        self.builder = saved_builder
        self._function_ir = saved_function
        self._return_type_desc = saved_return
        self._in_init = saved_in_init
        self._scopes = saved_scopes
        self._captures = saved_captures
        return thunk

    def _bind_method_closure(
        self,
        instance: Value,
        layout: ClassLayout,
        method: MethodLayout,
        method_closure: Any,
    ) -> Value:
        thunk = self._method_thunk(layout, method)
        raw_env = self.builder.call(
            self._function("lox_alloc_env", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, 2)],
        )
        bound_type = llvm_ir.literal_struct([_I8_PTR, _I8_PTR])
        bound = self.builder.bitcast(raw_env, bound_type.as_pointer())
        self.builder.store(
            method_closure,
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            ),
        )
        self.builder.store(
            instance.llvm,
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            ),
        )
        return self._make_raw_closure(
            thunk, raw_env, f"<fn {method.name}>", method.info.fn_sig
        )

    def _bound_method(
        self, instance: Value, layout: ClassLayout, method: MethodLayout
    ) -> Value:
        struct_ = self._instance_struct(instance, 0)
        descriptor_slot = self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
        )
        descriptor = self.builder.load(descriptor_slot)
        desc_struct = self.builder.bitcast(descriptor, _CLASS_DESC.as_pointer())
        vtable_slot = self.builder.gep(
            desc_struct,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 3)],
        )
        vtable = self.builder.bitcast(
            self.builder.load(vtable_slot), _I8_PTR.as_pointer()
        )
        method_slot = self.builder.gep(
            vtable, [llvm_ir.constant(_I32, method.index)]
        )
        method_closure = self.builder.load(method_slot)
        return self._bind_method_closure(
            instance, layout, method, method_closure
        )

    def _this_value(self, line: int) -> Value:
        binding = self._find_binding("this")
        if binding is None:
            raise BackendError("'this' outside a method.", line)
        return self._load_binding(binding)

    def _super_method(self, expr: Super) -> Value:
        if self._method_class is None:
            raise BackendError("'super' outside a method.", expr.keyword.line)
        layout = self._classes[self._method_class]
        base = layout.super_layout
        if base is None:
            raise BackendError("'super' without a superclass.", expr.keyword.line)

        instance = self._this_value(expr.keyword.line)
        name = expr.method.lexeme
        descriptor = self.builder.load(self._globals[base.name].storage)
        desc_struct = self.builder.bitcast(descriptor, _CLASS_DESC.as_pointer())

        if name == "init":
            method = base.init_method
            if method is None:
                raise BackendError("Superclass has no initializer.", expr.keyword.line)
            closure = self.builder.load(
                self.builder.gep(
                    desc_struct,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 5)],
                )
            )
        else:
            method = base.method(name)
            if method is None:
                raise BackendError(
                    f"Undefined property '{name}'.", expr.method.line
                )
            vtable = self.builder.bitcast(
                self.builder.load(
                    self.builder.gep(
                        desc_struct,
                        [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 3)],
                    )
                ),
                _I8_PTR.as_pointer(),
            )
            closure = self.builder.load(
                self.builder.gep(
                    vtable, [llvm_ir.constant(_I32, method.index)]
                )
            )

        return self._bind_method_closure(instance, base, method, closure)

    def _get(self, expr: Get) -> Value:
        obj = self._expr(expr.object)
        if expr.optional and (obj.optional or obj.ty is ValueType.NIL):
            raise _unsupported("Optional receiver access", expr.name.line)
        if obj.ty is not ValueType.INSTANCE:
            self._poison(expr.name.line, "Only instances have properties.")
            return self._zero(ValueType.INT)

        layout = self._layout_for(obj, expr.name.line)
        field = layout.field(expr.name.lexeme)
        if field is not None:
            return self._load_field(obj, field, expr.name.line)
        method = layout.method(expr.name.lexeme)
        if method is not None:
            return self._bound_method(obj, layout, method)

        self._poison(
            expr.name.line, f"Undefined property '{expr.name.lexeme}'."
        )
        return self._zero(ValueType.INT)

    def _set(self, expr: Set) -> Value:
        obj = self._expr(expr.object)
        value = self._expr(expr.value)
        if obj.ty is not ValueType.INSTANCE:
            self._poison(expr.name.line, "Only instances have fields.")
            return value

        layout = self._layout_for(obj, expr.name.line)
        field = layout.field(expr.name.lexeme)
        if field is None:
            self._poison(expr.name.line, f"Undefined field '{expr.name.lexeme}'.")
            return value

        value = self._coerce(value, field.ty, expr.name.line)

        if not field.mutable:
            if not self._in_init:
                self._poison(
                    expr.name.line,
                    f"Can't assign to immutable field '{field.name}'.",
                )
                return value
            bitmap = self.builder.load(self._bitmap_slot(obj, field.line))
            mask = llvm_ir.constant(_INT, 1 << field.index)
            already = self.builder.icmp_signed(
                "!=",
                self.builder.and_(bitmap, mask),
                llvm_ir.constant(_INT, 0),
            )
            fresh = llvm_ir.append_block(self._function_ir, "val.fresh")
            used = llvm_ir.append_block(self._function_ir, "val.used")
            end = llvm_ir.append_block(self._function_ir, "val.end")
            self.builder.cbranch(already, used, fresh)

            self.builder = llvm_ir.builder(used)
            self._poison(
                expr.name.line,
                f"Can't assign to immutable field '{field.name}'.",
            )
            self.builder = llvm_ir.builder(fresh)
            self._store_field(obj, field, value)
            self.builder.branch(end)

            self.builder = llvm_ir.builder(end)
            return value

        self._store_field(obj, field, value)
        return value

    # --- variáveis ---

    def _var(self, stmt: Var) -> None:
        value: Value
        if stmt.initializer is None:
            if stmt.type_annotation is None:
                raise BackendError(
                    "Uninitialized variables need a type annotation "
                    "for the backend.",
                    stmt.name.line,
                )
            declared = self._type_desc(stmt.type_annotation, stmt.name.line)
            if not declared.optional:
                raise BackendError(
                    "Uninitialized variables of non-optional type are not "
                    "supported by the backend yet.",
                    stmt.name.line,
                )
            value = self._zero_desc(declared)
        else:
            value = self._expr(stmt.initializer)
            if stmt.type_annotation is not None:
                annotated = self._type_desc(stmt.type_annotation, stmt.name.line)
                if annotated.optional:
                    if value.ty is ValueType.NIL:
                        declared = annotated
                        value = self._zero_desc(annotated)
                    elif value.optional:
                        if not TypeDesc(value.ty, value.sig).same_as(
                            TypeDesc(annotated.ty, annotated.fn)
                        ):
                            raise BackendError(
                                f"Can't initialize {annotated.ty.name}? with "
                                f"{value.ty.name}?.",
                                stmt.name.line,
                            )
                        declared = value.desc
                    else:
                        # Como no L2, o tipo do slot é o do valor em runtime:
                        # `var b: Float? = 2` guarda `Int?` e imprime `2`.
                        declared = TypeDesc(value.ty, value.sig, True)
                        value = self._some(declared, value)
                elif value.optional or value.ty is ValueType.NIL:
                    declared = annotated
                    value = self._coerce(value, annotated, stmt.name.line)
                else:
                    # Anotação não converte em runtime (L2): `val f: Float = 2`
                    # guarda `Int` e imprime `2`.
                    declared = value.desc
            else:
                if value.ty is ValueType.NIL:
                    raise BackendError(
                        "Variables of type Nil are not supported by the backend yet.",
                        stmt.name.line,
                    )
                declared = value.desc

        if self._function_ir is self.main and len(self._scopes) == 1:
            existing = self._globals.get(stmt.name.lexeme)
            if existing is not None:
                # Redeclaração de global (`var x = 1; var x = 2;`): o interpretador
                # mantém um único binding e sobrescreve o valor; reusar o slot é o
                # que preserva a leitura dinâmica em funções já compiladas.
                if not existing.desc.same_as(declared):
                    raise BackendError(
                        f"Global '{stmt.name.lexeme}' was already declared as "
                        f"{existing.desc.ty.name}; redeclaring it as "
                        f"{declared.ty.name} is not supported by the backend yet.",
                        stmt.name.line,
                    )
                # `var f = ...` depois de `fn f` deixa de ser uma chamada direta.
                binding = Binding(
                    existing.storage,
                    declared.ty,
                    declared.fn,
                    declared.optional,
                    class_name=declared.class_name,
                )
                self._globals[stmt.name.lexeme] = binding
                self.builder.store(value.llvm, binding.storage)
                return

            name = f"g.{stmt.name.lexeme}"
            global_ = llvm_ir.global_variable(
                self.module, name, self._storage_llvm_type(declared)
            )
            binding = Binding(
                global_,
                declared.ty,
                declared.fn,
                declared.optional,
                class_name=declared.class_name,
            )
            self._globals[stmt.name.lexeme] = binding
            self.builder.store(value.llvm, global_)
            return

        if self._analysis.is_captured(stmt):
            cell = self._alloc_cell()
            cell_pointer = self._cell_pointer(cell, declared)
            self.builder.store(value.llvm, cell_pointer)
            self._scopes[-1][stmt.name.lexeme] = Binding(
                cell,
                declared.ty,
                declared.fn,
                declared.optional,
                cell=True,
                class_name=declared.class_name,
            )
            return

        slot = self.builder.alloca(
            self._storage_llvm_type(declared), name=stmt.name.lexeme
        )
        self.builder.store(value.llvm, slot)
        self._scopes[-1][stmt.name.lexeme] = Binding(
            slot,
            declared.ty,
            declared.fn,
            declared.optional,
            class_name=declared.class_name,
        )

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
        if value.ty in (ValueType.FUNCTION, ValueType.CLASS):
            return self._guard_closure(value, expr.name.lexeme, expr.name.line)
        return value

    def _assign(self, expr: Assign) -> Value:
        value = self._expr(expr.value)
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(expr.name.line, f"Undefined variable '{expr.name.lexeme}'.")
            return value

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

        value = self._coerce(value, binding.desc, expr.name.line)
        self._store_binding(binding, value)

        if binding.function is not None:
            # O binding agora aponta para outra função: chamadas seguintes são
            # indiretas (o corpo pode ter mudado).
            replacement = Binding(
                binding.storage,
                value.ty,
                value.sig,
                value.optional,
                binding.cell,
                class_name=value.class_name,
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
        if value.optional:
            return self._to_string_optional(value)

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
            case ValueType.CLASS | ValueType.INSTANCE:
                text = (
                    value.class_name or "?"
                    if value.ty is ValueType.CLASS
                    else f"{value.class_name or '?'} instance"
                )
                return self._string_literal(text)
            case ValueType.NIL:
                function = self._function("lox_str_nil", _I8_PTR, [])
                return Value(ValueType.STRING, self.builder.call(function, []))

    def _to_string_optional(self, value: Value) -> Value:
        tag = self._optional_tag(value)
        some = llvm_ir.append_block(self._function_ir, "opt.str.some")
        nothing = llvm_ir.append_block(self._function_ir, "opt.str.nil")
        end = llvm_ir.append_block(self._function_ir, "opt.str.end")
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(nothing)
        nothing_value = self.builder.call(
            self._function("lox_str_nil", _I8_PTR, []), []
        )
        nothing_end = self.builder.block
        self.builder.branch(end)

        self.builder = llvm_ir.builder(some)
        some_value = self._to_string(self._optional_payload(value)).llvm
        some_end = self.builder.block
        self.builder.branch(end)

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(_I8_PTR, "opt.str")
        merged.add_incoming(nothing_value, nothing_end)
        merged.add_incoming(some_value, some_end)
        return Value(ValueType.STRING, merged)

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

    def _optional_equality(
        self, left: Value, right: Value, operator: TokenType
    ) -> Value:
        equal = operator is TokenType.EQUAL_EQUAL
        true = llvm_ir.constant(_BOOL, 1)
        false = llvm_ir.constant(_BOOL, 0)

        if left.ty is ValueType.NIL or right.ty is ValueType.NIL:
            if left.ty is ValueType.NIL and right.ty is ValueType.NIL:
                return Value(ValueType.BOOL, true if equal else false)
            optional = right if left.ty is ValueType.NIL else left
            if optional.optional:
                tag = self._optional_tag(optional)
                is_nil = self.builder.icmp_signed(
                    "==", tag, llvm_ir.constant(_BOOL, 0)
                )
                return Value(
                    ValueType.BOOL,
                    is_nil if equal else self.builder.not_(is_nil),
                )
            return Value(ValueType.BOOL, false if equal else true)

        if left.optional and right.optional:
            if not left.desc.same_as(right.desc) and not (
                left.ty in NUMERIC and right.ty in NUMERIC
            ):
                return Value(ValueType.BOOL, false if equal else true)

            left_tag = self._optional_tag(left)
            right_tag = self._optional_tag(right)
            both_nil = self.builder.and_(
                self.builder.not_(left_tag), self.builder.not_(right_tag)
            )
            both_some = self.builder.and_(left_tag, right_tag)
            payload_equal = self._plain_equality(
                self._optional_payload(left),
                self._optional_payload(right),
                TokenType.EQUAL_EQUAL,
            ).llvm
            result = self.builder.or_(
                both_nil, self.builder.and_(both_some, payload_equal)
            )
            return Value(
                ValueType.BOOL,
                result if equal else self.builder.not_(result),
            )

        if left.optional or right.optional:
            optional = left if left.optional else right
            other = right if left.optional else left
            inner = TypeDesc(
                optional.ty, optional.sig, False, optional.class_name
            )
            if not inner.same_as(other.desc) and not (
                optional.ty in NUMERIC and other.ty in NUMERIC
            ):
                return Value(ValueType.BOOL, false if equal else true)

            tag = self._optional_tag(optional)
            payload = self._optional_payload(optional)
            if left.optional:
                payload_equal = self._plain_equality(
                    payload, other, TokenType.EQUAL_EQUAL
                ).llvm
            else:
                payload_equal = self._plain_equality(
                    other, payload, TokenType.EQUAL_EQUAL
                ).llvm

            result = self.builder.and_(tag, payload_equal)
            return Value(
                ValueType.BOOL,
                result if equal else self.builder.not_(result),
            )

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

    def _call(self, expr: Call) -> Value:
        if isinstance(expr.callee, Variable):
            name = expr.callee.name.lexeme
            if name == "len":
                return self._len(expr)
            if name == "str":
                return self._str(expr)
            if name == "repr":
                return self._repr(expr)

        if isinstance(expr.callee, Variable):
            depth = self.depths.get(expr.callee)
            if depth is not None or expr.callee.name.lexeme in self._globals:
                early = self._lookup(
                    expr.callee, expr.callee.name.lexeme, expr.callee.name.line
                )
                if early.ty is ValueType.CLASS:
                    return self._call_class(early, expr)

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
            return self._zero_desc(sig.ret)

        if info is not None:
            for index in range(count, maximum):
                default = info.params[index].default
                assert default is not None
                arguments.append(self._expr(default))

        arguments = [
            self._coerce(argument, expected, expr.paren.line)
            for argument, expected in zip(arguments, sig.params, strict=True)
        ]

        fnptr = self._closure_field(callee, 0)
        env = self._closure_field(callee, 1)
        function_type = llvm_ir.function_pointer(
            _VOID
            if sig.ret.ty is ValueType.NIL
            else self._storage_llvm_type(sig.ret),
            [_I8_PTR, *[self._storage_llvm_type(param) for param in sig.params]],
        )
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [env, *[argument.llvm for argument in arguments]],
        )
        if sig.ret.ty is ValueType.NIL:
            return Value(ValueType.NIL)
        return Value(
            sig.ret.ty,
            call,
            sig.ret.fn,
            sig.ret.optional,
            sig.ret.class_name,
        )

    def _call_class(self, binding: Binding, expr: Call) -> Value:
        name = binding.class_name or ""
        layout = self._classes.get(name)
        if layout is None:
            raise _unsupported("Class construction", expr.paren.line)

        class_ptr = self._load_binding(binding)
        class_ptr = self._guard_closure(class_ptr, name, expr.paren.line)

        arguments = [self._expr(argument) for argument in expr.arguments]
        init = layout.effective_init()
        minimum = 0 if init is None else init.fn_sig.min_params
        maximum = 0 if init is None else len(init.fn_sig.params)
        count = len(arguments)
        if not minimum <= count <= maximum:
            self._poison(
                expr.paren.line, self._arity_message(minimum, maximum, count)
            )
            return self._zero(ValueType.INSTANCE)

        if init is not None:
            for index in range(count, maximum):
                default = init.params[index].default
                assert default is not None
                arguments.append(self._expr(default))
            arguments = [
                self._coerce(argument, expected, expr.paren.line)
                for argument, expected in zip(
                    arguments, init.fn_sig.params, strict=True
                )
            ]

        call = self.builder.call(
            layout.ctor, [argument.llvm for argument in arguments]
        )
        return Value(ValueType.INSTANCE, call, class_name=name)

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
            right = self._coerce(
                self._expr(expr.right),
                inner,
                expr.operator.line,
            )
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
