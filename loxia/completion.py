# SPDX-License-Identifier: MIT OR Apache-2.0
"""Completion do LSP sobre a AST original (não a reescrita pelo loader).

A AST reescrita tem nomes mangled (`std$strings$upper`) e perde imports; aqui partimos do
texto do documento para sugerir locais no escopo, imports, membros de módulo, variantes de
enum e membros de classe. O `SymbolIndex` reescrito é usado só para tipos inferidos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loxia.builtins_docs import BUILTIN_DOCS
from loxia.source_symbols import (
    FROM_LINE,
    IMPORT_LINE,
    ImportRef,
    Member,
    SourceContext,
    class_signature,
    function_signature,
    imports_of,
    load_module,
    parse_for_completion,
)
from loxia.symbols import SymbolIndex
from loxia_core.bundle import bundle_dir
from loxia_core.frontend.expr import Call, ListLiteral, Literal, MapLiteral, Variable
from loxia_core.frontend.keywords import KEYWORDS
from loxia_core.frontend.stmt import (
    Class,
    EnumDecl,
    Field,
    Function,
    Interface,
    Stmt,
    TypeAlias,
    Var,
)
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import (
    ANY,
    STRING,
    ClassTy,
    EnumObjectTy,
    InterfaceTy,
    ListTy,
    MapTy,
    display,
)

KIND_VARIABLE = 6
KIND_FIELD = 5
KIND_METHOD = 2
KIND_FUNCTION = 3
KIND_CLASS = 7
KIND_INTERFACE = 8
KIND_ENUM = 13
KIND_MODULE = 9
KIND_TYPE = 25
KIND_ENUM_MEMBER = 20
KIND_KEYWORD = 14


@dataclass(frozen=True)
class Item:
    label: str
    kind: int
    detail: str
    doc: str | None
    sort: str


def complete(
    source: str,
    path: Path | None,
    offset: int,
    type_index: SymbolIndex | None,
    *,
    inherited_members: bool = True,
) -> list[dict[str, object]]:
    """Itens de completion para o offset (byte) no documento."""
    prefix, dot_receiver = _cursor(source, offset)
    statements = parse_for_completion(source, offset)
    if statements is None:
        if dot_receiver is not None:
            return _render(_textual_enum_members(dot_receiver, source), prefix)
        return _render(_keyword_items() + _builtin_items(), prefix)
    imports = imports_of(statements)
    import_items = _import_items(source, offset, path, statements)
    if import_items:
        items = import_items
    elif dot_receiver is not None:
        items = _member_items(
            dot_receiver,
            statements,
            path,
            offset,
            imports,
            type_index,
            inherited_members=inherited_members,
        )
        if not items:
            items = _textual_enum_members(dot_receiver, source)
    else:
        items = _value_items(statements, offset, imports, path)
        items.extend(_keyword_items())
    return _render(items, prefix)


def _render(items: list[Item], prefix: str) -> list[dict[str, object]]:
    items = [item for item in items if item.label.startswith(prefix)]
    best: dict[str, Item] = {}
    for item in items:
        current = best.get(item.label)
        if current is None or item.sort < current.sort:
            best[item.label] = item
    return [
        {
            "label": item.label,
            "kind": item.kind,
            "detail": item.detail,
            "insertText": item.label,
            **({"documentation": {"kind": "markdown", "value": item.doc}} if item.doc else {}),
            "sortText": item.sort,
        }
        for item in sorted(best.values(), key=lambda entry: entry.sort)
    ]


def _cursor(source: str, offset: int) -> tuple[str, str | None]:
    prefix_text = source[max(0, offset - 200) : offset]
    line = prefix_text.rsplit("\n", 1)[-1]
    match = _DOT.search(line)
    if match is not None:
        return match.group(2), match.group(1)
    word = _WORD.search(line)
    return (word.group(0) if word else ""), None


_DOT = __import__("re").compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z0-9_]*)$")
_WORD = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def _module_statements(module: str, path: Path | None) -> list[Stmt] | None:
    loaded = load_module(module, path)
    return loaded.statements if loaded is not None else None


def _declarations(statements: list[Stmt]) -> list[Item]:
    items: list[Item] = []
    for statement in statements:
        if isinstance(statement, Function):
            items.append(
                Item(
                    statement.name.lexeme,
                    KIND_FUNCTION,
                    function_signature(statement),
                    statement.doc,
                    f"1_{statement.name.lexeme}",
                )
            )
        elif isinstance(statement, Class):
            items.append(
                Item(
                    statement.name.lexeme,
                    KIND_CLASS,
                    class_signature(statement),
                    statement.doc,
                    f"1_{statement.name.lexeme}",
                )
            )
        elif isinstance(statement, Interface):
            items.append(
                Item(
                    statement.name.lexeme,
                    KIND_INTERFACE,
                    f"interface {statement.name.lexeme}",
                    statement.doc,
                    f"1_{statement.name.lexeme}",
                )
            )
        elif isinstance(statement, EnumDecl):
            items.append(
                Item(
                    statement.name.lexeme,
                    KIND_ENUM,
                    f"enum {statement.name.lexeme}",
                    statement.doc,
                    f"1_{statement.name.lexeme}",
                )
            )
        elif isinstance(statement, TypeAlias):
            items.append(
                Item(
                    statement.name.lexeme,
                    KIND_TYPE,
                    f"type {statement.name.lexeme} = {display(statement.target)}",
                    statement.doc,
                    f"1_{statement.name.lexeme}",
                )
            )
    return items


def _value_items(
    statements: list[Stmt],
    offset: int,
    imports: dict[str, ImportRef],
    path: Path | None,
) -> list[Item]:
    index = SymbolIndex(statements, source="", checker=None, resolver=None)
    function, _klass = _context(statements, offset)
    items: list[Item] = []
    for symbol in index.symbols:
        if "$" in symbol.name:
            continue
        if symbol.token.offset > offset:
            continue
        if symbol.container not in (None, function):
            continue
        kind = {
            "function": KIND_FUNCTION,
            "class": KIND_CLASS,
            "interface": KIND_INTERFACE,
            "enum": KIND_ENUM,
            "type": KIND_TYPE,
            "field": KIND_FIELD,
            "method": KIND_METHOD,
            "variant": KIND_ENUM_MEMBER,
        }.get(symbol.kind, KIND_VARIABLE)
        scope = "0" if symbol.container is not None else "1"
        items.append(
            Item(
                symbol.name,
                kind,
                symbol.signature,
                symbol.doc,
                f"{scope}_{symbol.name}",
            )
        )
    for local, imported in imports.items():
        module, public = imported.module, imported.public
        item = Item(
            local,
            KIND_MODULE if public is None else KIND_FUNCTION,
            f"from {module}" if public is not None else f"import {module}",
            None,
            f"2_{local}",
        )
        if public is not None:
            loaded = _module_statements(module, path)
            if loaded is not None:
                for declaration in _declarations(loaded):
                    if declaration.label == public:
                        item = Item(
                            local,
                            declaration.kind,
                            declaration.detail,
                            declaration.doc,
                            f"2_{local}",
                        )
                        break
        items.append(item)
    for builtin in BUILTIN_DOCS:
        if "." in builtin.name:
            continue
        items.append(
            Item(
                builtin.name,
                KIND_MODULE if builtin.kind == "module" else KIND_FUNCTION,
                builtin.signature,
                builtin.doc,
                f"3_{builtin.name}",
            )
        )
    return items


def _member_items(
    receiver: str,
    statements: list[Stmt],
    path: Path | None,
    offset: int,
    imports: dict[str, ImportRef],
    type_index: SymbolIndex | None,
    *,
    inherited_members: bool,
) -> list[Item]:
    if receiver in {"this", "super"}:
        _, klass = _context(statements, offset)
        if klass is None:
            return []
        if receiver == "super":
            parent = _superclass(statements, klass)
            if parent is None:
                return []
            return _members_for(statements, parent, path, inherited=True)
        return _members_for(statements, klass, path, inherited=inherited_members)
    if receiver in imports:
        imported = imports[receiver]
        loaded = load_module(imported.module, path)
        if loaded is None:
            return []
        if imported.public is not None:
            return _members_for(
                loaded.statements,
                imported.public,
                loaded.path,
                inherited=inherited_members,
            )
        return [item for item in _declarations(loaded.statements) if not item.label.startswith("_")]
    if receiver in {"Int", "Float", "math", "io", "fs", "process", "os", "time"}:
        return _native_members(receiver)
    token = _token_named(statements, receiver, offset)
    ty = None
    if type_index is not None and token is not None:
        ty = type_index.type_at(token)
    symbol = _find_symbol(statements, receiver)
    if symbol is not None and symbol.kind in {"enum", "class", "interface"}:
        return _members_for(statements, symbol.name, path, inherited=inherited_members)
    if ty is None and symbol is not None:
        ty = symbol.type
    if ty is None:
        ty = declared_type(statements, receiver)
    if isinstance(ty, (ClassTy, InterfaceTy, EnumObjectTy)):
        name = ty.name.rsplit("$", 1)[-1]
        return _members_for(statements, name, path, inherited=inherited_members)
    if isinstance(ty, list) and ty:
        return []
    if isinstance(ty, ListTy):
        return [
            Item("push", KIND_METHOD, "push(value)", None, "1_push"),
            Item("pop", KIND_METHOD, "pop() -> T?", None, "1_pop"),
        ]
    if isinstance(ty, MapTy):
        return [
            Item("get", KIND_METHOD, "get(key) -> V?", None, "1_get"),
            Item("has", KIND_METHOD, "has(key) -> Bool", None, "1_has"),
            Item("remove", KIND_METHOD, "remove(key) -> Bool", None, "1_remove"),
            Item("keys", KIND_METHOD, "keys() -> List[K]", None, "1_keys"),
            Item("values", KIND_METHOD, "values() -> List[V]", None, "1_values"),
        ]
    if ty == STRING:
        return []
    return []


def _native_members(module: str) -> list[Item]:
    prefix = module + "."
    return [
        Item(
            builtin.name[len(prefix) :],
            KIND_FUNCTION,
            builtin.signature,
            builtin.doc,
            f"1_{builtin.name}",
        )
        for builtin in BUILTIN_DOCS
        if builtin.name.startswith(prefix)
    ]


def _members_for(
    statements: list[Stmt],
    name: str,
    path: Path | None,
    *,
    inherited: bool,
) -> list[Item]:
    context = SourceContext(statements, path)
    return [_member_item(member) for member in context.members(name, inherited=inherited)]


def _member_item(member: Member) -> Item:
    kind = {
        "field": KIND_FIELD,
        "method": KIND_METHOD,
        "variant": KIND_ENUM_MEMBER,
    }.get(member.kind, KIND_VARIABLE)
    return Item(member.name, kind, member.signature, member.doc, f"1_{member.name}")


def enclosing_context(statements: list[Stmt], offset: int) -> tuple[str | None, str | None]:
    """Função e classe que contêm o offset, para signatureHelp."""
    return _context(statements, offset)


def superclass_name(statements: list[Stmt], name: str) -> str | None:
    """Superclasse direta de uma classe local, para `super.` no signatureHelp."""
    return _superclass(statements, name)


def _context(statements: list[Stmt], offset: int) -> tuple[str | None, str | None]:
    function: str | None = None
    klass: str | None = None
    for statement in statements:
        if isinstance(statement, Class):
            for method in statement.methods:
                if _inside(method, offset):
                    return method.name.lexeme, statement.name.lexeme
        elif isinstance(statement, Function) and _inside(statement, offset):
            function = statement.name.lexeme
    return function, klass


def _inside(function: Function, offset: int) -> bool:
    if function.params_end is None or function.end is None:
        return False
    return function.params_end.offset <= offset <= function.end.offset


def _token_named(statements: list[Stmt], name: str, offset: int) -> Token | None:
    tokens: list[Token] = []

    def walk(value: object) -> None:
        if isinstance(value, Token):
            if value.lexeme == name and value.offset <= offset:
                tokens.append(value)
            return
        if hasattr(value, "__dataclass_fields__"):
            for field_name in value.__dataclass_fields__:
                walk(getattr(value, field_name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for statement in statements:
        walk(statement)
    return max(tokens, key=lambda token: token.offset) if tokens else None


def _find_symbol(statements: list[Stmt], name: str) -> Any:
    index = SymbolIndex(statements, source="", checker=None, resolver=None)
    return index.by_name.get(name)


def _keyword_items() -> list[Item]:
    return [Item(keyword, KIND_KEYWORD, keyword, None, f"4_{keyword}") for keyword in KEYWORDS]


def _import_items(
    source: str, offset: int, path: Path | None, statements: list[Stmt]
) -> list[Item]:
    line = source[:offset].rsplit("\n", 1)[-1]
    match = IMPORT_LINE.match(line)
    if match is not None:
        typed = match.group(1)
        if typed and not typed.startswith("std."):
            return []
        prefix = "" if typed else "std."
        return [
            Item(
                prefix + file.stem,
                KIND_MODULE,
                f"std.{file.stem}",
                None,
                f"2_{file.stem}",
            )
            for file in sorted(bundle_dir("std").glob("*.lx"))
        ]
    match = FROM_LINE.match(line)
    if match is not None:
        module = match.group(1)
        module_statements = _module_statements(module, path)
        if module_statements is None:
            return []
        return [item for item in _declarations(module_statements) if not item.label.startswith("_")]
    return []


def _statement_name(statement: Stmt) -> str | None:
    if isinstance(statement, (Function, Class, EnumDecl, Interface, TypeAlias)):
        return statement.name.lexeme
    return None


def declared_type(statements: list[Stmt], name: str) -> Any:
    found: Any = None

    def walk(value: object) -> None:
        nonlocal found
        if found is not None:
            return
        if isinstance(value, (Var, Field)):
            if value.name.lexeme != name:
                return
            if value.type_annotation is not None:
                found = value.type_annotation
            elif isinstance(value.initializer, ListLiteral):
                found = ListTy(ANY)
            elif isinstance(value.initializer, MapLiteral):
                found = MapTy(ANY, ANY)
            elif isinstance(value.initializer, Literal) and isinstance(
                value.initializer.value, str
            ):
                found = STRING
            elif isinstance(value.initializer, Call) and isinstance(
                value.initializer.callee, Variable
            ):
                found = ClassTy(value.initializer.callee.name.lexeme)
            return
        if hasattr(value, "__dataclass_fields__"):
            for field_name in value.__dataclass_fields__:
                walk(getattr(value, field_name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for statement in statements:
        walk(statement)
    return found


def _superclass(statements: list[Stmt], name: str) -> str | None:
    for statement in statements:
        if (
            isinstance(statement, Class)
            and statement.name.lexeme == name
            and statement.superclass is not None
        ):
            return statement.superclass.name.lexeme
    return None


def _builtin_items() -> list[Item]:
    return [
        Item(
            builtin.name,
            KIND_MODULE if builtin.kind == "module" else KIND_FUNCTION,
            builtin.signature,
            builtin.doc,
            f"3_{builtin.name}",
        )
        for builtin in BUILTIN_DOCS
        if "." not in builtin.name
    ]


_ENUM_TEXT = __import__("re").compile(
    r"\benum\s+([A-Za-z_][A-Za-z0-9_]*)[^{]*\{(.*?)\}", __import__("re").S
)


def _textual_enum_members(receiver: str, source: str) -> list[Item]:
    for match in _ENUM_TEXT.finditer(source):
        if match.group(1) != receiver:
            continue
        items: list[Item] = []
        for chunk in match.group(2).split(","):
            part = chunk.strip().split("(", 1)[0].strip()
            if part and part[0].isalpha():
                items.append(
                    Item(
                        part,
                        KIND_ENUM_MEMBER,
                        f"{receiver}.{part}",
                        None,
                        f"1_{part}",
                    )
                )
        return items
    return []
