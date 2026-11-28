# SPDX-License-Identifier: MIT OR Apache-2.0
"""Modelo de tipos, valores e layouts do lowering (sem emissão de IR).

Este módulo é a fronteira estável entre o lowering e o emissor: as ABI/representações
documentadas no ADR-0048 vivem aqui, longe das decisões de fluxo de código.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.diagnostic import Span
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.ty import FnTy, Ty
from loxia_core.thir import (
    TExpr,
    TFunction,
)
from loxia_core.thir import (
    TParam as Param,
)

_INT = llvm_ir.int_type(64)
_BOOL = llvm_ir.int_type(1)
_I32 = llvm_ir.int_type(32)
_FLOAT = llvm_ir.float_type()
_VOID = llvm_ir.void_type()
_I8_PTR = llvm_ir.pointer_type()
_CLOSURE = llvm_ir.literal_struct([_I8_PTR, _I8_PTR, _I8_PTR, _INT, _INT, _I8_PTR])
_CLASS_DESC = llvm_ir.literal_struct(
    [_I8_PTR, _INT, _I8_PTR, _I8_PTR, _INT, _I8_PTR, _INT, _INT, _INT, _I8_PTR]
)
_INTERFACE_ENTRY = llvm_ir.literal_struct([_INT, _I8_PTR])
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
ANY_TAG_BYTES = 13

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

    INTERNAL_PREFIX = "internal lowering error: "

    def __init__(
        self,
        message: str,
        line: int | None = None,
        *,
        code: Code = Code.BACKEND_INTERNAL,
    ) -> None:
        if code is Code.BACKEND_INTERNAL and not message.startswith("internal "):
            message = f"{self.INTERNAL_PREFIX}{message}"
        super().__init__(message)
        self.message = message
        self.line = line
        self.code = code


class ValueType(Enum):
    INT = auto()
    FLOAT = auto()
    BOOL = auto()
    STRING = auto()
    BYTES = auto()
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
    """Assinatura de um valor de função, derivada do `FnTy` do checker.

    Em variádicos, o último item de `params` é a `List` do rest e
    `vararg_element` guarda o descritor do elemento.
    """

    params: tuple[TypeDesc, ...]
    ret: TypeDesc
    min_params: int
    variadic: bool = False
    vararg_element: TypeDesc | None = None


@dataclass(frozen=True)
class TypeDesc:
    """Tipo representável no backend; `fn` só existe para `ValueType.FUNCTION`."""

    ty: ValueType
    fn: FnSig | None = None
    optional: bool = False
    class_name: str | None = None
    interface_name: str | None = None

    def same_as(self, other: TypeDesc) -> bool:
        enum_name_ok = (
            self.ty is ValueType.ENUM
            and other.ty is ValueType.ENUM
            and (
                self.class_name is None
                or other.class_name is None
                or self.class_name == other.class_name
            )
        )
        return (
            self.ty is other.ty
            and self.fn == other.fn
            and self.optional == other.optional
            and (enum_name_ok or self.class_name == other.class_name)
            and self.interface_name == other.interface_name
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
    generic: Any = None
    generic_node: Any = None
    interface_name: str | None = None
    mutable: bool = True

    @property
    def desc(self) -> TypeDesc:
        return TypeDesc(
            self.ty,
            self.sig,
            self.optional,
            self.class_name,
            self.interface_name,
        )


@dataclass(frozen=True)
class FunctionInfo:
    """Assinatura já emitida: função LLVM e assinatura do checker."""

    ir: Any
    params: list[Param]
    fn_sig: FnSig
    this_class: str | None = None
    # Classe léxica para `super` em funções locais/lambdas: não implica ABI de `this`.
    method_class: str | None = None
    is_init: bool = False
    type_subst: dict[str, Any] | None = None
    this_interface: str | None = None
    # Stack trace (ADR-0089): nome exibível e posição da declaração (R1015).
    trace_name: str = ""
    decl_file: str = ""
    decl_line: int = 0
    decl_column: int = 1
    fn_ty: FnTy | None = None


@dataclass(frozen=True)
class Value:
    """Valor no IR. `NIL` não tem representação em LLVM: `llvm` fica `None`."""

    ty: ValueType
    llvm: Any = None
    sig: FnSig | None = None
    optional: bool = False
    class_name: str | None = None
    function: FunctionInfo | None = None
    generic: Any = None
    generic_node: Any = None
    interface_name: str | None = None
    # `True` quando o valor é um zero de recheio depois de um panic site: a
    # avaliação já emitiu o `Rxxxx` e o código é inalcançável. A coerção troca
    # esse lixo por um zero do tipo esperado em vez de estourar (I1/#244).
    error: bool = False

    @property
    def desc(self) -> TypeDesc:
        return TypeDesc(
            self.ty,
            self.sig,
            self.optional,
            self.class_name,
            self.interface_name,
        )


def merge_callable_metadata(left: Value, right: Value) -> tuple[Any, Any, Any]:
    """Metadados de chamada comuns aos dois ramos de um `phi`.

    Um ramo `nil` não tem metadados: o valor não-nulo é o único que pode ser
    chamado. Dois valores de função só compartilham metadados quando são a
    **mesma** função (ou a mesma lambda genérica); caso contrário o resultado
    fica sem `FunctionInfo` e a chamada indireta precisa recusar defaults.
    """
    if left.ty is ValueType.NIL:
        return (right.function, right.generic, right.generic_node)
    if right.ty is ValueType.NIL:
        return (left.function, left.generic, left.generic_node)
    if left.function is not None and left.function is right.function:
        return (left.function, None, None)
    if (
        left.generic is not None
        and left.generic is right.generic
        and left.generic_node is right.generic_node
    ):
        return (None, left.generic, left.generic_node)
    return (None, None, None)


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
    initializer: TExpr | None
    index: int
    line: int
    column: int = 0
    # Anotação declarada (não achatada em `TypeDesc`), para propagar `List[T]`/
    # `Map[K, V]` ao lowering de literais em campos.
    annotation: Ty | None = None
    # Offset absoluto em palavras de 8 bytes, já contando o header da instância
    # (`class` + bitmap). Um campo `Any` ocupa duas palavras (ADR-0145).
    slot: int = 0


def field_words(fields: list[FieldLayout]) -> int:
    """Palavras de 8 bytes ocupadas pelos campos: 2 para `Any`, 1 para o resto."""
    return sum(2 if field.ty.ty is ValueType.ANY else 1 for field in fields)


@dataclass
class MethodLayout:
    name: str
    info: FunctionInfo
    index: int
    node: TFunction | None = None
    thunk: Any = None


@dataclass
class ClassLayout:
    name: str
    id: int
    fields: list[FieldLayout]
    methods: list[MethodLayout]
    init: FunctionInfo | None
    init_node: TFunction | None = None
    super_name: str | None = None
    super_layout: ClassLayout | None = None
    local: bool = False
    ir_name: str | None = None
    display_name: str | None = None
    generic: bool = False
    init_method: MethodLayout | None = None
    vtable_size: int = 0
    interfaces: tuple[str, ...] = ()
    ctor: Any = None
    instance_type: Any = None
    # Declaração da classe: nome exibível nos frames e posição do R1015 no ctor.
    decl_token: Span | None = None
    # `Exception`/`RuntimeError`: ctor sintético de 1 argumento (`message`),
    # sem `init` no AST. Ver `_ctor_body`/`_call_class`.
    synthetic_exception: bool = False

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

    def word_count(self) -> int:
        """Palavras de payload (sem o header) dos campos, incluindo a base."""
        base = 0 if self.super_layout is None else self.super_layout.word_count()
        return base + field_words(self.fields)

    def all_fields(self) -> list[FieldLayout]:
        base = [] if self.super_layout is None else self.super_layout.all_fields()
        return [*base, *self.fields]

    def effective_interfaces(self) -> list[str]:
        """Interfaces próprias + herdadas, sem duplicata e da derivada para a base."""
        names = list(self.interfaces)
        if self.super_layout is not None:
            for name in self.super_layout.effective_interfaces():
                if name not in names:
                    names.append(name)
        return names


def _unsupported(what: str, line: int | None) -> BackendError:
    return BackendError(
        f"{what} is not supported by the backend yet.",
        line,
        code=Code.BACKEND_UNSUPPORTED,
    )
