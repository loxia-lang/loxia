# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tipos da linguagem e operações estruturais básicas.

Tipos são apagados em runtime; este módulo é usado pelo parser (anotações) e pelo
checker (inferência/checagem). O tree-walk continua dinâmico.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loxia_core.frontend.tokens import Token


class Ty:
    """Base de todos os tipos."""


@dataclass(frozen=True)
class Prim(Ty):
    name: str

    def __str__(self) -> str:
        return self.name


ANY = Prim("Any")
ERROR = Prim("<error>")
NEVER = Prim("Never")
NIL = Prim("Nil")
BOOL = Prim("Bool")
INT = Prim("Int")
FLOAT = Prim("Float")
STRING = Prim("String")
BYTES = Prim("Bytes")
RANGE = Prim("Range")

PRIMITIVES: dict[str, Ty] = {
    "Any": ANY,
    "Never": NEVER,
    "Nil": NIL,
    "Bool": BOOL,
    "Int": INT,
    "Float": FLOAT,
    "String": STRING,
    "Bytes": BYTES,
    "Range": RANGE,
}


@dataclass(frozen=True)
class TyVar(Ty):
    """Parâmetro de tipo de uma função genérica.

    `id` é único por instanciação para não confundir `T` de funções diferentes; o `name`
    serve só para diagnóstico.
    """

    name: str
    id: int
    bounds: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class ListTy(Ty):
    element: Ty


@dataclass(frozen=True)
class MapTy(Ty):
    key: Ty
    value: Ty


@dataclass(frozen=True)
class TupleTy(Ty):
    """Tupla imutável de aridade fixa; covariante por elemento."""

    items: tuple[Ty, ...]


@dataclass(frozen=True)
class ClassTy(Ty):
    """Instância de uma classe; `args` vazio para classe não genérica.

    `token` é metadado opcional do parser (posição do nome na anotação), usado pelo
    rename do LSP. Fora de comparação/hash para não mudar igualdade de tipos.
    """

    name: str
    args: tuple[Ty, ...] = ()
    token: Token | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class EnumTy(Ty):
    name: str
    args: tuple[Ty, ...] = ()


@dataclass(frozen=True)
class EnumObjectTy(Ty):
    """O enum como namespace de variantes (`Cor`, `Result`)."""

    name: str


@dataclass(frozen=True)
class ClassObjectTy(Ty):
    """A classe como valor (chamável, base de `super`)."""

    name: str


@dataclass(frozen=True)
class InterfaceTy(Ty):
    """Tipo de uma interface nominal (ADR-0080); não é valor nem construtor."""

    name: str


@dataclass(frozen=True)
class NativeModuleTy(Ty):
    """Namespace nativo somente leitura (`Int`, `Float`, `math`)."""

    name: str


@dataclass(frozen=True)
class UnionTy(Ty):
    members: tuple[Ty, ...]


@dataclass(frozen=True)
class FnTy(Ty):
    params: tuple[Ty, ...]
    ret: Ty
    min_params: int
    variadic: bool = False

    @property
    def fixed_params(self) -> int:
        return len(self.params) - 1 if self.variadic else len(self.params)

    def __str__(self) -> str:
        rendered = [display(param) for param in self.params]
        if self.variadic and rendered:
            rendered[-1] = f"...{rendered[-1]}"
        params = ", ".join(rendered)
        return f"fn({params}) -> {display(self.ret)}"


@dataclass(frozen=True)
class GenericFnTy(Ty):
    """Função genérica ainda não instanciada.

    Só é válida como callee de uma chamada; o checker instancia os parâmetros de tipo e
    unifica com os argumentos/contexto.
    """

    name: str
    type_params: tuple[TyVar, ...]
    fn: FnTy


@dataclass(frozen=True)
class NativeFnTy(Ty):
    """Função nativa cuja assinatura o checker valida caso a caso (ex.: `len`)."""

    name: str


def display(ty: Ty) -> str:
    if isinstance(ty, TyVar):
        if ty.bounds:
            return f"{ty.name}: {' + '.join(ty.bounds)}"
        return ty.name
    if isinstance(ty, (Prim, ClassObjectTy, InterfaceTy, NativeModuleTy)):
        return ty.name
    if isinstance(ty, ClassTy):
        if ty.args:
            return f"{ty.name}[" + ", ".join(display(arg) for arg in ty.args) + "]"
        return ty.name
    if isinstance(ty, EnumTy):
        if ty.args:
            return f"{ty.name}[" + ", ".join(display(arg) for arg in ty.args) + "]"
        return ty.name
    if isinstance(ty, ListTy):
        return f"List[{display(ty.element)}]"
    if isinstance(ty, MapTy):
        return f"Map[{display(ty.key)}, {display(ty.value)}]"
    if isinstance(ty, TupleTy):
        return "(" + ", ".join(display(item) for item in ty.items) + ")"
    if isinstance(ty, GenericFnTy):
        params = ", ".join(display(var) for var in ty.type_params)
        args = ", ".join(display(param) for param in ty.fn.params)
        return f"fn[{params}]({args}) -> {display(ty.fn.ret)}"
    if isinstance(ty, UnionTy):
        return " | ".join(
            f"({display(member)})" if isinstance(member, FnTy) else display(member)
            for member in ty.members
        )
    if isinstance(ty, FnTy):
        return str(ty)
    if isinstance(ty, NativeFnTy):
        return f"fn {ty.name}"

    return str(ty)


def union(*types: Ty) -> Ty:
    members: list[Ty] = []
    for ty in types:
        if ty is NEVER:
            continue
        candidates = ty.members if isinstance(ty, UnionTy) else (ty,)

        for candidate in candidates:
            if candidate is ANY:
                return ANY
            if candidate not in members:
                members.append(candidate)

    if not members:
        return NEVER
    if len(members) == 1:
        return members[0]

    return UnionTy(tuple(members))


def nullable(ty: Ty) -> Ty:
    return union(ty, NIL)


def is_nilable(ty: Ty) -> bool:
    if ty is ANY or ty is NIL:
        return True
    if isinstance(ty, UnionTy):
        return any(member is NIL for member in ty.members)

    return False


def is_union(ty: Ty) -> bool:
    return isinstance(ty, UnionTy)


def non_nil(ty: Ty) -> Ty:
    """Remove `Nil` de `ty`; `nil ?? b` sempre cai em `b`."""
    if ty is NIL:
        return NEVER
    if ty is ANY:
        return ANY
    if isinstance(ty, UnionTy):
        return union(*(member for member in ty.members if member is not NIL))

    return ty


def truthy(ty: Ty) -> Ty:
    """Remove de `ty` as partes que nunca são truthy (só `Nil` hoje)."""
    if ty is NIL:
        return NEVER
    if ty is ANY:
        return ANY
    if isinstance(ty, UnionTy):
        return union(*(truthy(member) for member in ty.members))

    return ty


def falsy(ty: Ty) -> Ty:
    """Mantém de `ty` só as partes que podem ser falsy (`Nil` e `Bool`)."""
    if ty is NIL:
        return NIL
    if ty is BOOL:
        return BOOL
    if ty is ANY:
        return ANY
    if isinstance(ty, UnionTy):
        return union(*(falsy(member) for member in ty.members))

    return NEVER
