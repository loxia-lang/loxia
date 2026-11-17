"""Teste dinâmico de tipo para a expressão `is`.

Os tipos são apagados no runtime; este módulo é a única ponte entre um `Ty` estático e um
valor concreto. Ele existe para `is` e não deve ser usado pelo checker para inferência.
"""

from __future__ import annotations

from collections.abc import Callable

from loxia_core.execution import numeric
from loxia_core.execution.lox_class import LoxClass
from loxia_core.execution.lox_enum import LoxEnumValue
from loxia_core.execution.lox_instance import LoxInstance
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.lox_map import LoxMap
from loxia_core.execution.lox_range import LoxRange
from loxia_core.execution.lox_tuple import LoxTuple
from loxia_core.frontend.ty import (
    ANY,
    BOOL,
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
    ListTy,
    MapTy,
    NativeFnTy,
    TupleTy,
    Ty,
    UnionTy,
)


def matches_type(
    value: object,
    ty: Ty,
    class_lookup: Callable[[str], LoxClass | None] | None = None,
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
    if isinstance(ty, UnionTy):
        return any(matches_type(value, member, class_lookup) for member in ty.members)
    if isinstance(ty, (FnTy, NativeFnTy)):
        return False

    return False
