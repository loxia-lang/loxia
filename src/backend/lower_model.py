"""Modelo de tipos, valores e layouts do lowering (sem emissão de IR).

Este módulo é a fronteira estável entre o lowering e o emissor: as ABI/representações
documentadas no ADR-0048 vivem aqui, longe das decisões de fluxo de código.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from src.backend import llvm_ir
from src.frontend.expr import Expr
from src.frontend.stmt import Function, Param
from src.frontend.token_type import TokenType

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
_ANY = llvm_ir.literal_struct([_INT, _INT])
ANY_TAG_NIL = 0
ANY_TAG_INT = 1
ANY_TAG_FLOAT = 2
ANY_TAG_BOOL = 3
ANY_TAG_STRING = 4
ANY_TAG_CLASS = 5
ANY_TAG_INSTANCE = 6
ANY_TAG_FUNCTION = 7
ANY_TAG_RANGE = 8
ANY_TAG_LIST = 9
ANY_TAG_MAP = 10
ANY_TAG_TUPLE = 11
ANY_TAG_ENUM = 12

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
    RANGE = auto()
    LIST = auto()
    MAP = auto()
    TUPLE = auto()
    ENUM = auto()
    ANY = auto()


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
    layout_key: str | None = None

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
    type_subst: dict[str, Any] | None = None


@dataclass(frozen=True)
class Value:
    """Valor no IR. `NIL` não tem representação em LLVM: `llvm` fica `None`."""

    ty: ValueType
    llvm: Any = None
    sig: FnSig | None = None
    optional: bool = False
    class_name: str | None = None
    function: FunctionInfo | None = None

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
    local: bool = False
    ir_name: str | None = None
    display_name: str | None = None
    generic: bool = False
    init_method: MethodLayout | None = None
    vtable_size: int = 0
    ctor: Any = None
    instance_type: Any = None

    @property
    def display(self) -> str:
        return self.display_name or self.name

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

    def field_count(self) -> int:
        base = 0 if self.super_layout is None else self.super_layout.field_count()
        return base + len(self.fields)

    def all_fields(self) -> list[FieldLayout]:
        base = [] if self.super_layout is None else self.super_layout.all_fields()
        return [*base, *self.fields]


def _unsupported(what: str, line: int | None) -> BackendError:
    return BackendError(f"{what} is not supported by the backend yet.", line)

