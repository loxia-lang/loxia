# SPDX-License-Identifier: MIT OR Apache-2.0
"""Teste dinâmico de tipo para a expressão `is`.

Os tipos são apagados no runtime; este módulo é a única ponte entre um `Ty` estático e um
valor concreto. Ele existe para `is` e não deve ser usado pelo checker para inferência.
"""

from __future__ import annotations

from collections.abc import Callable

from loxia_core.execution import numeric
from loxia_core.execution.lox_class import LoxClass
from loxia_core.execution.lox_enum import LoxEnumValue
from loxia_core.execution.lox_exception import LoxExceptionValue
from loxia_core.execution.lox_instance import LoxInstance
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.lox_map import LoxMap
from loxia_core.execution.lox_range import LoxRange
from loxia_core.execution.lox_tuple import LoxTuple
from loxia_core.frontend.ty import (
    ANY,
    BOOL,
    BYTES,
    ERROR,
    FLOAT,
    INT,
    NEVER,
    NIL,
    RANGE,
    STRING,
    ClassObjectTy,
    ClassTy,
    EnumTy,
    FnTy,
    InterfaceTy,
    ListTy,
    MapTy,
    NativeFnTy,
    TupleTy,
    Ty,
    UnionTy,
)


def _rep_code(ty: Ty) -> int:
    """Representação de máquina (ADR-0147); espelha o runtime C."""
    if ty is ANY:
        return 0
    if ty is INT:
        return 1
    if ty is FLOAT:
        return 2
    if ty is BOOL:
        return 3
    if ty is NIL:
        return 4
    pointer_types = (ListTy, MapTy, TupleTy, ClassTy, InterfaceTy, EnumTy, FnTy)
    if isinstance(ty, pointer_types) or ty in (STRING, BYTES, RANGE):
        return 5
    if isinstance(ty, UnionTy):
        if len(ty.members) == 2:
            nil = [member for member in ty.members if member is NIL]
            other = [member for member in ty.members if member is not NIL]
            if nil and len(other) == 1:
                payload = other[0]
                if payload in (INT, FLOAT, BOOL):
                    return 100 + _rep_code(payload)
                if isinstance(payload, pointer_types) or payload in (STRING, BYTES, RANGE):
                    return 5
        return 0
    return 0


def _fn_abi_compatible(target: FnTy, actual: FnTy) -> bool:
    if target.variadic != actual.variadic:
        return False
    count = len(target.params)
    if actual.variadic:
        if len(actual.params) != count:
            return False
    elif count != len(actual.params):
        # O alvo tem que passar todos os parâmetros do callee; defaults só são
        # preenchidos em chamada estática (o lowering não os inventa no dinâmico).
        return False
    for target_param, actual_param in zip(target.params, actual.params, strict=False):
        if not same_rep(target_param, actual_param):
            return False
    return same_rep(target.ret, actual.ret)


def same_rep(left: Ty, right: Ty) -> bool:
    if isinstance(left, FnTy) and isinstance(right, FnTy):
        return _fn_abi_compatible(left, right)
    return _rep_code(left) == _rep_code(right)


def matches_type(
    value: object,
    ty: Ty,
    class_lookup: Callable[[str], LoxClass | None] | None = None,
    fn_assignable: Callable[[FnTy, FnTy], bool] | None = None,
    rep_equal: Callable[[Ty, Ty], bool] | None = None,
) -> bool:
    """Devolve se `value` satisfaz `ty` em runtime.

    `List[T]`/`Map[K, V]` checam os elementos/chaves/valores recursivamente; listas vazias
    satisfazem qualquer elemento. Para `ClassTy`, `class_lookup` resolve o nome para o
    objeto de classe (identidade por objeto, ADR-0044); sem lookup, cai no nome. Tipos de
    função ainda não são suportados pelo checker em `is`, então aqui devolvem `False`.
    """
    if ty is ANY:
        return True
    if ty is NEVER or ty is ERROR:
        return False
    if isinstance(ty, FnTy):
        actual = getattr(value, "fn_type", None)
        return (
            isinstance(actual, FnTy)
            and fn_assignable is not None
            and rep_equal is not None
            and fn_assignable(ty, actual)
            and rep_equal(ty, actual)
        )
    if ty is NIL:
        return value is None
    if ty is BOOL:
        return isinstance(value, bool)
    if ty is INT:
        return numeric.is_int(value)
    if ty is FLOAT:
        return numeric.is_float(value)
    if ty is STRING:
        return isinstance(value, str)
    if ty is BYTES:
        return isinstance(value, bytes)
    if ty is RANGE:
        return isinstance(value, LoxRange)
    if isinstance(ty, ListTy):
        return isinstance(value, LoxList) and all(
            matches_type(element, ty.element, class_lookup) for element in value.elements
        )
    if isinstance(ty, MapTy):
        return isinstance(value, LoxMap) and all(
            matches_type(key, ty.key, class_lookup) and matches_type(item, ty.value, class_lookup)
            for key, item in value.items
        )
    if isinstance(ty, TupleTy):
        return (
            isinstance(value, LoxTuple)
            and len(value.items) == len(ty.items)
            and all(
                matches_type(item, item_ty, class_lookup)
                for item, item_ty in zip(value.items, ty.items, strict=True)
            )
        )
    if isinstance(ty, ClassTy):
        if isinstance(value, LoxExceptionValue):
            return value.is_instance_of(ty.name)
        if isinstance(value, LoxInstance):
            if class_lookup is not None:
                klass = class_lookup(ty.name)
                if klass is not None:
                    return value.is_instance_of_class(klass)
            return value.is_instance_of(ty.name)
        # `is Cor` chega aqui como ClassTy porque o parser não distingue enum de
        # classe; o valor desambigua no runtime.
        return isinstance(value, LoxEnumValue) and value.enum == ty.name
    if isinstance(ty, EnumTy):
        return isinstance(value, LoxEnumValue) and value.enum == ty.name
    if isinstance(ty, ClassObjectTy):
        return isinstance(value, LoxClass) and value.is_subclass_of(ty.name)
    if isinstance(ty, InterfaceTy):
        return isinstance(value, LoxInstance) and value.implements_interface(ty.name)
    if isinstance(ty, UnionTy):
        return any(matches_type(value, member, class_lookup) for member in ty.members)
    if isinstance(ty, (FnTy, NativeFnTy)):
        return False

    return False
