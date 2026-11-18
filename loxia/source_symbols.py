# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resolução de símbolos sobre a AST original, para o LSP.

O ``SymbolIndex`` trabalha sobre a AST reescrita pelo loader: nomes de módulos viram
``mod$nome`` e os imports desaparecem. Completion e signatureHelp precisam do contrário —
do texto como o usuário escreveu. Este módulo resolve nomes/imports/membros sobre a AST
original e carrega módulos pelo caminho, sem reimplementar tipos do checker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from loxia_core.bundle import bundle_dir
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import (
    Class,
    EnumDecl,
    Field,
    Function,
    Import,
    Interface,
    Param,
    Stmt,
    TypeAlias,
    Var,
)
from loxia_core.frontend.ty import (
    ClassTy,
    Ty,
    display,
)

_MANGLED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\$")
IMPORT_LINE = re.compile(r"^\s*import\s+([\w.]*)$")
FROM_LINE = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+([\w]*)$")


@dataclass(frozen=True)
class ImportRef:
    """Um import visto do documento de origem (``None`` = namespace)."""

    module: str
    public: str | None


@dataclass(frozen=True)
class Member:
    name: str
    kind: str
    signature: str
    doc: str | None
    owner: str
    inherited: bool = False


@dataclass(frozen=True)
class ModuleSource:
    statements: list[Stmt]
    path: Path | None


def parse_source(source: str) -> list[Stmt] | None:
    """Parse estrito: ``None`` quando há qualquer erro de scanner/parser."""
    reporter = ErrorReporter(max_errors=0)
    tokens = Scanner(source, reporter).scan_tokens()
    if reporter.had_error:
        return None
    statements = Parser(tokens, reporter=reporter).parse()
    if reporter.had_error:
        return None
    return statements


def parse_for_completion(source: str, offset: int) -> list[Stmt] | None:
    """Parse tolerante para completion/signatureHelp com o cursor no meio da expressão."""
    prefix = source[:offset]
    line = prefix.rsplit("\n", 1)[-1]
    needs_placeholder = (
        line.rstrip().endswith(".")
        or IMPORT_LINE.match(line) is not None
        or FROM_LINE.match(line) is not None
    )
    placeholder = "x" if needs_placeholder else ""
    candidates = [
        prefix + placeholder + source[offset:],
        source,
        prefix + placeholder,
    ]
    depth = prefix.count("{") - prefix.count("}")
    if depth > 0:
        candidates.append(prefix + placeholder + "\n" + "}" * depth)
    for candidate in candidates:
        statements = parse_source(candidate)
        if statements is not None:
            return statements
    return None


def imports_of(statements: list[Stmt]) -> dict[str, ImportRef]:
    """local -> import, na ordem em que aparece no documento."""
    result: dict[str, ImportRef] = {}
    for statement in statements:
        if not isinstance(statement, Import):
            continue
        module = ".".join(part.lexeme for part in statement.path)
        if statement.from_import:
            for item in statement.names:
                local = (item.alias or item.name).lexeme
                result[local] = ImportRef(module, item.name.lexeme)
        else:
            local = (
                statement.alias.lexeme if statement.alias is not None else statement.path[-1].lexeme
            )
            result[local] = ImportRef(module, None)
    return result


def load_module(module: str, path: Path | None) -> ModuleSource | None:
    """Carrega o módulo pelo mesmo esquema do completion (``std`` ou relativo)."""
    file: Path | None = None
    if module == "std" or module.startswith("std."):
        name = module[4:] if module.startswith("std.") else ""
        if name:
            file = bundle_dir("std") / f"{name}.lx"
    elif path is not None:
        candidate = path.parent.joinpath(*module.split(".")).with_suffix(".lx")
        if candidate.is_file():
            file = candidate
    if file is None or not file.is_file():
        return None
    try:
        statements = parse_source(file.read_text(encoding="utf-8"))
    except OSError:
        return None
    if statements is None:
        return None
    return ModuleSource(statements, file)


def display_source_type(ty: Ty) -> str:
    """``display`` sem prefixos mangled (``mod$Point`` -> ``Point``)."""
    return _MANGLED.sub("", display(ty))


