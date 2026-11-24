# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tabela de declarações do checker: classes, enums, interfaces e hierarquia.

Parte do split `TypeOps`/`DeclTable` do ADR-0141: aqui ficam os registros e as
consultas de declaração, sem estado de fluxo nem regras de tipos. O checker
mantém os escopos e delega as buscas para cá.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import FnTy, Ty, TyVar


@dataclass
class FieldBinding:
    ty: Ty
    mutable: bool
    token: Token


@dataclass
class ClassInfo:
    name: str
    superclass: str | None
    fields: dict[str, FieldBinding] = field(default_factory=dict)
    methods: dict[str, FnTy] = field(default_factory=dict)
    method_tokens: dict[str, Token] = field(default_factory=dict)
    init: FnTy | None = None
    type_params: tuple[TyVar, ...] = ()
    type_param_names: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()


@dataclass
class InterfaceInfo:
    name: str
    methods: dict[str, FnTy] = field(default_factory=dict)
    method_tokens: dict[str, Token] = field(default_factory=dict)
    defaults: dict[str, bool] = field(default_factory=dict)
    declared: bool = False


@dataclass
class EnumVariantInfo:
    name: str
    payload: tuple[Ty, ...]
    token: Token | None = None


@dataclass
class EnumInfo:
    name: str
    type_params: tuple[TyVar, ...] = ()
    type_param_names: tuple[str, ...] = ()
    variants: dict[str, EnumVariantInfo] = field(default_factory=dict)


@dataclass(frozen=True)
class FunctionSignature:
    type_params: tuple[TyVar, ...]
    type_param_names: tuple[str, ...]
    fn: FnTy


class DeclTable:
    """Classes, enums e interfaces declarados, com as buscas de hierarquia."""

    def __init__(self) -> None:
        self.classes: dict[str, ClassInfo] = {}
        self.enums: dict[str, EnumInfo] = {}
        self.interfaces: dict[str, InterfaceInfo] = {}

    def find_field(self, class_name: str, field_name: str) -> FieldBinding | None:
        name: str | None = class_name
        while name is not None:
            info = self.classes.get(name)
            if info is None:
                return None
            if field_name in info.fields:
                return info.fields[field_name]
            name = info.superclass

        return None

    def find_method(self, class_name: str, method_name: str) -> FnTy | None:
        """Métodos da classe/hierarquia e, por último, os defaults de interface."""
        name: str | None = class_name
        while name is not None:
            info = self.classes.get(name)
            if info is None:
                return None
            if method_name in info.methods:
                return info.methods[method_name]
            if method_name == "init" and info.init is not None:
                return info.init
            name = info.superclass

        name = class_name
        while name is not None:
            info = self.classes.get(name)
            if info is None:
                return None
            for interface in info.interfaces:
                interface_info = self.interfaces.get(interface)
                if interface_info is not None:
                    method = interface_info.methods.get(method_name)
                    if method is not None:
                        return method
            name = info.superclass

        return None

    def find_class_method(self, class_name: str | None, method_name: str) -> FnTy | None:
        """Só métodos declarados por classes (não defaults de interface)."""
        name = class_name
        while name is not None:
            info = self.classes.get(name)
            if info is None:
                return None
            if method_name in info.methods:
                return info.methods[method_name]
            if method_name == "init" and info.init is not None:
                return info.init
            name = info.superclass

        return None

    def initializer(self, info: ClassInfo) -> FnTy | None:
        """`init` da classe ou o primeiro `init` herdado (o runtime herda)."""
        if info.init is not None:
            return info.init
        if info.superclass is None:
            return None
        return self.find_method(info.superclass, "init")

    def is_subclass(self, actual: str, expected: str) -> bool:
        name: str | None = actual
        while name is not None:
            if name == expected:
                return True
            info = self.classes.get(name)
            name = info.superclass if info is not None else None

        return False

    def implements_interface(self, class_name: str, interface: str) -> bool:
        """Nominal e transitivo pela superclasse (ADR-0080)."""
        name: str | None = class_name
        while name is not None:
            info = self.classes.get(name)
            if info is None:
                return False
            if interface in info.interfaces:
                return True
            name = info.superclass

        return False

    def interface_names(self, info: ClassInfo) -> list[str]:
        names: list[str] = []
        current: ClassInfo | None = info
        while current is not None:
            for interface in current.interfaces:
                if interface not in names:
                    names.append(interface)
            current = (
                self.classes.get(current.superclass) if current.superclass is not None else None
            )

        return names
