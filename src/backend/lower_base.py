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
from src.frontend.expr import Call, Expr
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

    # Métodos compartilhados entre mixins. O MRO resolve para a implementação real.
    def _expr(self, expr: Expr) -> Value:
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

    def _unwrap(self, value: Value, line: int, message: str) -> Value:
        raise NotImplementedError

    def _coerce(self, value: Value, expected: TypeDesc, line: int | None) -> Value:
        raise NotImplementedError

    def _poison(self, line: int, message: str) -> None:
        raise NotImplementedError

    def __getattr__(self, name: str) -> Any:
        # Demais métodos definidos em outro mixin são resolvidos pelo MRO em runtime.
        raise AttributeError(name)
