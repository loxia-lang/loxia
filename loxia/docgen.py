# SPDX-License-Identifier: MIT OR Apache-2.0
"""Geração de documentação a partir de `///` (ADR-0091).

O parser guarda a doc no nó de declaração; este módulo só transforma AST em Markdown
ou JSON, sem executar o programa. Determinístico: ordem de declaração, sem caminho
absoluto, sem timestamp.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from loxia_core.frontend.stmt import (
    Class,
    EnumDecl,
    Field,
    Function,
    Interface,
    Param,
    Stmt,
    TypeAlias,
    Var,
)
from loxia_core.frontend.ty import Ty, display

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DocSymbol:
    name: str
    kind: str
    signature: str
    doc: str | None
    line: int
    column: int
    visibility: str
    container: str | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "doc": self.doc,
            "line": self.line,
            "column": self.column,
            "visibility": self.visibility,
            "container": self.container,
        }


def _visibility(name: str) -> str:
    return "private" if name.startswith("_") else "public"


def _type_text(ty: Ty | None) -> str:
    if ty is None:
        return ""
    return display(ty)


def _params(params: list[Param]) -> str:
    rendered: list[str] = []
    for param in params:
        name = f"...{param.name.lexeme}" if param.variadic else param.name.lexeme
        annotation = _type_text(param.type_annotation)
        if annotation:
            name += f": {annotation}"
        if param.default is not None:
            name += " = ..."
        rendered.append(name)
    return ", ".join(rendered)


def _function_symbol(function: Function, *, container: str | None = None) -> DocSymbol:
    type_params = (
        "[" + ", ".join(item.lexeme for item in function.type_params) + "]"
        if function.type_params
        else ""
    )
    signature = f"fn {function.name.lexeme}{type_params}({_params(function.params)})"
    if function.return_type is not None:
        signature += f" -> {_type_text(function.return_type)}"
    return DocSymbol(
        name=function.name.lexeme,
        kind="method" if container is not None else "function",
        signature=signature,
        doc=function.doc,
        line=function.name.line,
        column=function.name.column,
        visibility=_visibility(function.name.lexeme),
        container=container,
    )


def _field_symbol(field: Field, container: str) -> DocSymbol:
    keyword = "var" if field.mutable else "val"
    annotation = _type_text(field.type_annotation)
    signature = f"{keyword} {field.name.lexeme}"
    if annotation:
        signature += f": {annotation}"
    return DocSymbol(
        name=field.name.lexeme,
        kind="field",
        signature=signature,
        doc=field.doc,
        line=field.name.line,
        column=field.name.column,
        visibility=_visibility(field.name.lexeme),
        container=container,
    )


def _declaration_symbols(statement: Stmt) -> list[DocSymbol]:
    if isinstance(statement, Function):
        return [_function_symbol(statement)]

    if isinstance(statement, Class):
        type_params = (
            "[" + ", ".join(item.lexeme for item in statement.type_params) + "]"
            if statement.type_params
            else ""
        )
        superclass = (
            f"({statement.superclass.name.lexeme})" if statement.superclass is not None else ""
        )
        implements = (
            " implements " + ", ".join(item.lexeme for item in statement.implements)
            if statement.implements
            else ""
        )
        symbols = [
            DocSymbol(
                name=statement.name.lexeme,
                kind="class",
                signature=f"class {statement.name.lexeme}{type_params}{superclass}{implements}",
                doc=statement.doc,
                line=statement.name.line,
                column=statement.name.column,
                visibility=_visibility(statement.name.lexeme),
            )
        ]
        symbols.extend(_field_symbol(field, statement.name.lexeme) for field in statement.fields)
        symbols.extend(
            _function_symbol(method, container=statement.name.lexeme)
            for method in statement.methods
        )
        return symbols

    if isinstance(statement, Interface):
        symbols = [
            DocSymbol(
                name=statement.name.lexeme,
                kind="interface",
                signature=f"interface {statement.name.lexeme}",
                doc=statement.doc,
                line=statement.name.line,
                column=statement.name.column,
                visibility=_visibility(statement.name.lexeme),
            )
        ]
        symbols.extend(
            _function_symbol(method, container=statement.name.lexeme)
            for method in statement.methods
        )
        return symbols

    if isinstance(statement, EnumDecl):
        type_params = (
            "[" + ", ".join(item.lexeme for item in statement.type_params) + "]"
            if statement.type_params
            else ""
        )
        symbols = [
            DocSymbol(
                name=statement.name.lexeme,
                kind="enum",
                signature=f"enum {statement.name.lexeme}{type_params}",
                doc=statement.doc,
                line=statement.name.line,
                column=statement.name.column,
                visibility=_visibility(statement.name.lexeme),
            )
        ]
        for variant in statement.variants:
            payload = (
                "(" + ", ".join(_type_text(item) for item in variant.payload) + ")"
                if variant.payload
                else ""
            )
            symbols.append(
                DocSymbol(
                    name=variant.name.lexeme,
                    kind="variant",
                    signature=f"{variant.name.lexeme}{payload}",
                    doc=variant.doc,
                    line=variant.name.line,
                    column=variant.name.column,
                    visibility=_visibility(variant.name.lexeme),
                    container=statement.name.lexeme,
                )
            )
        return symbols

    if isinstance(statement, TypeAlias):
        return [
            DocSymbol(
                name=statement.name.lexeme,
                kind="type",
                signature=f"type {statement.name.lexeme} = {_type_text(statement.target)}",
                doc=statement.doc,
                line=statement.name.line,
                column=statement.name.column,
                visibility=_visibility(statement.name.lexeme),
            )
        ]

    if isinstance(statement, Var):
        keyword = "var" if statement.mutable else "val"
        signature = f"{keyword} {statement.name.lexeme}"
        annotation = _type_text(statement.type_annotation)
        if annotation:
            signature += f": {annotation}"
        return [
            DocSymbol(
                name=statement.name.lexeme,
                kind="variable",
                signature=signature,
                doc=statement.doc,
                line=statement.name.line,
                column=statement.name.column,
                visibility=_visibility(statement.name.lexeme),
            )
        ]

    return []


def extract(statements: list[Stmt]) -> list[DocSymbol]:
    symbols: list[DocSymbol] = []
    for statement in statements:
        symbols.extend(_declaration_symbols(statement))
    return symbols


def payload(source: str, symbols: list[DocSymbol]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "symbols": [symbol.as_json() for symbol in symbols],
    }


def render_json(source: str, symbols: list[DocSymbol]) -> str:
    return json.dumps(payload(source, symbols), ensure_ascii=False, indent=2) + "\n"


_KIND_TITLES = {
    "class": "Classes",
    "interface": "Interfaces",
    "enum": "Enums",
    "type": "Types",
    "function": "Functions",
    "variable": "Variables",
}


def render_markdown(source: str, symbols: list[DocSymbol]) -> str:
    lines = [f"# Loxia API — `{source}`", ""]
    if not symbols:
        lines.append("_No public declarations._")
        return "\n".join(lines) + "\n"

    top_level = [symbol for symbol in symbols if symbol.container is None]
    for kind, title in _KIND_TITLES.items():
        group = [symbol for symbol in top_level if symbol.kind == kind]
        if not group:
            continue
        lines.extend([f"## {title}", ""])
        for symbol in group:
            lines.extend([f"### `{symbol.signature}`", ""])
            lines.append(symbol.doc or "_No documentation._")
            lines.append("")
            members = [item for item in symbols if item.container == symbol.name]
            for member in members:
                lines.extend([f"#### `{member.signature}`", ""])
                lines.append(member.doc or "_No documentation._")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "SCHEMA_VERSION",
    "DocSymbol",
    "extract",
    "payload",
    "render_json",
    "render_markdown",
]
