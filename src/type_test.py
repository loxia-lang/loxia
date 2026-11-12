"""Teste dinâmico de tipo para a expressão `is`.

Os tipos são apagados no runtime; este módulo é a única ponte entre um `Ty` estático e um
valor concreto. Ele existe para `is` e não deve ser usado pelo checker para inferência.
"""

from __future__ import annotations

from src import numeric
from src.lox_class import LoxClass
from src.lox_instance import LoxInstance
from src.lox_list import LoxList
from src.lox_map import LoxMap
from src.lox_range import LoxRange
from src.ty import (
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
    FnTy,
    ListTy,
    MapTy,
    NativeFnTy,
    Ty,
    UnionTy,
)


def matches_type(value: object, ty: Ty) -> bool:
    """Devolve se `value` satisfaz `ty` em runtime.

    `List[T]`/`Map[K, V]` checam os elementos/chaves/valores recursivamente; listas vazias
    satisfazem qualquer elemento. Tipos de função ainda não são suportados pelo checker em
    `is`, então aqui devolvem `False`.
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
            matches_type(element, ty.element) for element in value.elements
        )
    if isinstance(ty, MapTy):
        return isinstance(value, LoxMap) and all(
            matches_type(key, ty.key) and matches_type(item, ty.value)
            for key, item in value.items
        )
    if isinstance(ty, ClassTy):
        return isinstance(value, LoxInstance) and value.is_instance_of(ty.name)
    if isinstance(ty, ClassObjectTy):
        return isinstance(value, LoxClass) and value.is_subclass_of(ty.name)
    if isinstance(ty, UnionTy):
        return any(matches_type(value, member) for member in ty.members)
    if isinstance(ty, (FnTy, NativeFnTy)):
        return False

    return False
