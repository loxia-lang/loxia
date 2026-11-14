"""Contexto compartilhado pelos módulos do lowering.

O lowering é dividido por responsabilidade: funções, variáveis, tipos/optionais,
classes, chamadas e strings. Cada mixin acessa o mesmo `Lowerer`; este módulo declara
os atributos do contexto e deixa a resolução de métodos cruzados para o MRO/`__getattr__`.
Nenhuma ABI é definida aqui: as representações ficam em `lower_model.py` e seguem o
ADR-0048.
"""

from __future__ import annotations

from typing import Any

from src.backend.captures import CaptureAnalysis
from src.backend.lower_model import (
    Binding,
    ClassLayout,
    FunctionInfo,
    MethodLayout,
    TypeDesc,
    Value,
    ValueType,
)
from src.frontend.expr import Call, Expr, Get, Range
from src.frontend.stmt import Function
from src.frontend.token_type import TokenType
from src.frontend.ty import Ty


class LoweringBase:
    """Atributos e escape hatch para chamadas entre os mixins do lowering."""

    module: Any
    types: dict[Expr, Ty]
    depths: dict[Expr, int]
    main: Any
    builder: Any
    _runtime: Any
    _messages: Any
    _displays: Any
    _poison_count: int
    _string_count: int
    _function_counter: int
    _scopes: list[dict[str, Binding]]
    _captures: dict[str, Binding]
    _globals: dict[str, Binding]
    _top_level: dict[int, FunctionInfo]
    _class_names: set[str]
    _classes: dict[str, ClassLayout]
    _local_class_counter: int
    _function_ir: Any
    _return_type_desc: TypeDesc
    _in_init: bool
    _method_class: str | None
    _analysis: CaptureAnalysis
    _type_subst: dict[str, Ty]
    _enum_layouts: dict[str, Any]
    _finally_stack: list[list[Any]]
    _enum_names: dict[str, Any]
    _list_expected_element: Ty | None
    _map_expected_key: Ty | None
    _map_expected_value: Ty | None
    generic_instances: Any
    generic_classes: Any
    generic_class_sites: Any
    _generic_fns: dict[str, Any]
    _generic_fn_cache: dict[tuple[str, tuple[str, ...]], FunctionInfo]
    _generic_class_layouts: dict[str, ClassLayout]
    _generic_class_by_source: Any
    _generic_class_nodes: Any
    _generic_descriptors: Any

    # Métodos compartilhados entre mixins. O MRO resolve para a implementação real.
    def _expr(self, expr: Expr) -> Value:
        raise NotImplementedError

    def _function_info(
        self,
        stmt: Function,
        *,
        llvm_name: str | None = None,
        this_class: str | None = None,
        is_init: bool = False,
        allow_generic: bool = False,
    ) -> FunctionInfo:
        raise NotImplementedError

    def _emit_function(
        self, info: FunctionInfo, stmt: Function, captures: Any
    ) -> None:
        raise NotImplementedError

    def _arity_message(self, minimum: int, maximum: int, count: int) -> str:
        raise NotImplementedError

    def _call_generic(self, stmt: Function, expr: Call) -> Value:
        raise NotImplementedError

    def _range_expr(self, expr: Range) -> Value:
        raise NotImplementedError

    def _range_call(self, expr: Call) -> Value:
        raise NotImplementedError

    def _call_generic_class(self, name: str, expr: Call) -> Value:
        raise NotImplementedError

    def _call_list_method(self, expr: Call, obj: Value) -> Value:
        raise NotImplementedError

    def _list_len(self, value: Value) -> Value:
        raise NotImplementedError

    def _call_map_method(self, expr: Call, obj: Value) -> Value:
        raise NotImplementedError

    def _map_len(self, value: Value) -> Value:
        raise NotImplementedError

    def _map_equal(self, left: Value, right: Value) -> Value:
        raise NotImplementedError

    def _unbox_value(self, raw: Any, desc: TypeDesc, line: int | None) -> Value:
        raise NotImplementedError

    def _tuple_get(self, expr: Any, obj: Value) -> Value:
        raise NotImplementedError

    def _tuple_len(self, value: Value) -> Value:
        raise NotImplementedError

    def _chars(self, expr: Call) -> Value:
        raise NotImplementedError

    def _enum_construct(self, expr: Call) -> Value:
        raise NotImplementedError

    def _enum_get(self, expr: Get) -> Value:
        raise NotImplementedError

    def _call_generic_lambda(self, callee: Value, expr: Call) -> Value:
        raise NotImplementedError

    def _build_closure(self, info: Any, captures: Any, display: str) -> Value:
        raise NotImplementedError

    def _unbox_any(self, value: Value, desc: TypeDesc, line: int | None) -> Value:
        raise NotImplementedError

    def _math_call(self, expr: Call) -> Value:
        raise NotImplementedError

    def _parse_call(self, expr: Call, desc: TypeDesc) -> Value:
        raise NotImplementedError

    def _instantiate_class(
        self, name: str, args: tuple[Ty, ...], line: int | None
    ) -> TypeDesc:
        raise NotImplementedError

    def _subst_ty(self, ty: Ty) -> Ty:
        raise NotImplementedError

    def _class_display(self, class_name: str) -> str:
        raise NotImplementedError

    def _type_desc(self, ty: Ty, line: int | None) -> TypeDesc:
        raise NotImplementedError

    def _storage_llvm_type(self, desc: TypeDesc) -> Any:
        raise NotImplementedError

    def _zero_desc(self, desc: TypeDesc) -> Value:
        raise NotImplementedError

    def _zero(self, ty: ValueType) -> Value:
        raise NotImplementedError

    def _plain_equality(
        self, left: Value, right: Value, operator: TokenType
    ) -> Value:
        raise NotImplementedError

    def _find_binding(self, name: str) -> Binding | None:
        raise NotImplementedError

    def _bound_method(
        self, instance: Value, layout: ClassLayout, method: MethodLayout
    ) -> Value:
        raise NotImplementedError

    def _len(self, expr: Call) -> Value:
        raise NotImplementedError

    def _str(self, expr: Call) -> Value:
        raise NotImplementedError

    def _repr(self, expr: Call) -> Value:
        raise NotImplementedError

    def _load_binding(self, binding: Binding) -> Value:
        raise NotImplementedError

    def _some(self, desc: TypeDesc, value: Value) -> Value:
        raise NotImplementedError

    def _box_value(self, value: Value, line: int | None) -> Value:
        raise NotImplementedError

    def _unwrap(self, value: Value, line: int, message: str) -> Value:
        raise NotImplementedError

    def _coerce(self, value: Value, expected: TypeDesc, line: int | None) -> Value:
        raise NotImplementedError

    def _poison(self, line: int, message: str) -> None:
        raise NotImplementedError

    def __getattr__(self, name: str) -> Any:
        # Demais métodos definidos em outro mixin são resolvidos pelo MRO em runtime.
        raise AttributeError(name)
