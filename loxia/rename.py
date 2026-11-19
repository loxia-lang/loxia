# SPDX-License-Identifier: MIT OR Apache-2.0
"""Rename cross-file semântico de declarações top-level de módulos.

O `ModuleLoader` reescreve nomes públicos para ``mod$nome`` preservando a posição
original do token. A partir dessa AST resolvida, este módulo coleta só os usos que
pertencem à declaração alvo, mesmo que outro arquivo tenha um local com o mesmo nome.
Imports, aliases e anotações de tipo são editados no texto original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path

from loxia.engine import Loxia
from loxia.source_symbols import imports_of, parse_source
from loxia.symbols import SymbolIndex
from loxia_core.diagnostics.source import display_path
from loxia_core.frontend.stmt import Import, Stmt
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import ClassTy

_TOP_LEVEL = {"function", "class", "enum", "interface", "type", "variable"}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Target:
    old_name: str
    declaration_file: Path
    declaration_offset: int
    mangled: frozenset[str]
    direct_names: dict[Path, frozenset[str]]
    aliases: dict[Path, frozenset[str]]


@dataclass
class _Analysis:
    path: Path
    text: str
    original: list[Stmt]
    merged: list[Stmt]
    index: SymbolIndex


@dataclass
class _Workspace:
    root: Path
    files: dict[Path, str]
    analyses: dict[Path, _Analysis]
    positions: dict[tuple[Path, int], set[str]]
    tokens_by_lexeme: dict[str, set[tuple[Path, int]]]
    declarations: dict[str, tuple[Path, Token]]


def semantic_target(
    root: Path, files: dict[Path, str], target_path: Path, token: Token
) -> Target | None:
    workspace = _workspace(root, files)
    if isinstance(workspace, str):
        return None
    return _target(workspace, target_path, token)


def semantic_rename(
    root: Path,
    files: dict[Path, str],
    target_path: Path,
    token: Token,
    new_name: str,
) -> dict[str, object] | str | None:
    workspace = _workspace(root, files)
    if isinstance(workspace, str):
        return workspace
    target = _target(workspace, target_path, token)
    if target is None:
        return None
    if new_name == target.old_name:
        return {"changes": {}}
    return _edits(workspace, target, new_name)


def _workspace(root: Path, files: dict[Path, str]) -> _Workspace | str:
    analyses: dict[Path, _Analysis] = {}
    positions: dict[tuple[Path, int], set[str]] = {}
    tokens_by_lexeme: dict[str, set[tuple[Path, int]]] = {}
    declarations: dict[str, tuple[Path, Token]] = {}
    for path in sorted(files):
        text = files[path]
        original = parse_source(text)
        if original is None:
            return f"Can't rename across files: parse error in {path.name}."
        lox = Loxia(error_format="json", color="never", max_errors=0)
        lox.use_file(display_path(str(path)), module_root=root)
        lox.check(text, emit=False)
        merged = lox.last_statements
        if merged is None:
            return f"Can't rename across files: parse error in {path.name}."
        index = SymbolIndex(
            merged,
            source=text,
            checker=lox.last_checker,
            resolver=lox.last_resolver,
        )
        analyses[path] = _Analysis(path, text, original, merged, index)
        for symbol in index.symbols:
            if symbol.container is not None or symbol.kind not in _TOP_LEVEL:
                continue
            token_file = _token_file(symbol.token, root, path)
            declarations.setdefault(symbol.name, (token_file, symbol.token))
        for statement in merged:
            for item in _tokens(statement):
                token_file = _token_file(item, root, path)
                key = (token_file, item.offset)
                positions.setdefault(key, set()).add(item.lexeme)
                tokens_by_lexeme.setdefault(item.lexeme, set()).add(key)
    return _Workspace(root, dict(files), analyses, positions, tokens_by_lexeme, declarations)


def _target(workspace: _Workspace, target_path: Path, token: Token) -> Target | None:
    key = (target_path.resolve(), token.offset)
    candidates = {lexeme for lexeme in workspace.positions.get(key, set()) if "$" in lexeme}
    if not candidates:
        analysis = workspace.analyses.get(target_path)
        if analysis is not None:
            candidates = _candidate_from_import(analysis, token)
            candidates = {item for item in candidates if item in workspace.declarations}
    if not candidates:
        return None
    names = sorted(candidates)
    declaration = next(
        (workspace.declarations[name] for name in names if name in workspace.declarations),
        None,
    )
    if declaration is None:
        return None
    declaration_file, declaration_token = declaration
    old_name = declaration_token.lexeme.rsplit("$", 1)[-1]
    direct_names: dict[Path, set[str]] = {}
    aliases: dict[Path, set[str]] = {}
    for path, analysis in workspace.analyses.items():
        for statement in analysis.original:
            if not isinstance(statement, Import) or not statement.from_import:
                continue
            module = ".".join(part.lexeme for part in statement.path)
            for item in statement.names:
                candidate = module.replace(".", "$") + "$" + item.name.lexeme
                if candidate in candidates:
                    local = (item.alias or item.name).lexeme
                    if item.alias is not None and local != item.name.lexeme:
                        aliases.setdefault(path, set()).add(local)
                    else:
                        direct_names.setdefault(path, set()).add(local)
    direct_names.setdefault(declaration_file, set()).add(old_name)
    if token.lexeme in aliases.get(target_path, set()) and token.lexeme != old_name:
        return None
    return Target(
        old_name=old_name,
        declaration_file=declaration_file,
        declaration_offset=declaration_token.offset,
        mangled=frozenset(candidates),
        direct_names={path: frozenset(names) for path, names in direct_names.items()},
        aliases={path: frozenset(names) for path, names in aliases.items()},
    )


def _candidate_from_import(analysis: _Analysis, token: Token) -> set[str]:
    candidates: set[str] = set()
    imported = imports_of(analysis.original).get(token.lexeme)
    if imported is not None and imported.public is not None:
        candidates.add(imported.module.replace(".", "$") + "$" + imported.public)
    for statement in analysis.original:
        if not isinstance(statement, Import) or not statement.from_import:
            continue
        module = ".".join(part.lexeme for part in statement.path)
        for item in statement.names:
            if item.name.lexeme == token.lexeme:
                candidates.add(module.replace(".", "$") + "$" + item.name.lexeme)
    return candidates


def _edits(workspace: _Workspace, target: Target, new_name: str) -> dict[str, object] | str:
    edits: dict[Path, dict[int, str]] = {}
    affected: set[Path] = {target.declaration_file}
    for name in target.mangled:
        for path, offset in workspace.tokens_by_lexeme.get(name, set()):
            identifier = _identifier_at(workspace.files[path], offset)
            if identifier in target.aliases.get(path, frozenset()):
                continue
            edits.setdefault(path, {})[offset] = new_name
            affected.add(path)
    edits.setdefault(target.declaration_file, {})[target.declaration_offset] = new_name

    for path, analysis in workspace.analyses.items():
        for statement in analysis.original:
            if not isinstance(statement, Import) or not statement.from_import:
                continue
            module = ".".join(part.lexeme for part in statement.path)
            for item in statement.names:
                candidate = module.replace(".", "$") + "$" + item.name.lexeme
                if candidate in target.mangled:
                    edits.setdefault(path, {})[item.name.offset] = new_name
                    affected.add(path)

    for path, names in target.direct_names.items():
        local_analysis = workspace.analyses.get(path)
        if local_analysis is None:
            continue
        affected.add(path)
        for statement in local_analysis.original:
            for type_token in _class_type_tokens(statement):
                if type_token.lexeme in names:
                    edits.setdefault(path, {})[type_token.offset] = new_name

    for path in affected:
        collision_analysis = workspace.analyses.get(path)
        if collision_analysis is None:
            continue
        for statement in collision_analysis.original:
            for token in _tokens(statement):
                if token.lexeme == new_name:
                    return (
                        f"Can't rename '{target.old_name}' to '{new_name}': "
                        f"the name is already used in {path.name}."
                    )

    changes: dict[str, list[dict[str, object]]] = {}
    for path, offsets in edits.items():
        text = workspace.files[path]
        entries: list[dict[str, object]] = []
        for offset, replacement in sorted(offsets.items()):
            identifier = _identifier_at(text, offset)
            if identifier is None:
                continue
            start = _position(text, offset)
            end = _position(text, offset + len(identifier.encode("utf-8")))
            entries.append(
                {
                    "range": {"start": start, "end": end},
                    "newText": replacement,
                }
            )
        if entries:
            changes[path.resolve().as_uri()] = entries
    return {"changes": changes}


def _tokens(value: object) -> list[Token]:
    found: list[Token] = []

    def visit(item: object) -> None:
        if isinstance(item, Token):
            found.append(item)
            return
        if is_dataclass(item) and not isinstance(item, type):
            for field in fields(item):
                visit(getattr(item, field.name))
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return found


def _class_type_tokens(value: object) -> list[Token]:
    found: list[Token] = []

    def visit(item: object) -> None:
        if isinstance(item, ClassTy) and item.token is not None:
            found.append(item.token)
        if is_dataclass(item) and not isinstance(item, type):
            for field in fields(item):
                visit(getattr(item, field.name))
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return found


def _token_file(token: Token, root: Path, fallback: Path) -> Path:
    if not token.file:
        return fallback.resolve()
    path = Path(token.file)
    if path.is_absolute():
        return path.resolve()
    for base in (Path.cwd(), root, fallback.parent):
        candidate = base / path
        if candidate.exists():
            return candidate.resolve()
    return (root / path).resolve()


def _identifier_at(text: str, offset: int) -> str | None:
    data = text.encode("utf-8")
    match = _IDENTIFIER.match(data[offset:].decode("utf-8"))
    return match.group(0) if match is not None else None


def _position(text: str, offset: int) -> dict[str, int]:
    data = text.encode("utf-8")
    prefix = data[:offset].decode("utf-8")
    line = prefix.count("\n")
    last = prefix.rsplit("\n", 1)[-1]
    return {"line": line, "character": len(last.encode("utf-16-le")) // 2}