def function_signature(function: Function) -> str:
    params = ", ".join(param_signature(param) for param in function.params)
    type_params = (
        "[" + ", ".join(item.lexeme for item in function.type_params) + "]"
        if function.type_params
        else ""
    )
    signature = f"fn {function.name.lexeme}{type_params}({params})"
    if function.return_type is not None:
        signature += f" -> {display(function.return_type)}"
    return signature


def param_signature(param: Param) -> str:
    text = f"...{param.name.lexeme}" if param.variadic else param.name.lexeme
    if param.type_annotation is not None:
        text += f": {display(param.type_annotation)}"
    return text


def field_signature(field: Field) -> str:
    keyword = "var" if field.mutable else "val"
    signature = f"{keyword} {field.name.lexeme}"
    if field.type_annotation is not None:
        signature += f": {display(field.type_annotation)}"
    return signature


def class_signature(statement: Class) -> str:
    type_params = (
        "[" + ", ".join(item.lexeme for item in statement.type_params) + "]"
        if statement.type_params
        else ""
    )
    superclass = f"({statement.superclass.name.lexeme})" if statement.superclass is not None else ""
    implements = (
        f" implements {', '.join(item.lexeme for item in statement.implements)}"
        if statement.implements
        else ""
    )
    return f"class {statement.name.lexeme}{type_params}{superclass}{implements}"


def declaration_name(statement: Stmt) -> str | None:
    if isinstance(statement, (Function, Class, EnumDecl, Interface, TypeAlias, Var)):
        return statement.name.lexeme
    return None


