# SPDX-License-Identifier: MIT OR Apache-2.0
"""Índice de símbolos para LSP-1 (hover/definition), sobre a AST do checker.

Não reimplementa tipos: lê `Checker.types` e `Resolver.references`. Cobre variáveis,
parâmetros, funções/métodos, classes, interfaces, enums, variantes, campos e type aliases.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from loxia.source_symbols import (
    class_signature as _class_signature,
)
from loxia.source_symbols import (
    field_signature as _field_signature,
)
from loxia.source_symbols import (
    function_signature as _function_signature,
)
from loxia.source_symbols import (
    param_signature as _param_signature,
)
from loxia_core.frontend.destructuring import pattern_names
from loxia_core.frontend.expr import (
    Call,
    Expr,
    Get,
    Match,
    Set,
    Super,
    This,
    Variable,
    VariantPattern,
)
from loxia_core.frontend.stmt import (
    Block,
    Class,
    Destructure,
    EnumDecl,
    ForIn,
    Function,
    If,
    Interface,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import ClassTy, EnumObjectTy, InterfaceTy, Ty, display
from loxia_core.semantics.checker import Checker
from loxia_core.semantics.resolver import Resolver


def token_key(token: Token) -> tuple[int, int, int]:
    return (token.line, token.column or 1, token.offset)


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    token: Token
    signature: str
    doc: str | None
    container: str | None = None
    type: Ty | None = None
    annotated: bool = False


class SymbolIndex:
    def __init__(
        self,
        statements: list[Stmt],
        *,
        source: str,
        checker: Checker | None,
        resolver: Resolver | None,
    ) -> None:
        self.source = source
        self.symbols: list[Symbol] = []
        self.by_token: dict[tuple[int, int, int], Symbol] = {}
        self.by_name: dict[str, Symbol] = {}
        self.by_container: dict[str, dict[str, Symbol]] = {}
        self.references: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        self.token_types: dict[tuple[int, int, int], Ty] = {}
        self._checker = checker
        self._resolver = resolver
        self._add_statements(statements, container=None)
        if resolver is not None:
            for use, declaration in resolver.references.items():
                self.references[token_key(use)] = token_key(declaration)
        self._collect_expressions(statements)

    # -- declarações -----------------------------------------------------

    def _add(self, symbol: Symbol) -> None:
        self.symbols.append(symbol)
        self.by_token[token_key(symbol.token)] = symbol
        if symbol.container is None:
            self.by_name.setdefault(symbol.name, symbol)
        else:
            self.by_container.setdefault(symbol.container, {})[symbol.name] = symbol

    def _add_statements(self, statements: list[Stmt], *, container: str | None) -> None:
        for statement in statements:
            self._add_statement(statement, container=container)

    def _add_statement(self, statement: Stmt, *, container: str | None) -> None:
        if isinstance(statement, Function):
            self._add_function(statement, container=container)
        elif isinstance(statement, Class):
            self._add(
                Symbol(
                    name=statement.name.lexeme,
                    kind="class",
                    token=statement.name,
                    signature=_class_signature(statement),
                    doc=statement.doc,
                    container=container,
                )
            )
            for field in statement.fields:
                initializer_type = (
                    self._checker.types.get(field.initializer)
                    if self._checker is not None and field.initializer is not None
                    else None
                )
                ty = field.type_annotation or initializer_type
                self._add(
                    Symbol(
                        name=field.name.lexeme,
                        kind="field",
                        token=field.name,
                        signature=_field_signature(field),
                        doc=field.doc,
                        container=statement.name.lexeme,
                        type=ty,
                        annotated=field.type_annotation is not None,
                    )
                )
            for method in statement.methods:
                self._add_function(method, container=statement.name.lexeme)
        elif isinstance(statement, Interface):
            self._add(
                Symbol(
                    name=statement.name.lexeme,
                    kind="interface",
                    token=statement.name,
                    signature=f"interface {statement.name.lexeme}",
                    doc=statement.doc,
                    container=container,
                )
            )
            for method in statement.methods:
                self._add_function(method, container=statement.name.lexeme)
        elif isinstance(statement, EnumDecl):
            self._add(
                Symbol(
                    name=statement.name.lexeme,
                    kind="enum",
                    token=statement.name,
                    signature=f"enum {statement.name.lexeme}",
                    doc=statement.doc,
                    container=container,
                )
            )
            for variant in statement.variants:
                payload = (
                    "(" + ", ".join(display(item) for item in variant.payload) + ")"
                    if variant.payload
                    else ""
                )
                self._add(
                    Symbol(
                        name=variant.name.lexeme,
                        kind="variant",
                        token=variant.name,
                        signature=f"{variant.name.lexeme}{payload}",
                        doc=variant.doc,
                        container=statement.name.lexeme,
                    )
                )
        elif isinstance(statement, TypeAlias):
            self._add(
                Symbol(
                    name=statement.name.lexeme,
                    kind="type",
                    token=statement.name,
                    signature=f"type {statement.name.lexeme} = {display(statement.target)}",
                    doc=statement.doc,
                    container=container,
                )
            )
        elif isinstance(statement, Var):
            initializer_type = (
                self._checker.types.get(statement.initializer)
                if self._checker is not None and statement.initializer is not None
                else None
            )
            ty = statement.type_annotation or initializer_type
            keyword = "var" if statement.mutable else "val"
            signature = f"{keyword} {statement.name.lexeme}"
            if ty is not None:
                signature += f": {display(ty)}"
            self._add(
                Symbol(
                    name=statement.name.lexeme,
                    kind="variable",
                    token=statement.name,
                    signature=signature,
                    doc=statement.doc,
                    container=container,
                    type=ty,
                    annotated=statement.type_annotation is not None,
                )
            )
        elif isinstance(statement, Destructure):
            for name in pattern_names(statement.pattern):
                self._add(
                    Symbol(
                        name=name.lexeme,
                        kind="variable",
                        token=name,
                        signature=f"val {name.lexeme}",
                        doc=None,
                        container=container,
                    )
                )
        elif isinstance(statement, Block):
            self._add_statements(statement.statements, container=container)
        elif isinstance(statement, ForIn):
            loop_type = None
            if self._checker is not None:
                iterable_type = self._checker.types.get(statement.iterable)
                if iterable_type is not None:
                    loop_type = self._checker.element_type(iterable_type, statement.name)
            signature = f"val {statement.name.lexeme}"
            if loop_type is not None:
                signature += f": {display(loop_type)}"
            self._add(
                Symbol(
                    name=statement.name.lexeme,
                    kind="variable",
                    token=statement.name,
                    signature=signature,
                    doc=None,
                    container=container,
                    type=loop_type,
                )
            )
            self._add_statement(statement.body, container=container)
        elif isinstance(statement, If):
            self._add_statement(statement.then_branch, container=container)
            if statement.else_branch is not None:
                self._add_statement(statement.else_branch, container=container)
        elif isinstance(statement, While):
            self._add_statement(statement.body, container=container)
        elif isinstance(statement, Try):
            self._add_statements(statement.body, container=container)
            for clause in statement.handlers:
                self._add(
                    Symbol(
                        name=clause.binding.lexeme,
                        kind="variable",
                        token=clause.binding,
                        signature=f"val {clause.binding.lexeme}",
                        doc=None,
                        container=container,
                    )
                )
                self._add_statements(clause.body, container=container)
            if statement.finally_body is not None:
                self._add_statements(statement.finally_body, container=container)

    def _add_function(self, function: Function, *, container: str | None) -> None:
        self._add(
            Symbol(
                name=function.name.lexeme,
                kind="method" if container is not None else "function",
                token=function.name,
                signature=_function_signature(function),
                doc=function.doc,
                container=container,
                type=function.return_type,
            )
        )
        for param in function.params:
            self._add(
                Symbol(
                    name=param.name.lexeme,
                    kind="variable",
                    token=param.name,
                    signature=_param_signature(param),
                    doc=None,
                    container=function.name.lexeme,
                    type=param.type_annotation,
                    annotated=param.type_annotation is not None,
                )
            )
        self._add_statements(function.body, container=function.name.lexeme)

    # -- expressões ------------------------------------------------------

    def _collect_expressions(self, statements: list[Stmt]) -> None:
        for statement in statements:
            _walk_value(statement, self._on_expr)

    def _on_expr(self, expression: Expr) -> None:
        if isinstance(expression, Variable):
            key = token_key(expression.name)
            ty = self._type_of(expression)
            if ty is not None:
                self.token_types[key] = ty
            if key not in self.references:
                symbol = self.by_name.get(expression.name.lexeme)
                if symbol is not None:
                    self.references[key] = token_key(symbol.token)
            return

        if isinstance(expression, (Get, Set)):
            key = token_key(expression.name)
            ty = self._type_of(expression)
            if ty is not None:
                self.token_types[key] = ty
            object_type = (
                self._checker.types.get(expression.object) if self._checker is not None else None
            )
            if isinstance(object_type, (ClassTy, InterfaceTy, EnumObjectTy)):
                symbol = self.by_container.get(object_type.name, {}).get(expression.name.lexeme)
                if symbol is not None:
                    self.references[key] = token_key(symbol.token)
            return

        if isinstance(expression, (This, Super)):
            ty = self._type_of(expression)
            if ty is not None:
                self.token_types[token_key(expression.keyword)] = ty
            return

        if isinstance(expression, Match):
            for arm in expression.arms:
                if isinstance(arm.pattern, VariantPattern):
                    for binding in arm.pattern.bindings:
                        self._add(
                            Symbol(
                                name=binding.lexeme,
                                kind="variable",
                                token=binding,
                                signature=f"val {binding.lexeme}",
                                doc=None,
                            )
                        )
            return

        if isinstance(expression, Call):
            # O hover/definition do callee já é coberto por Variable/Get.
            return

    def _type_of(self, expression: Expr) -> Ty | None:
        if self._checker is None:
            return None
        return self._checker.types.get(expression)

    # -- consulta --------------------------------------------------------

    def symbol_at(self, token: Token) -> Symbol | None:
        key = token_key(token)
        direct = self.by_token.get(key)
        if direct is not None:
            return direct
        target = self.references.get(key)
        if target is not None:
            return self.by_token.get(target)
        return self.by_name.get(token.lexeme)

    def type_at(self, token: Token) -> Ty | None:
        return self.token_types.get(token_key(token))

    def reference_target(self, token: Token) -> Symbol | None:
        key = token_key(token)
        target = self.references.get(key)
        if target is None:
            return self.by_token.get(key)
        return self.by_token.get(target)


def _walk_value(value: object, on_expr: Any) -> None:
    if isinstance(value, (Token, Ty, str, int, float, bool)) or value is None:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _walk_value(item, on_expr)
        return
    if hasattr(value, "accept") and value.__class__.__module__.endswith("expr"):
        on_expr(value)
    if is_dataclass(value):
        for field in fields(value):
            _walk_value(getattr(value, field.name), on_expr)