class SourceContext:
    """Visão de um documento/módulo original, com cache de módulos carregados."""

    def __init__(
        self,
        statements: list[Stmt],
        path: Path | None,
        cache: dict[tuple[str, str], SourceContext] | None = None,
    ) -> None:
        self.statements = statements
        self.path = path
        self.imports = imports_of(statements)
        self._cache: dict[tuple[str, str], SourceContext] = cache if cache is not None else {}
        self._declarations: dict[str, Stmt] = {}
        for statement in statements:
            name = declaration_name(statement)
            if name is not None:
                self._declarations.setdefault(name, statement)

    # -- módulos ---------------------------------------------------------

    def _key(self, module: str) -> tuple[str, str]:
        return (module, str(self.path.parent) if self.path is not None else "")

    def module_context(self, module: str) -> SourceContext | None:
        key = self._key(module)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        loaded = load_module(module, self.path)
        if loaded is None:
            return None
        context = SourceContext(loaded.statements, loaded.path, self._cache)
        self._cache[key] = context
        return context

    # -- declarações -----------------------------------------------------

    def declaration(self, name: str, *, seen: set[tuple[str, str]] | None = None) -> Stmt | None:
        found = self._declarations.get(name)
        if found is not None:
            return found
        imported = self.imports.get(name)
        if imported is None:
            imported = next(
                (ref for ref in self.imports.values() if ref.public == name),
                None,
            )
        if imported is None or imported.public is None:
            return None
        visited = set() if seen is None else seen
        key = (str(self.path) if self.path is not None else "", name)
        if key in visited:
            return None
        visited.add(key)
        context = self.module_context(imported.module)
        if context is None:
            return None
        return context.declaration(imported.public, seen=visited)

    def declaration_with_context(
        self, name: str, *, seen: set[tuple[str, str]] | None = None
    ) -> tuple[Stmt, SourceContext] | None:
        found = self._declarations.get(name)
        if found is not None:
            return found, self
        imported = self.imports.get(name)
        if imported is None:
            imported = next(
                (ref for ref in self.imports.values() if ref.public == name),
                None,
            )
        if imported is None or imported.public is None:
            return None
        visited = set() if seen is None else seen
        key = (str(self.path) if self.path is not None else "", name)
        if key in visited:
            return None
        visited.add(key)
        context = self.module_context(imported.module)
        if context is None:
            return None
        resolved = context.declaration_with_context(imported.public, seen=visited)
        if resolved is None:
            return None
        return resolved

    def class_like_with_context(
        self, name: str
    ) -> tuple[Class | Interface | EnumDecl, SourceContext] | None:
        resolved = self.declaration_with_context(_public_name(name))
        if resolved is None:
            return None
        declaration, context = resolved
        if isinstance(declaration, (Class, Interface, EnumDecl)):
            return declaration, context
        if isinstance(declaration, TypeAlias) and isinstance(declaration.target, ClassTy):
            return context.class_like_with_context(declaration.target.name)
        return None

    def class_like(self, name: str) -> Class | Interface | EnumDecl | None:
        resolved = self.class_like_with_context(name)
        return resolved[0] if resolved is not None else None

    def members(
        self,
        name: str,
        *,
        inherited: bool = True,
        seen: set[str] | None = None,
    ) -> list[Member]:
        resolved = self.class_like_with_context(name)
        if resolved is None:
            return []
        declaration, context = resolved
        owner = declaration.name.lexeme
        visited = set() if seen is None else seen
        if owner in visited:
            return []
        visited.add(owner)

        found: list[Member] = []
        if isinstance(declaration, EnumDecl):
            for variant in declaration.variants:
                found.append(
                    Member(
                        variant.name.lexeme,
                        "variant",
                        f"{owner}.{variant.name.lexeme}",
                        variant.doc,
                        owner,
                    )
                )
            return found
        if isinstance(declaration, Interface):
            for method in declaration.methods:
                found.append(
                    Member(
                        method.name.lexeme,
                        "method",
                        function_signature(method),
                        method.doc,
                        owner,
                    )
                )
            return found

        for field in declaration.fields:
            found.append(
                Member(field.name.lexeme, "field", field_signature(field), field.doc, owner)
            )
        for method in declaration.methods:
            found.append(
                Member(method.name.lexeme, "method", function_signature(method), method.doc, owner)
            )
        if not inherited:
            return found

        names = {member.name for member in found}
        ancestors: list[tuple[str, SourceContext]] = []
        if declaration.superclass is not None:
            base = declaration.superclass.name.lexeme
            base_resolved = context.declaration_with_context(base)
            if base_resolved is not None:
                ancestors.append((base, base_resolved[1]))
        for token in declaration.implements:
            interface_resolved = context.declaration_with_context(token.lexeme)
            if interface_resolved is not None:
                ancestors.append((token.lexeme, interface_resolved[1]))
        for base, ancestor_context in ancestors:
            for member in ancestor_context.members(base, inherited=True, seen=visited):
                if member.name in names:
                    continue
                names.add(member.name)
                found.append(
                    Member(
                        member.name,
                        member.kind,
                        member.signature,
                        member.doc,
                        member.owner,
                        inherited=True,
                    )
                )
        return found

    def function_signature(self, name: str) -> str | None:
        declaration = self.declaration(_public_name(name))
        if isinstance(declaration, Function):
            return function_signature(declaration)
        if isinstance(declaration, Class):
            return self.constructor_signature(name)
        return None

    def method_signature(self, receiver: Ty | str, name: str) -> str | None:
        class_name = _type_name(receiver)
        if class_name is None:
            return None
        for member in self.members(class_name, inherited=True):
            if member.kind == "method" and member.name == name:
                return member.signature
        return None

    def constructor_signature(self, name: str) -> str | None:
        declaration = self.class_like(name)
        if not isinstance(declaration, Class):
            return None
        init = next(
            (method for method in declaration.methods if method.name.lexeme == "init"), None
        )
        params = "" if init is None else ", ".join(param_signature(item) for item in init.params)
        return f"class {declaration.name.lexeme}({params})"

    def namespace_signature(self, local: str, name: str) -> str | None:
        imported = self.imports.get(local)
        if imported is None or imported.public is not None:
            return None
        context = self.module_context(imported.module)
        if context is None:
            return None
        return context.function_signature(name)


def _public_name(name: str) -> str:
    return name.rsplit("$", 1)[-1]


def _type_name(receiver: Ty | str) -> str | None:
    if isinstance(receiver, str):
        return _public_name(receiver)
    name = getattr(receiver, "name", None)
    if isinstance(name, str):
        return _public_name(name)
    return None
