# SPDX-License-Identifier: MIT OR Apache-2.0
"""Servidor LSP mínimo (ADR-0090), JSON-RPC sobre stdio, sem dependências.

LSP-0: full sync, diagnostics e documentSymbol. LSP-1: hover/definition via
`SymbolIndex`. LSP-2 parcial: completion, signatureHelp, formatting e semantic tokens.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, cast
from urllib.parse import unquote, urlparse

from loxia import __version__
from loxia.builtins_docs import BUILTIN_DOCS
from loxia.completion import complete as completion_items
from loxia.completion import declared_type as completion_declared_type
from loxia.completion import enclosing_context as completion_context
from loxia.completion import superclass_name as completion_superclass
from loxia.engine import Loxia
from loxia.formatter import format_source
from loxia.formatter.edits import build_edits
from loxia.rename import semantic_references, semantic_rename, semantic_target
from loxia.source_symbols import SourceContext, display_source_type, parse_for_completion
from loxia.symbols import Symbol, SymbolIndex, token_key
from loxia_core.bundle import bundle_dir
from loxia_core.diagnostics.diagnostic import (
    Diagnostic,
    Severity,
    Span,
)
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.source import display_path
from loxia_core.frontend.keywords import KEYWORDS
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import (
    Class,
    EnumDecl,
    Function,
    Import,
    Interface,
    Stmt,
    TypeAlias,
    Var,
)
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import (
    ClassObjectTy,
    ClassTy,
    EnumObjectTy,
    EnumTy,
    InterfaceTy,
    Ty,
    UnionTy,
)
from loxia_core.loader.loader import ModuleLoader
from loxia_core.semantics.resolver import Resolver

JSONRPC_VERSION = "2.0"
SCHEMA_VERSION = 1

# DocumentSymbolKind da LSP.

SEMANTIC_TOKEN_TYPES = (
    "keyword",
    "type",
    "class",
    "enum",
    "interface",
    "function",
    "method",
    "variable",
    "property",
    "string",
    "number",
    "operator",
)

_OPERATOR_TYPES = frozenset(
    name
    for name in dir(TokenType)
    if name
    in {
        "PLUS",
        "MINUS",
        "STAR",
        "SLASH",
        "SLASH_SLASH",
        "PERCENT",
        "STAR_STAR",
        "EQUAL",
        "EQUAL_EQUAL",
        "BANG_EQUAL",
        "LESS",
        "LESS_EQUAL",
        "GREATER",
        "GREATER_EQUAL",
        "AND",
        "OR",
        "PIPE",
        "AMPERSAND",
        "CARET",
        "TILDE",
        "LESS_LESS",
        "GREATER_GREATER",
        "GREATER_GREATER_GREATER",
        "QUESTION_QUESTION",
        "QUESTION_DOT",
        "ARROW",
        "DOT_DOT",
    }
)

SYMBOL_KINDS = {
    "class": 5,
    "method": 6,
    "field": 8,
    "enum": 10,
    "interface": 11,
    "function": 12,
    "variable": 13,
    "type": 26,
    "variant": 22,
}

# Toda request atendida precisa estar aqui; o teste de drift compara este conjunto com
# as capabilities anunciadas no initialize.
REQUEST_METHODS = frozenset(
    {
        "initialize",
        "shutdown",
        "textDocument/documentSymbol",
        "textDocument/hover",
        "textDocument/definition",
        "textDocument/references",
        "textDocument/documentHighlight",
        "textDocument/typeDefinition",
        "textDocument/implementation",
        "textDocument/completion",
        "textDocument/signatureHelp",
        "textDocument/formatting",
        "workspace/symbol",
        "workspace/willRenameFiles",
        "textDocument/codeAction",
        "textDocument/prepareRename",
        "textDocument/rename",
        "textDocument/inlayHint",
        "textDocument/semanticTokens/full",
        "textDocument/prepareTypeHierarchy",
        "typeHierarchy/supertypes",
        "typeHierarchy/subtypes",
    }
)

_UNNECESSARY_CODES = frozenset({"W1001", "W1002"})


@dataclass(frozen=True)
class TypeDecl:
    """Declaração de tipo top-level de um módulo, para hierarquia e implementação."""

    name: str
    kind: str
    path: Path
    token: Token
    superclass: str | None = None
    interfaces: tuple[str, ...] = ()


@dataclass
class Document:
    text: str
    version: int
    path: Path | None
    uri: str


def _read_message(stream: IO[bytes]) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        name, _, value = line.decode("ascii", "replace").partition(":")
        headers[name.strip().lower()] = value.strip()

    try:
        length = int(headers["content-length"])
    except (KeyError, ValueError):
        return None

    body = stream.read(length)
    if not body:
        return None
    try:
        message = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


def _send(stream: IO[bytes], message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def _response(message_id: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": message_id, "result": result}


def _error(message_id: object, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": message_id,
        "error": {"code": code, "message": message},
    }


def _notification(method: str, params: object) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "method": method, "params": params}


def _uri_to_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def _path_to_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _utf16_column(text: str, column: int | None) -> int:
    """Converte coluna 1-based em code points para code units UTF-16."""
    if column is None or column < 1:
        return 0
    prefix = text[: column - 1]
    return len(prefix.encode("utf-16-le")) // 2


def _position(line: int, column: int | None, source: str) -> dict[str, int]:
    lines = source.splitlines()
    text = lines[line - 1] if 0 <= line - 1 < len(lines) else ""
    return {"line": max(0, line - 1), "character": _utf16_column(text, column)}


def _range(span: Span, source: str) -> dict[str, object]:
    start = _position(span.start.line, span.start.column, source)
    end = _position(span.end.line, span.end.column, source)
    if end["line"] < start["line"] or (
        end["line"] == start["line"] and end["character"] < start["character"]
    ):
        end = start
    return {"start": start, "end": end}


def _token_range(token: Token, source: str) -> dict[str, object]:
    start = _position(token.line, token.column, source)
    end = _position(token.line, (token.column or 1) + len(token.lexeme), source)
    return {"start": start, "end": end}


def _offset_range(source: str, offset: int, identifier: str) -> dict[str, object]:
    """Range UTF-16 de um identificador a partir do offset em bytes (como o rename)."""
    start = _position_at(source, offset)
    end_offset = offset + len(identifier.encode("utf-8"))
    end = _position_at(source, end_offset)
    return {"start": start, "end": end}


def _offset_span(source: str, start_offset: int, end_offset: int) -> dict[str, object]:
    return {
        "start": _position_at(source, start_offset),
        "end": _position_at(source, end_offset),
    }


def _position_at(source: str, offset: int) -> dict[str, int]:
    data = source.encode("utf-8")
    prefix = data[:offset].decode("utf-8")
    line = prefix.count("\n")
    last = prefix.rsplit("\n", 1)[-1]
    return {"line": line, "character": len(last.encode("utf-16-le")) // 2}


def _module_of(path: Path, root: Path) -> tuple[str, ...] | None:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if relative.suffix == ".lx":
        relative = relative.with_suffix("")
    parts = tuple(part for part in relative.parts if part not in {"", "."})
    return parts or None


def _rewrite_module(
    module: tuple[str, ...], renames: list[tuple[tuple[str, ...], tuple[str, ...]]]
) -> tuple[str, ...] | None:
    best: tuple[int, tuple[str, ...], tuple[str, ...]] | None = None
    for old, new in renames:
        if len(old) == 0 or module[: len(old)] != old:
            continue
        if best is None or len(old) > best[0]:
            best = (len(old), old, new)
    if best is None:
        return None
    _, old, new = best
    return new + module[len(old) :]


def _kind_matches(requested: str, kind: str) -> bool:
    return kind == requested or kind.startswith(requested + ".")


def _range_key(value: object) -> tuple[tuple[int, int], tuple[int, int]]:
    if not isinstance(value, dict):
        return ((0, 0), (0, 0))
    start = value.get("start")
    end = value.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        return ((0, 0), (0, 0))
    start_line = start.get("line")
    start_character = start.get("character")
    end_line = end.get("line")
    end_character = end.get("character")
    return (
        (
            start_line if isinstance(start_line, int) else 0,
            start_character if isinstance(start_character, int) else 0,
        ),
        (
            end_line if isinstance(end_line, int) else 0,
            end_character if isinstance(end_character, int) else 0,
        ),
    )


def _type_names(ty: Ty | None) -> list[str]:
    if isinstance(ty, (ClassTy, EnumTy, EnumObjectTy, ClassObjectTy, InterfaceTy)):
        # O loader reescreve nomes importados para ``modulo$Nome``; a declaração no
        # workspace usa o nome público.
        return [ty.name.rsplit("$", 1)[-1]]
    if isinstance(ty, UnionTy):
        names: list[str] = []
        for member in ty.members:
            for name in _type_names(member):
                if name not in names:
                    names.append(name)
        return names
    return []


def _type_declarations_of(statements: list[Stmt], path: Path) -> list[TypeDecl]:
    declarations: list[TypeDecl] = []
    for statement in statements:
        if isinstance(statement, Class):
            superclass = statement.superclass.name.lexeme if statement.superclass else None
            declarations.append(
                TypeDecl(
                    name=statement.name.lexeme,
                    kind="class",
                    path=path,
                    token=statement.name,
                    superclass=superclass,
                    interfaces=tuple(item.lexeme for item in statement.implements),
                )
            )
        elif isinstance(statement, Interface):
            declarations.append(
                TypeDecl(
                    name=statement.name.lexeme,
                    kind="interface",
                    path=path,
                    token=statement.name,
                )
            )
        elif isinstance(statement, EnumDecl):
            declarations.append(
                TypeDecl(
                    name=statement.name.lexeme,
                    kind="enum",
                    path=path,
                    token=statement.name,
                )
            )
    return declarations


def _find_type(name: str, declarations: list[TypeDecl], preferred: Path | None) -> TypeDecl | None:
    same_file = [
        item
        for item in declarations
        if item.name == name
        and preferred is not None
        and item.path.resolve() == preferred.resolve()
    ]
    if same_file:
        return same_file[0]
    matches = [item for item in declarations if item.name == name]
    return matches[0] if len(matches) == 1 else None


def _subtypes(declaration: TypeDecl, declarations: list[TypeDecl]) -> list[TypeDecl]:
    if declaration.kind == "interface":
        found = [
            item
            for item in declarations
            if item.kind == "class" and declaration.name in item.interfaces
        ]
    elif declaration.kind == "class":
        found = [
            item
            for item in declarations
            if item.kind == "class" and item.superclass == declaration.name
        ]
    else:
        return []
    unique: dict[tuple[Path, int], TypeDecl] = {}
    for item in found:
        unique.setdefault((item.path.resolve(), item.token.offset), item)
    return list(unique.values())


def _implementors(declaration: TypeDecl, declarations: list[TypeDecl]) -> list[TypeDecl]:
    """Classes que implementam a interface, direta ou herdando de quem implementa."""
    if declaration.kind != "interface":
        return _subtypes(declaration, declarations)
    found: list[TypeDecl] = []
    names = {declaration.name}
    changed = True
    while changed:
        changed = False
        for item in declarations:
            if item.kind != "class" or item in found:
                continue
            implements = declaration.name in item.interfaces
            inherited = item.superclass is not None and item.superclass in names
            if implements or inherited:
                found.append(item)
                names.add(item.name)
                changed = True
    return found


def _type_hierarchy_item(declaration: TypeDecl, source: str) -> dict[str, object]:
    rng = _token_range(declaration.token, source)
    return {
        "name": declaration.name,
        "kind": SYMBOL_KINDS.get(declaration.kind, 5),
        "uri": _path_to_uri(declaration.path),
        "range": rng,
        "selectionRange": rng,
        "detail": declaration.kind,
        "data": {"name": declaration.name, "path": str(declaration.path)},
    }


def _severity(severity: Severity) -> int:
    return 1 if severity is Severity.ERROR else 2


class Server:
    def __init__(self, stdin: IO[bytes], stdout: IO[bytes]) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.documents: dict[str, Document] = {}
        self.indexes: dict[str, SymbolIndex] = {}
        self.source_maps: dict[str, object] = {}
        self.module_files: dict[str, dict[str, Path]] = {}
        self.clean: dict[str, bool] = {}
        self.dependencies: dict[str, frozenset[Path]] = {}
        self.root: Path | None = None
        self.shutdown = False
        self.inlay_hints = True
        self.inherited_members = True

    def _apply_settings(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        inlay = data.get("inlayHints")
        if isinstance(inlay, dict) and isinstance(inlay.get("enabled"), bool):
            self.inlay_hints = inlay["enabled"]
        completion = data.get("completion")
        if isinstance(completion, dict) and isinstance(completion.get("inheritedMembers"), bool):
            self.inherited_members = completion["inheritedMembers"]

    def run(self) -> int:
        while True:
            message = _read_message(self.stdin)
            if message is None:
                return 0
            method = message.get("method")
            if not isinstance(method, str):
                continue
            if method == "exit":
                return 0 if self.shutdown else 1
            if "id" in message:
                self._request(message, method)
            else:
                self._notification(method, message.get("params"))

    # -- dispatch --------------------------------------------------------

    def _request(self, message: dict[str, Any], method: str) -> None:
        message_id = message.get("id")
        if method not in REQUEST_METHODS:
            _send(self.stdout, _error(message_id, -32601, f"Method not found: {method}"))
            return
        if method == "initialize":
            params = message.get("params")
            if isinstance(params, dict):
                root_uri = params.get("rootUri")
                if isinstance(root_uri, str):
                    self.root = _uri_to_path(root_uri)
                self._apply_settings(params.get("initializationOptions"))
            _send(
                self.stdout,
                _response(
                    message_id,
                    {
                        "capabilities": {
                            "textDocumentSync": 1,
                            "hoverProvider": True,
                            "definitionProvider": True,
                            "referencesProvider": True,
                            "documentHighlightProvider": True,
                            "typeDefinitionProvider": True,
                            "implementationProvider": True,
                            "typeHierarchyProvider": True,
                            "workspaceSymbolProvider": True,
                            "renameProvider": {"prepareProvider": True},
                            "documentSymbolProvider": True,
                            "completionProvider": {
                                "triggerCharacters": [".", ":"],
                                "resolveProvider": False,
                            },
                            "signatureHelpProvider": {"triggerCharacters": ["(", ","]},
                            "documentFormattingProvider": True,
                            "codeActionProvider": {
                                "codeActionKinds": [
                                    "quickfix",
                                    "source.fixAll",
                                    "source.fixAll.loxia",
                                ]
                            },
                            "inlayHintProvider": True,
                            "semanticTokensProvider": {
                                "legend": {
                                    "tokenTypes": list(SEMANTIC_TOKEN_TYPES),
                                    "tokenModifiers": [],
                                },
                                "full": True,
                            },
                            "workspace": {
                                "fileOperations": {
                                    "willRename": {"filters": [{"pattern": {"glob": "**/*.lx"}}]}
                                }
                            },
                        },
                        "serverInfo": {
                            "name": "loxia-lsp",
                            "version": __version__,
                        },
                    },
                ),
            )
            return

        if method == "shutdown":
            self.shutdown = True
            _send(self.stdout, _response(message_id, None))
            return

        if method == "textDocument/documentSymbol":
            _send(
                self.stdout,
                _response(message_id, self._document_symbols(message)),
            )
            return

        if method == "textDocument/hover":
            _send(self.stdout, _response(message_id, self._hover(message)))
            return

        if method == "textDocument/definition":
            _send(self.stdout, _response(message_id, self._definition(message)))
            return

        if method == "textDocument/references":
            _send(self.stdout, _response(message_id, self._references(message)))
            return

        if method == "textDocument/documentHighlight":
            _send(
                self.stdout,
                _response(message_id, self._document_highlight(message)),
            )
            return

        if method == "textDocument/typeDefinition":
            _send(
                self.stdout,
                _response(message_id, self._type_definition(message)),
            )
            return

        if method == "textDocument/implementation":
            _send(
                self.stdout,
                _response(message_id, self._implementation(message)),
            )
            return

        if method == "textDocument/prepareTypeHierarchy":
            _send(
                self.stdout,
                _response(message_id, self._prepare_type_hierarchy(message)),
            )
            return

        if method == "typeHierarchy/supertypes":
            _send(
                self.stdout,
                _response(message_id, self._type_hierarchy_supertypes(message)),
            )
            return

        if method == "typeHierarchy/subtypes":
            _send(
                self.stdout,
                _response(message_id, self._type_hierarchy_subtypes(message)),
            )
            return

        if method == "textDocument/completion":
            _send(self.stdout, _response(message_id, self._completion(message)))
            return

        if method == "textDocument/signatureHelp":
            _send(
                self.stdout,
                _response(message_id, self._signature_help(message)),
            )
            return

        if method == "textDocument/formatting":
            _send(self.stdout, _response(message_id, self._formatting(message)))
            return

        if method == "workspace/symbol":
            _send(
                self.stdout,
                _response(message_id, self._workspace_symbols(message)),
            )
            return

        if method == "workspace/willRenameFiles":
            _send(
                self.stdout,
                _response(message_id, self._will_rename_files(message)),
            )
            return

        if method == "textDocument/codeAction":
            _send(
                self.stdout,
                _response(message_id, self._code_action(message)),
            )
            return

        if method == "textDocument/prepareRename":
            _send(
                self.stdout,
                _response(message_id, self._prepare_rename(message)),
            )
            return

        if method == "textDocument/rename":
            result = self._rename(message)
            if isinstance(result, str):
                _send(self.stdout, _error(message_id, -32602, result))
            else:
                _send(self.stdout, _response(message_id, result))
            return

        if method == "textDocument/inlayHint":
            _send(
                self.stdout,
                _response(message_id, self._inlay_hint(message)),
            )
            return

        if method == "textDocument/semanticTokens/full":
            _send(
                self.stdout,
                _response(message_id, self._semantic_tokens(message)),
            )
            return

        _send(
            self.stdout,
            _error(message_id, -32601, f"Method not found: {method}"),
        )

    def _notification(self, method: str, params: object) -> None:
        if not isinstance(params, dict):
            return
        if method == "workspace/didChangeConfiguration":
            self._apply_settings(params.get("settings"))
            return
        if method == "textDocument/didOpen":
            document = params.get("textDocument")
            if isinstance(document, dict):
                self._open(document)
        elif method == "textDocument/didChange":
            self._change(params)
        elif method == "textDocument/didSave":
            self._publish(params.get("textDocument"))
        elif method == "textDocument/didClose":
            document = params.get("textDocument")
            if isinstance(document, dict) and isinstance(document.get("uri"), str):
                uri = document["uri"]
                closed = self.documents.pop(uri, None)
                self.indexes.pop(uri, None)
                self.dependencies.pop(uri, None)
                _send(
                    self.stdout,
                    _notification(
                        "textDocument/publishDiagnostics",
                        {"uri": uri, "diagnostics": []},
                    ),
                )
                if closed is not None and closed.path is not None:
                    self._recheck_dependents(closed.path, skip_uri=uri)

    # -- documentos ------------------------------------------------------

    def _open(self, document: dict[str, Any]) -> None:
        uri = document.get("uri")
        text = document.get("text")
        version = document.get("version", 0)
        if not isinstance(uri, str) or not isinstance(text, str):
            return
        path = _uri_to_path(uri)
        self.documents[uri] = Document(
            text=text,
            version=version if isinstance(version, int) else 0,
            path=path,
            uri=uri,
        )
        self.indexes.pop(uri, None)
        self._publish_by_uri(uri)

    def _change(self, params: dict[str, Any]) -> None:
        document = params.get("textDocument")
        changes = params.get("contentChanges")
        if not isinstance(document, dict) or not isinstance(changes, list):
            return
        uri = document.get("uri")
        if not isinstance(uri, str):
            return
        current = self.documents.get(uri)
        if current is None or not changes:
            return
        change = changes[0]
        if not isinstance(change, dict) or not isinstance(change.get("text"), str):
            return
        version = document.get("version", current.version)
        current.text = change["text"]
        if isinstance(version, int):
            current.version = version
        self.indexes.pop(uri, None)
        self._publish_by_uri(uri)
        if current.path is not None:
            self._recheck_dependents(current.path, skip_uri=uri)

    def _recheck_dependents(self, path: Path, *, skip_uri: str) -> None:
        """Recheca documentos abertos cujo import closure inclui o módulo alterado.

        O loader lê o texto não salvo via `module_overrides` (ADR-0090, limitação
        declarada); a ordem publica o documento alterado primeiro e os importadores
        depois, para o editor não mostrar um diagnóstico velho.
        """
        changed = path.resolve()
        for uri, dependencies in list(self.dependencies.items()):
            if uri == skip_uri or changed not in dependencies:
                continue
            self.indexes.pop(uri, None)
            self._publish_by_uri(uri)

    def _publish(self, document: object) -> None:
        if isinstance(document, dict) and isinstance(document.get("uri"), str):
            self._publish_by_uri(document["uri"])

    def _publish_by_uri(self, uri: str) -> None:
        document = self.documents.get(uri)
        if document is None:
            return
        _send(
            self.stdout,
            _notification(
                "textDocument/publishDiagnostics",
                {
                    "uri": uri,
                    "version": document.version,
                    "diagnostics": self._diagnostics(document),
                },
            ),
        )

    # -- diagnóstico -----------------------------------------------------

    def _diagnostics(self, document: Document) -> list[dict[str, object]]:
        lox = Loxia(error_format="json", color="never", max_errors=0)
        if document.path is not None:
            lox.use_file(display_path(str(document.path)), module_root=document.path.parent)
        else:
            lox.use_file("<lsp>")
        overrides = {
            current.path.resolve(): current.text
            for current in self.documents.values()
            if current.path is not None
        }
        lox.check(document.text, emit=False, module_overrides=overrides)
        batch = lox.reporter.batch()
        sources = lox.sources
        self.source_maps[document.uri] = sources
        self.module_files[document.uri] = lox.module_files
        self.clean[document.uri] = not lox.reporter.had_error
        self.dependencies[document.uri] = frozenset(lox.watched_files)
        checker = lox.last_checker
        resolver = lox.last_resolver
        statements = lox.last_statements
        if statements is None and lox.last_recovered_statements:
            # Erro de sintaxe: o parser recuperou os statements anteriores (ADR-0113).
            # Sem checker: anotações e assinaturas valem; o corpo não é analisado.
            statements = lox.last_recovered_statements
            checker = None
            resolver = self._resolve_recovered(lox, statements)
        self.indexes[document.uri] = SymbolIndex(
            statements or [],
            source=document.text,
            checker=checker,
            resolver=resolver,
        )

        result: list[dict[str, object]] = []
        for diagnostic in batch.diagnostics:
            result.append(
                self._diagnostic(
                    diagnostic,
                    document=document,
                    lox=lox,
                    sources=sources,
                )
            )
        return result

    def _resolve_recovered(self, lox: Loxia, statements: list[Stmt]) -> Resolver | None:
        """Resolve escopos dos statements recuperados, sem misturar diagnósticos."""
        reporter = ErrorReporter(max_errors=0)
        resolver = Resolver(lox.interpreter, reporter, warn_unused=False)
        try:
            resolver.resolve(statements)
        except Exception:
            return None
        return resolver

    def _diagnostic(
        self,
        diagnostic: Diagnostic,
        *,
        document: Document,
        lox: Loxia,
        sources: object,
    ) -> dict[str, object]:
        span = diagnostic.span
        rng: dict[str, object]
        if span is None:
            source = document.text
            uri = document.uri
            rng = {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 0},
            }
        else:
            source = document.text
            uri = document.uri
            if span.file != lox._file:
                source = _source_for(sources, span.file, document.text)
                uri = self._uri_for_file(span.file, document)
            rng = _range(span, source)

        related = []
        for label in diagnostic.labels:
            label_source = _source_for(sources, label.span.file, source)
            label_uri = uri
            if span is not None and label.span.file != span.file:
                label_uri = self._uri_for_file(label.span.file, document)
            related.append(
                {
                    "location": {
                        "uri": label_uri,
                        "range": _range(label.span, label_source),
                    },
                    "message": label.message or "",
                }
            )

        data: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "phase": diagnostic.phase.value,
        }
        if diagnostic.help is not None:
            data["help"] = diagnostic.help
        if diagnostic.notes:
            data["notes"] = list(diagnostic.notes)
        if diagnostic.fixes:
            data["fixes"] = [
                {
                    "title": fix.message,
                    "applicability": fix.applicability.value,
                    "edits": [
                        {
                            "uri": edit_uri,
                            "range": _range(edit.span, edit_source),
                            "newText": edit.new_text,
                        }
                        for edit, (edit_uri, edit_source) in (
                            (edit, self._fix_target(edit, document, lox, sources))
                            for edit in fix.edits
                        )
                    ],
                }
                for fix in diagnostic.fixes
            ]
        if diagnostic.trace is not None:
            data["trace"] = {
                "frames": [
                    {
                        "name": frame.name,
                        "file": frame.file,
                        "line": frame.line,
                        "column": frame.column,
                    }
                    for frame in diagnostic.trace.frames
                ],
                "omitted": diagnostic.trace.omitted,
            }

        payload: dict[str, object] = {
            "range": rng,
            "severity": _severity(diagnostic.severity),
            "code": diagnostic.code.value,
            "source": "loxia",
            "message": diagnostic.message,
        }
        if diagnostic.code.value in _UNNECESSARY_CODES:
            # DiagnosticTag.Unnecessary: o editor apaga/apaga visualmente o nome sem
            # mudar severidade, mensagem ou exit code do CLI.
            payload["tags"] = [1]
        if related:
            payload["relatedInformation"] = related
        payload["data"] = data
        return payload

    def _fix_target(
        self,
        edit: object,
        document: Document,
        lox: Loxia,
        sources: object,
    ) -> tuple[str, str]:
        """Resolve URI e texto do arquivo de um `Edit` (mesmo mapa do span)."""
        span = edit.span  # type: ignore[attr-defined]
        if span.file == lox._file:
            return document.uri, document.text
        source = _source_for(sources, span.file, document.text)
        return self._uri_for_file(span.file, document), source

    def _rename_target(
        self, index: SymbolIndex, token: Token
    ) -> tuple[tuple[int, int, int], set[tuple[int, int, int]]] | None:
        """Só variáveis locais/parâmetros: `references` do resolver cobre esses casos."""
        key = token_key(token)
        declaration = index.references.get(key)
        if declaration is None:
            if key in index.references.values():
                declaration = key
            else:
                return None
        occurrences = {
            use
            for use, declaration_key in index.references.items()
            if declaration_key == declaration
        }
        occurrences.add(declaration)
        return declaration, occurrences

    def _tokens_by_key(self, text: str) -> dict[tuple[int, int, int], Token]:
        reporter = ErrorReporter(max_errors=0)
        return {token_key(token): token for token in Scanner(text, reporter).scan_tokens()}

    def _prepare_rename(self, message: dict[str, Any]) -> object:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        document = self._document(params)
        if document is None:
            return None
        token = self._token_at(document, params.get("position"))
        if token is None:
            return None
        index = self._index_for(document.uri)
        if index is None:
            return None
        tokens = self._tokens_by_key(document.text)
        local = self._rename_target(index, token)
        if local is not None and local[0] not in tokens:
            local = None
        if (
            local is None
            and not self._is_top_level(index, token)
            and self._semantic_target(document, token) is None
        ):
            return None
        return {
            "range": _token_range(token, document.text),
            "placeholder": token.lexeme,
        }

    def _semantic_target(self, document: Document, token: Token) -> object | None:
        if self.root is None or document.path is None:
            return None
        files = dict(self._workspace_files())
        return semantic_target(self.root, files, document.path, token)

    def _rename(self, message: dict[str, Any]) -> object:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        new_name = params.get("newName")
        if not isinstance(new_name, str) or not _valid_name(new_name):
            return "Invalid name."
        document = self._document(params)
        if document is None:
            return None
        token = self._token_at(document, params.get("position"))
        if token is None:
            return None
        index = self._index_for(document.uri)
        if index is None:
            return None
        tokens = self._tokens_by_key(document.text)
        target = self._rename_target(index, token)
        if target is not None and target[0] not in tokens:
            target = None
        if target is None:
            if self.root is not None and document.path is not None:
                files = dict(self._workspace_files())
                semantic = semantic_rename(self.root, files, document.path, token, new_name)
                if isinstance(semantic, str):
                    return semantic
                if semantic is not None:
                    return semantic
            if self._is_top_level(index, token):
                return self._workspace_rename(document, token, new_name)
            return "Rename is only supported for local variables, parameters and top-level declarations."
        _declaration, occurrences = target
        edits: list[dict[str, object]] = []
        for key in sorted(occurrences, key=lambda item: (item[0], item[1])):
            found = tokens.get(key)
            if found is None:
                continue
            edits.append(
                {
                    "range": _token_range(found, document.text),
                    "newText": new_name,
                }
            )
        if not edits:
            return None
        return {"changes": {document.uri: edits}}

    def _workspace_symbols(self, message: dict[str, Any]) -> list[dict[str, object]]:
        params = message.get("params")
        query = ""
        if isinstance(params, dict):
            raw_query = params.get("query")
            if isinstance(raw_query, str):
                query = raw_query.casefold()
        found: list[dict[str, object]] = []
        for path, text in self._workspace_files():
            reporter = ErrorReporter(max_errors=0)
            try:
                statements = Parser(
                    Scanner(text, reporter).scan_tokens(), reporter=reporter
                ).parse()
            except Exception:
                continue
            if reporter.had_error or statements is None:
                continue
            index = SymbolIndex(
                statements,
                source=text,
                checker=None,
                resolver=None,
            )
            uri = _path_to_uri(path)
            for symbol in index.symbols:
                if query and query not in symbol.name.casefold():
                    continue
                found.append(
                    {
                        "name": symbol.name,
                        "kind": _symbol_kind(symbol.kind),
                        "location": {
                            "uri": uri,
                            "range": _token_range(symbol.token, text),
                        },
                        **({"containerName": symbol.container} if symbol.container else {}),
                    }
                )

        def sort_key(item: dict[str, object]) -> tuple[str, str, int, int]:
            location = cast(dict[str, Any], item["location"])
            range_ = cast(dict[str, Any], location["range"])
            start_ = cast(dict[str, Any], range_["start"])
            return (
                str(item["name"]).casefold(),
                str(location["uri"]),
                int(start_["line"]),
                int(start_["character"]),
            )

        found.sort(key=sort_key)
        return found

    def _is_top_level(self, index: SymbolIndex, token: Token) -> bool:
        symbol = index.by_token.get(token_key(token))
        if symbol is None or symbol.container is not None:
            return False
        return symbol.kind in {
            "function",
            "class",
            "enum",
            "interface",
            "type",
            "variable",
        }

    def _workspace_files(self) -> list[tuple[Path, str]]:
        files: dict[Path, str] = {}
        for uri, document in self.documents.items():
            path = _uri_to_path(uri)
            if path is not None:
                files[path] = document.text
        if self.root is None:
            return sorted(files.items())
        try:
            candidates = self.root.rglob("*.lx")
        except OSError:
            candidates = iter(())
        for path in candidates:
            if any(part.startswith(".") or part in {"node_modules"} for part in path.parts):
                continue
            if path not in files:
                try:
                    files[path] = path.read_text(encoding="utf-8")
                except OSError:
                    continue
        return sorted(files.items())

    def _workspace_rename(self, document: Document, token: Token, new_name: str) -> object:
        old = token.lexeme
        if self.root is None:
            return "Cross-file rename requires an initialized workspace root."
        files = self._workspace_files()
        if not files:
            return "Cross-file rename requires an initialized workspace root."
        target_key = token_key(token)
        declarations = 0
        parsed: list[tuple[Path, str, list[Stmt], SymbolIndex]] = []
        for path, text in files:
            reporter = ErrorReporter(max_errors=0)
            parser = Parser(Scanner(text, reporter).scan_tokens(), reporter=reporter)
            statements = parser.parse()
            if reporter.had_error or statements is None:
                return f"Can't rename across files: parse error in {path.name}."
            index = SymbolIndex(
                statements,
                source=text,
                checker=None,
                resolver=None,
            )
            for symbol in index.symbols:
                if symbol.name != old:
                    continue
                if symbol.container is None and symbol.kind in {
                    "function",
                    "class",
                    "enum",
                    "interface",
                    "type",
                }:
                    declarations += 1
                    if token_key(symbol.token) != target_key or path != document.path:
                        continue
                else:
                    return (
                        f"Can't rename '{old}' across files: the name is also a "
                        f"{symbol.kind} in {path.name}."
                    )
            parsed.append((path, text, statements, index))
        if declarations != 1:
            return f"Can't rename '{old}' across files: ambiguous declaration."
        changes: dict[str, list[dict[str, object]]] = {}
        for path, text, statements, _index in parsed:
            skip: set[tuple[int, int, int]] = set()
            for statement in statements:
                if isinstance(statement, Import):
                    for part in statement.path:
                        skip.add(token_key(part))
            reporter = ErrorReporter(max_errors=0)
            edits: list[dict[str, object]] = [
                {
                    "range": _token_range(found, text),
                    "newText": new_name,
                }
                for found in Scanner(text, reporter).scan_tokens()
                if found.type is TokenType.IDENTIFIER
                and found.lexeme == old
                and token_key(found) not in skip
            ]
            if edits:
                changes[_path_to_uri(path)] = edits
        if not changes:
            return None
        return {"changes": changes}

    def _will_rename_files(self, message: dict[str, Any]) -> dict[str, object] | None:
        """`workspace/willRenameFiles`: reescreve imports quando um módulo muda de nome."""
        if self.root is None:
            return None
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        files = params.get("files")
        if not isinstance(files, list):
            return None
        renames: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            old_uri = item.get("oldUri")
            new_uri = item.get("newUri")
            if not isinstance(old_uri, str) or not isinstance(new_uri, str):
                continue
            old_path = _uri_to_path(old_uri)
            new_path = _uri_to_path(new_uri)
            if old_path is None or new_path is None:
                continue
            old_module = _module_of(old_path, self.root)
            new_module = _module_of(new_path, self.root)
            if old_module is None or new_module is None or old_module == new_module:
                continue
            renames.append((old_module, new_module))
        if not renames:
            return None

        changes: dict[str, list[dict[str, object]]] = {}
        for path, text in self._workspace_files():
            reporter = ErrorReporter(max_errors=0)
            try:
                statements = Parser(
                    Scanner(text, reporter).scan_tokens(), reporter=reporter
                ).parse()
            except Exception:
                continue
            if reporter.had_error or statements is None:
                continue
            edits: list[dict[str, object]] = []
            for statement in statements:
                if not isinstance(statement, Import) or not statement.path:
                    continue
                module = tuple(part.lexeme for part in statement.path)
                replacement = _rewrite_module(module, renames)
                if replacement is None:
                    continue
                first = statement.path[0]
                last = statement.path[-1]
                edits.append(
                    {
                        "range": _offset_span(
                            text,
                            first.offset,
                            last.offset + len(last.lexeme.encode("utf-8")),
                        ),
                        "newText": ".".join(replacement),
                    }
                )
            if edits:
                changes[_path_to_uri(path)] = edits
        if not changes:
            return None
        return {"changes": changes}

    def _document(self, params: dict[str, Any]) -> Document | None:
        text_document = params.get("textDocument")
        if not isinstance(text_document, dict):
            return None
        uri = text_document.get("uri")
        if not isinstance(uri, str):
            return None
        return self.documents.get(uri)

    def _code_action(self, message: dict[str, Any]) -> list[dict[str, object]]:
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        context = params.get("context")
        if not isinstance(context, dict):
            return []
        diagnostics = context.get("diagnostics")
        if not isinstance(diagnostics, list):
            return []
        raw_only = context.get("only")
        requested = (
            [item for item in raw_only if isinstance(item, str)]
            if isinstance(raw_only, list)
            else None
        )
        actions: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        quickfix_allowed = requested is None or any(
            _kind_matches(kind, "quickfix") for kind in requested
        )
        for diagnostic in diagnostics if quickfix_allowed else []:
            if not isinstance(diagnostic, dict):
                continue
            data = diagnostic.get("data")
            if not isinstance(data, dict):
                continue
            fixes = data.get("fixes")
            if not isinstance(fixes, list):
                continue
            for fix in fixes:
                if not isinstance(fix, dict):
                    continue
                edits = fix.get("edits")
                if not isinstance(edits, list):
                    continue
                changes: dict[str, list[dict[str, object]]] = {}
                for edit in edits:
                    if not isinstance(edit, dict):
                        continue
                    uri = edit.get("uri")
                    edit_range = edit.get("range")
                    new_text = edit.get("newText")
                    if (
                        not isinstance(uri, str)
                        or not isinstance(edit_range, dict)
                        or not isinstance(new_text, str)
                    ):
                        continue
                    changes.setdefault(uri, []).append({"range": edit_range, "newText": new_text})
                if not changes:
                    continue
                title = fix.get("title")
                if not isinstance(title, str):
                    title = "Fix"
                key = (title, json.dumps(changes, sort_keys=True))
                if key in seen:
                    continue
                seen.add(key)
                actions.append(
                    {
                        "title": title,
                        "kind": "quickfix",
                        "isPreferred": fix.get("applicability") == "safe",
                        "edit": {"changes": changes},
                        "diagnostics": [diagnostic],
                    }
                )

        if requested is not None and any(
            _kind_matches(kind, "source.fixAll.loxia") for kind in requested
        ):
            document = self._document(params)
            if document is not None:
                fix_all = self._fix_all(document)
                if fix_all is not None:
                    actions.append(fix_all)
        return actions

    def _fix_all(self, document: Document) -> dict[str, object] | None:
        """Aplica todos os fixes `safe` do documento como uma edição só."""
        changes: dict[str, list[dict[str, object]]] = {}
        for diagnostic in self._diagnostics(document):
            data = diagnostic.get("data")
            if not isinstance(data, dict):
                continue
            fixes = data.get("fixes")
            if not isinstance(fixes, list):
                continue
            for fix in fixes:
                if not isinstance(fix, dict) or fix.get("applicability") != "safe":
                    continue
                edits = fix.get("edits")
                if not isinstance(edits, list):
                    continue
                for edit in edits:
                    if not isinstance(edit, dict):
                        continue
                    uri = edit.get("uri")
                    edit_range = edit.get("range")
                    new_text = edit.get("newText")
                    if (
                        not isinstance(uri, str)
                        or not isinstance(edit_range, dict)
                        or not isinstance(new_text, str)
                    ):
                        continue
                    changes.setdefault(uri, []).append({"range": edit_range, "newText": new_text})
        overlaps = False
        merged: dict[str, list[dict[str, object]]] = {}
        for uri, entries in changes.items():
            ordered = sorted(entries, key=lambda item: _range_key(item["range"]))
            kept: list[dict[str, object]] = []
            last_end: tuple[int, int] | None = None
            for entry in ordered:
                start, end = _range_key(entry["range"])
                if last_end is not None and start < last_end:
                    overlaps = True
                    break
                kept.append(entry)
                last_end = end
            if overlaps:
                break
            merged[uri] = kept
        if overlaps or not merged:
            return None
        return {
            "title": "Fix all safe fixes",
            "kind": "source.fixAll.loxia",
            "isPreferred": False,
            "edit": {"changes": merged},
        }

    # -- hover/definition ------------------------------------------------

    def _index_for(self, uri: str) -> SymbolIndex | None:
        index = self.indexes.get(uri)
        if index is not None:
            return index
        document = self.documents.get(uri)
        if document is None:
            return None
        self._diagnostics(document)
        return self.indexes.get(uri)

    def _token_at(self, document: Document, position: object) -> Token | None:
        if not isinstance(position, dict):
            return None
        line = position.get("line")
        character = position.get("character")
        if not isinstance(line, int) or not isinstance(character, int):
            return None
        lines = document.text.splitlines()
        if line < 0 or line >= len(lines):
            return None
        line_text = lines[line]
        units = 0
        column = 1
        for char in line_text:
            width = len(char.encode("utf-16-le")) // 2
            if units >= character:
                break
            units += width
            column += 1

        reporter = ErrorReporter(max_errors=0)
        tokens = Scanner(document.text, reporter).scan_tokens()
        for token in tokens:
            if token.line != line + 1:
                continue
            end = (token.column or 1) + len(token.lexeme)
            if (token.column or 1) <= column < end and token.type in (
                TokenType.IDENTIFIER,
                TokenType.THIS,
                TokenType.SUPER,
            ):
                return token
        return None

    def _hover(self, message: dict[str, Any]) -> dict[str, object] | None:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        document_info = params.get("textDocument")
        if not isinstance(document_info, dict):
            return None
        uri = document_info.get("uri")
        if not isinstance(uri, str):
            return None
        document = self.documents.get(uri)
        if document is None:
            return None
        token = self._token_at(document, params.get("position"))
        if token is None:
            return None
        index = self._index_for(uri)
        if index is None:
            return None

        symbol = index.symbol_at(token)
        ty = index.type_at(token) or (symbol.type if symbol is not None else None)
        parts: list[str] = []
        if symbol is not None:
            parts.append(f"```lox\n{symbol.signature}\n```")
            if symbol.doc:
                parts.append(symbol.doc)
        elif ty is not None:
            parts.append(f"```lox\n{display_source_type(ty)}\n```")
        else:
            return None

        return {
            "contents": {"kind": "markdown", "value": "\n\n".join(parts)},
            "range": _token_range(token, document.text),
        }

    def _definition(self, message: dict[str, Any]) -> dict[str, object] | None:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        document_info = params.get("textDocument")
        if not isinstance(document_info, dict):
            return None
        uri = document_info.get("uri")
        if not isinstance(uri, str):
            return None
        document = self.documents.get(uri)
        if document is None:
            return None
        token = self._token_at(document, params.get("position"))
        if token is None:
            return None
        index = self._index_for(uri)
        if index is None:
            return None
        symbol = index.reference_target(token)
        if symbol is None:
            return self._module_definition(document, token)

        target_uri = self._uri_for_token(symbol.token, document)
        target_source = document.text
        if (
            symbol.token.file
            and document.path is not None
            and symbol.token.file != document.path.name
        ):
            target_source = _source_for(self.source_maps.get(uri), symbol.token.file, document.text)
        return {
            "uri": target_uri,
            "range": _token_range(symbol.token, target_source),
        }

    def _module_definition(self, document: Document, token: Token) -> dict[str, object] | None:
        """Import/alias fora do `SymbolIndex`: resolve o arquivo do módulo."""
        if document.path is None:
            return None
        statements = parse_for_completion(document.text, len(document.text))
        if statements is None:
            return None
        context = SourceContext(statements, document.path)
        imported = context.imports.get(token.lexeme)
        if imported is None:
            return None
        module_file = self.module_files.get(document.uri, {}).get(
            ModuleLoader.display_path(imported.module)
        )
        if module_file is None:
            return None
        if imported.public is not None:
            found = context.declaration_with_context(token.lexeme)
            if found is not None:
                statement, module_context = found
                name_token = getattr(statement, "name", None)
                if isinstance(name_token, Token) and module_context.path is not None:
                    try:
                        text = module_context.path.read_text(encoding="utf-8")
                    except OSError:
                        text = ""
                    return {
                        "uri": _path_to_uri(module_context.path),
                        "range": _token_range(name_token, text),
                    }
        return {
            "uri": _path_to_uri(module_file),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 0},
            },
        }

    # -- referências, tipos e hierarquia ---------------------------------

    def _references(self, message: dict[str, Any]) -> list[dict[str, object]]:
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        document = self._document(params)
        if document is None:
            return []
        token = self._token_at(document, params.get("position"))
        if token is None:
            return []
        index = self._index_for(document.uri)
        if index is None:
            return []
        context = params.get("context")
        include_declaration = True
        if isinstance(context, dict):
            include_declaration = context.get("includeDeclaration", True) is not False
        locations: list[dict[str, object]] = []

        local = self._rename_target(index, token)
        tokens = self._tokens_by_key(document.text)
        if local is not None and local[0] in tokens:
            declaration, occurrences = local
            for key in sorted(occurrences, key=lambda item: (item[0], item[1], item[2])):
                found = tokens.get(key)
                if found is None:
                    continue
                if not include_declaration and key == declaration:
                    continue
                locations.append({"uri": document.uri, "range": _token_range(found, document.text)})
        elif self.root is not None and document.path is not None:
            files = dict(self._workspace_files())
            references = semantic_references(self.root, files, document.path, token)
            if references is None:
                return []
            declaration_path, declaration_offset = references.declaration
            for path, offset, name in references.occurrences:
                if not include_declaration and (
                    path.resolve() == declaration_path.resolve() and offset == declaration_offset
                ):
                    continue
                text = files.get(path)
                if text is None:
                    try:
                        text = path.read_text(encoding="utf-8")
                    except OSError:
                        continue
                locations.append(
                    {
                        "uri": _path_to_uri(path),
                        "range": _offset_range(text, offset, name),
                    }
                )

        locations.sort(
            key=lambda item: (
                str(item["uri"]),
                cast(dict[str, Any], item["range"])["start"]["line"],
                cast(dict[str, Any], item["range"])["start"]["character"],
            )
        )
        return locations

    def _document_highlight(self, message: dict[str, Any]) -> list[dict[str, object]]:
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        document = self._document(params)
        if document is None:
            return []
        token = self._token_at(document, params.get("position"))
        if token is None:
            return []
        index = self._index_for(document.uri)
        if index is None:
            return []
        highlights: list[dict[str, object]] = []

        local = self._rename_target(index, token)
        tokens = self._tokens_by_key(document.text)
        if local is not None and local[0] in tokens:
            declaration, occurrences = local
            for key in sorted(occurrences, key=lambda item: (item[0], item[1], item[2])):
                found = tokens.get(key)
                if found is None:
                    continue
                highlights.append(
                    {
                        "range": _token_range(found, document.text),
                        "kind": 3 if key == declaration else 2,
                    }
                )
        elif self.root is not None and document.path is not None:
            files = dict(self._workspace_files())
            references = semantic_references(self.root, files, document.path, token)
            if references is None:
                return []
            declaration_path, declaration_offset = references.declaration
            for path, offset, name in references.occurrences:
                if path.resolve() != document.path.resolve():
                    continue
                highlights.append(
                    {
                        "range": _offset_range(document.text, offset, name),
                        "kind": 3
                        if offset == declaration_offset
                        and path.resolve() == declaration_path.resolve()
                        else 2,
                    }
                )
        return highlights

    def _type_definition(self, message: dict[str, Any]) -> object | None:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        document = self._document(params)
        if document is None:
            return None
        token = self._token_at(document, params.get("position"))
        if token is None:
            return None
        index = self._index_for(document.uri)
        if index is None:
            return None
        symbol = index.symbol_at(token)
        ty = index.type_at(token) or (symbol.type if symbol is not None else None)
        names = _type_names(ty)
        if not names and symbol is not None:
            name = symbol.name.rsplit("$", 1)[-1]
            if symbol.container is None and symbol.kind in {"class", "enum", "interface", "type"}:
                names = [name]
        if not names:
            return None
        declarations, texts = self._type_declarations()
        targets: list[dict[str, object]] = []
        for name in names:
            declaration = _find_type(name, declarations, document.path)
            if declaration is None:
                continue
            text = texts.get(declaration.path, "")
            targets.append(
                {
                    "uri": _path_to_uri(declaration.path),
                    "range": _token_range(declaration.token, text),
                }
            )
        if not targets:
            return None
        return targets[0] if len(targets) == 1 else targets

    def _implementation(self, message: dict[str, Any]) -> object | None:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        document = self._document(params)
        if document is None:
            return None
        token = self._token_at(document, params.get("position"))
        if token is None:
            return None
        index = self._index_for(document.uri)
        if index is None:
            return None
        symbol = index.symbol_at(token) or index.reference_target(token)
        name = symbol.name.rsplit("$", 1)[-1] if symbol is not None else token.lexeme
        declarations, texts = self._type_declarations()
        declaration = _find_type(name, declarations, document.path)
        if declaration is None:
            return None
        targets = [
            {
                "uri": _path_to_uri(item.path),
                "range": _token_range(item.token, texts.get(item.path, "")),
            }
            for item in _implementors(declaration, declarations)
        ]
        if not targets:
            return None
        return targets[0] if len(targets) == 1 else targets

    def _prepare_type_hierarchy(self, message: dict[str, Any]) -> list[dict[str, object]]:
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        document = self._document(params)
        if document is None:
            return []
        token = self._token_at(document, params.get("position"))
        if token is None:
            return []
        declarations, texts = self._type_declarations()
        declaration = next(
            (
                item
                for item in declarations
                if document.path is not None
                and item.path.resolve() == document.path.resolve()
                and item.token.line == token.line
                and item.token.column == token.column
            ),
            None,
        )
        if declaration is None:
            declaration = _find_type(token.lexeme, declarations, document.path)
        if declaration is None:
            return []
        return [_type_hierarchy_item(declaration, texts.get(declaration.path, ""))]

    def _type_hierarchy_supertypes(self, message: dict[str, Any]) -> list[dict[str, object]]:
        declaration = self._type_hierarchy_target(message)
        if declaration is None:
            return []
        declarations, texts = self._type_declarations()
        names = ([declaration.superclass] if declaration.superclass else []) + list(
            declaration.interfaces
        )
        items: list[dict[str, object]] = []
        for name in names:
            found = _find_type(name, declarations, declaration.path)
            if found is not None:
                items.append(_type_hierarchy_item(found, texts.get(found.path, "")))
        return items

    def _type_hierarchy_subtypes(self, message: dict[str, Any]) -> list[dict[str, object]]:
        declaration = self._type_hierarchy_target(message)
        if declaration is None:
            return []
        declarations, texts = self._type_declarations()
        return [
            _type_hierarchy_item(item, texts.get(item.path, ""))
            for item in _subtypes(declaration, declarations)
        ]

    def _type_hierarchy_target(self, message: dict[str, Any]) -> TypeDecl | None:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        item = params.get("item")
        if not isinstance(item, dict):
            return None
        data = item.get("data")
        name: str | None = None
        path: Path | None = None
        if isinstance(data, dict):
            raw_name = data.get("name")
            raw_path = data.get("path")
            if isinstance(raw_name, str):
                name = raw_name
            if isinstance(raw_path, str):
                path = Path(raw_path)
        if name is None:
            raw = item.get("name")
            if isinstance(raw, str):
                name = raw
        declarations, _texts = self._type_declarations()
        if name is None:
            return None
        if path is None:
            return _find_type(name, declarations, None)
        for declaration in declarations:
            if declaration.path.resolve() == path.resolve() and declaration.name == name:
                return declaration
        return None

    def _type_declarations(self) -> tuple[list[TypeDecl], dict[Path, str]]:
        declarations: list[TypeDecl] = []
        texts: dict[Path, str] = {}
        for path, text in self._workspace_files():
            texts[path] = text
            reporter = ErrorReporter(max_errors=0)
            try:
                statements = Parser(
                    Scanner(text, reporter).scan_tokens(), reporter=reporter
                ).parse()
            except Exception:
                continue
            if reporter.had_error or statements is None:
                continue
            declarations.extend(_type_declarations_of(statements, path))
        return declarations, texts

    # -- completion/signature/format/semantic ----------------------------

    def _line_text(self, document: Document, line: int) -> str | None:
        lines = document.text.splitlines()
        if 0 <= line < len(lines):
            return lines[line]
        return None

    def _character_to_column(self, line_text: str, character: int) -> int:
        units = 0
        column = 1
        for char in line_text:
            width = len(char.encode("utf-16-le")) // 2
            if units >= character:
                break
            units += width
            column += 1
        return column

    def _offset_at(self, text: str, line: int, character: int) -> int:
        lines = text.split("\n")
        if line < 0 or line >= len(lines):
            return len(text.encode("utf-8"))
        column = self._character_to_column(lines[line], character)
        prefix = "\n".join(lines[:line]) + ("\n" if line else "")
        return len((prefix + lines[line][: max(0, column - 1)]).encode("utf-8"))

    def _completion(self, message: dict[str, Any]) -> dict[str, object]:
        empty: dict[str, object] = {"isIncomplete": False, "items": []}
        params = message.get("params")
        if not isinstance(params, dict):
            return empty
        document_info = params.get("textDocument")
        position = params.get("position")
        if not isinstance(document_info, dict) or not isinstance(position, dict):
            return empty
        uri = document_info.get("uri")
        line = position.get("line")
        character = position.get("character")
        if not isinstance(uri, str) or not isinstance(line, int) or not isinstance(character, int):
            return empty
        document = self.documents.get(uri)
        if document is None:
            return empty
        index = self._index_for(uri)
        offset = self._offset_at(document.text, line, character)
        return {
            "isIncomplete": False,
            "items": completion_items(
                document.text,
                document.path,
                offset,
                index,
                inherited_members=self.inherited_members,
            ),
        }

    def _signature_help(self, message: dict[str, Any]) -> dict[str, object] | None:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        document_info = params.get("textDocument")
        if not isinstance(document_info, dict):
            return None
        uri = document_info.get("uri")
        position = params.get("position")
        if not isinstance(uri, str) or not isinstance(position, dict):
            return None
        document = self.documents.get(uri)
        if document is None:
            return None
        line = position.get("line")
        character = position.get("character")
        if not isinstance(line, int) or not isinstance(character, int):
            return None
        line_text = self._line_text(document, line)
        if line_text is None:
            return None
        column = self._character_to_column(line_text, character)
        prefix = line_text[: max(0, column - 1)]
        open_paren = prefix.rfind("(")
        if open_paren < 0:
            return None
        before = prefix[:open_paren]
        match = re.search(
            r"([A-Za-z_][A-Za-z0-9_]*(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*)*)\s*$",
            before,
        )
        if match is None:
            return None
        callee = match.group(1).replace(" ", "")
        parts = callee.split(".")
        name = parts[-1]
        offset = self._offset_at(document.text, line, character)
        statements = parse_for_completion(document.text, offset)
        signature = None
        if statements is not None:
            context = SourceContext(statements, document.path)
            if len(parts) == 1:
                signature = context.function_signature(name)
            else:
                receiver = ".".join(parts[:-1])
                signature = self._member_signature(
                    context,
                    statements,
                    document,
                    line,
                    before,
                    match.start(1),
                    receiver,
                    name,
                    offset,
                    uri,
                )
        if signature is None:
            builtin = next((item for item in BUILTIN_DOCS if item.name == name), None)
            if builtin is None:
                return None
            signature = builtin.signature

        start_paren = signature.find("(")
        end_paren = signature.rfind(")")
        if start_paren < 0 or end_paren <= start_paren:
            return None
        parameters = _split_parameters(signature[start_paren + 1 : end_paren])
        active = prefix[open_paren + 1 :].count(",")
        active = min(active, max(0, len(parameters) - 1))
        return {
            "signatures": [
                {
                    "label": signature,
                    "parameters": [{"label": item} for item in parameters],
                }
            ],
            "activeSignature": 0,
            "activeParameter": active,
        }

    def _member_signature(
        self,
        context: SourceContext,
        statements: list[Stmt],
        document: Document,
        line: int,
        before: str,
        start: int,
        receiver: str,
        name: str,
        offset: int,
        uri: str,
    ) -> str | None:
        imported = context.imports.get(receiver)
        if imported is not None and imported.public is None:
            return context.namespace_signature(receiver, name)

        last = receiver.rsplit(".", 1)[-1]
        last_start = before.rfind(last, start, start + len(receiver) + 1)
        token_character = len(before[:last_start].encode("utf-16-le")) // 2
        token = self._token_at(document, {"line": line, "character": token_character})
        ty = None
        if token is not None:
            index = self._index_for(uri)
            if index is not None:
                ty = index.type_at(token)
        if ty is None:
            ty = completion_declared_type(statements, last)
        if receiver in {"this", "super"}:
            _function, klass = completion_context(statements, offset)
            if klass is not None:
                target = klass if receiver == "this" else completion_superclass(statements, klass)
                if target is not None:
                    return context.method_signature(target, name)
        if ty is not None:
            return context.method_signature(ty, name)
        return None

    def _inlay_hint(self, message: dict[str, Any]) -> list[dict[str, object]]:
        if not self.inlay_hints:
            return []
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        document_info = params.get("textDocument")
        if not isinstance(document_info, dict):
            return []
        uri = document_info.get("uri")
        if not isinstance(uri, str):
            return []
        document = self.documents.get(uri)
        if document is None:
            return []
        index = self._index_for(uri)
        if index is None or not self.clean.get(uri, False):
            return []
        hints: list[dict[str, object]] = []
        for symbol in index.symbols:
            if symbol.kind not in {"variable", "field"}:
                continue
            if symbol.annotated or symbol.type is None:
                continue
            if not self._symbol_in_document(symbol, document):
                continue
            label = display_source_type(symbol.type)
            if label == "Any":
                continue
            position = self._after_name_position(document, symbol)
            if position is None:
                continue
            hints.append(
                {
                    "position": position,
                    "label": f": {label}",
                    "kind": 1,
                    "paddingLeft": False,
                }
            )
        hints.sort(
            key=lambda item: (
                cast(dict[str, int], item["position"])["line"],
                cast(dict[str, int], item["position"])["character"],
            )
        )
        return hints

    def _symbol_in_document(self, symbol: Symbol, document: Document) -> bool:
        if not symbol.token.file:
            return True
        if document.path is None:
            return True
        token_path = self._file_path(symbol.token.file, document)
        if token_path is None:
            return False
        try:
            return token_path.resolve() == document.path.resolve()
        except OSError:
            return False

    def _after_name_position(self, document: Document, symbol: Symbol) -> dict[str, int] | None:
        data = document.text.encode("utf-8")
        tail = data[symbol.token.offset :].decode("utf-8")
        match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", tail)
        if match is None:
            return None
        end = symbol.token.offset + len(match.group(0).encode("utf-8"))
        prefix = data[:end].decode("utf-8")
        line = prefix.count("\n")
        last = prefix.rsplit("\n", 1)[-1]
        character = len(last.encode("utf-16-le")) // 2
        return {"line": line, "character": character}

    def _formatting(self, message: dict[str, Any]) -> list[dict[str, object]]:
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        document_info = params.get("textDocument")
        if not isinstance(document_info, dict):
            return []
        uri = document_info.get("uri")
        if not isinstance(uri, str):
            return []
        document = self.documents.get(uri)
        if document is None:
            return []
        result = format_source(document.text, reporter=ErrorReporter(max_errors=0))
        if result is None or not result.changed:
            return []
        return [
            {
                "range": {
                    "start": _position_at(document.text, edit.start.offset),
                    "end": _position_at(document.text, edit.end.offset),
                },
                "newText": edit.new_text,
            }
            for edit in build_edits(document.text, result.text)
        ]

    def _semantic_tokens(self, message: dict[str, Any]) -> dict[str, object]:
        params = message.get("params")
        if not isinstance(params, dict):
            return {"data": []}
        document_info = params.get("textDocument")
        if not isinstance(document_info, dict):
            return {"data": []}
        uri = document_info.get("uri")
        if not isinstance(uri, str):
            return {"data": []}
        document = self.documents.get(uri)
        if document is None:
            return {"data": []}
        index = self._index_for(uri)
        if index is None:
            return {"data": []}
        tokens = Scanner(document.text, ErrorReporter(max_errors=0)).scan_tokens()
        data: list[int] = []
        previous_line = 0
        previous_character = 0
        for token in tokens:
            if token.type is TokenType.EOF or "\n" in token.lexeme:
                continue
            semantic = _semantic_type(token, index)
            if semantic is None or not token.lexeme:
                continue
            line = token.line - 1
            line_text = self._line_text(document, line) or ""
            character = _utf16_column(line_text, token.column)
            length = len(token.lexeme.encode("utf-16-le")) // 2
            if line < previous_line or (line == previous_line and character < previous_character):
                continue
            delta_line = line - previous_line
            delta_character = character if delta_line else character - previous_character
            data.extend(
                [
                    delta_line,
                    delta_character,
                    length,
                    SEMANTIC_TOKEN_TYPES.index(semantic),
                    0,
                ]
            )
            previous_line = line
            previous_character = character
        return {"data": data}

    def _file_path(self, file: str, document: Document) -> Path | None:
        """Caminho absoluto de um `token.file` lógico (`std/io.lx`, `lib/x.lx`)."""
        if document.path is not None and file == display_path(str(document.path)):
            return document.path
        mapped = self.module_files.get(document.uri, {}).get(file)
        if mapped is not None:
            return mapped
        path = Path(file)
        if path.is_absolute():
            return path
        candidates: list[Path] = []
        if self.root is not None:
            candidates.append(self.root / path)
        if document.path is not None:
            candidates.append(document.path.parent / path)
        if file.startswith("std/"):
            candidates.append(bundle_dir("std") / path.relative_to("std"))
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0] if candidates else None

    def _uri_for_file(self, file: str, document: Document) -> str:
        path = self._file_path(file, document)
        return document.uri if path is None else _path_to_uri(path)

    def _uri_for_token(self, token: Token, document: Document) -> str:
        if not token.file or document.path is None:
            return document.uri
        if token.file == display_path(str(document.path)):
            return document.uri
        return self._uri_for_file(token.file, document)

    # -- símbolos --------------------------------------------------------

    def _document_symbols(self, message: dict[str, Any]) -> list[dict[str, object]]:
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        document = params.get("textDocument")
        if not isinstance(document, dict) or not isinstance(document.get("uri"), str):
            return []
        current = self.documents.get(document["uri"])
        if current is None:
            return []

        reporter = ErrorReporter(max_errors=0)
        scanner = Scanner(current.text, reporter)
        tokens = scanner.scan_tokens()
        statements = Parser(tokens, reporter=reporter).parse()
        if reporter.had_error or statements is None:
            return []
        return [
            symbol for statement in statements for symbol in _symbols_for(statement, current.text)
        ]


def _split_parameters(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _semantic_type(token: Token, index: SymbolIndex) -> str | None:
    if token.lexeme in KEYWORDS:
        return "keyword"
    if token.type in (TokenType.STRING, TokenType.INTERPOLATED_STRING):
        return "string"
    if token.type is TokenType.NUMBER:
        return "number"
    if token.type.name in _OPERATOR_TYPES:
        return "operator"
    if token.type in (TokenType.THIS, TokenType.SUPER):
        return "keyword"
    if token.type is not TokenType.IDENTIFIER:
        return None

    symbol = index.symbol_at(token)
    if symbol is None:
        return "variable"
    return {
        "class": "class",
        "interface": "interface",
        "enum": "enum",
        "variant": "enum",
        "function": "function",
        "method": "method",
        "field": "property",
        "variable": "variable",
        "type": "type",
    }.get(symbol.kind, "variable")


def _source_for(sources: object, file: str, fallback: str) -> str:
    get = getattr(sources, "get", None)
    if callable(get):
        source = get(file)
        text = getattr(source, "text", None)
        if isinstance(text, str):
            return text
    return fallback


def _range_for_token(token: Token, source: str) -> dict[str, object]:
    return _token_range(token, source)


def _symbol(
    *,
    name: str,
    kind: str,
    token: Token,
    source: str,
    children: list[dict[str, object]] | None = None,
    detail: str | None = None,
) -> dict[str, object]:
    rng = _range_for_token(token, source)
    payload: dict[str, object] = {
        "name": name,
        "kind": SYMBOL_KINDS[kind],
        "range": rng,
        "selectionRange": rng,
    }
    if detail:
        payload["detail"] = detail
    if children:
        payload["children"] = children
    return payload


def _summary(doc: str | None) -> str | None:
    if not doc:
        return None
    return doc.splitlines()[0]


def _symbols_for(statement: Stmt, source: str) -> list[dict[str, object]]:
    if isinstance(statement, Function):
        return [
            _symbol(
                name=statement.name.lexeme,
                kind="function",
                token=statement.name,
                source=source,
                detail=_summary(statement.doc),
            )
        ]

    if isinstance(statement, Class):
        children = [
            _symbol(
                name=field.name.lexeme,
                kind="field",
                token=field.name,
                source=source,
                detail=_summary(field.doc),
            )
            for field in statement.fields
        ]
        children.extend(
            _symbol(
                name=method.name.lexeme,
                kind="method",
                token=method.name,
                source=source,
                detail=_summary(method.doc),
            )
            for method in statement.methods
        )
        return [
            _symbol(
                name=statement.name.lexeme,
                kind="class",
                token=statement.name,
                source=source,
                children=children,
                detail=_summary(statement.doc),
            )
        ]

    if isinstance(statement, Interface):
        children = [
            _symbol(
                name=method.name.lexeme,
                kind="method",
                token=method.name,
                source=source,
                detail=_summary(method.doc),
            )
            for method in statement.methods
        ]
        return [
            _symbol(
                name=statement.name.lexeme,
                kind="interface",
                token=statement.name,
                source=source,
                children=children,
                detail=_summary(statement.doc),
            )
        ]

    if isinstance(statement, EnumDecl):
        children = [
            _symbol(
                name=variant.name.lexeme,
                kind="variant",
                token=variant.name,
                source=source,
                detail=_summary(variant.doc),
            )
            for variant in statement.variants
        ]
        return [
            _symbol(
                name=statement.name.lexeme,
                kind="enum",
                token=statement.name,
                source=source,
                children=children,
                detail=_summary(statement.doc),
            )
        ]

    if isinstance(statement, TypeAlias):
        return [
            _symbol(
                name=statement.name.lexeme,
                kind="type",
                token=statement.name,
                source=source,
                detail=_summary(statement.doc),
            )
        ]

    if isinstance(statement, Var):
        return [
            _symbol(
                name=statement.name.lexeme,
                kind="variable",
                token=statement.name,
                source=source,
                detail=_summary(statement.doc),
            )
        ]

    return []


def main() -> int:
    server = Server(sys.stdin.buffer, sys.stdout.buffer)
    try:
        return server.run()
    except KeyboardInterrupt:
        return 0


def _valid_name(name: str) -> bool:
    if not name or not name.isascii():
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    if not all(char.isalnum() or char == "_" for char in name):
        return False
    return name not in {
        "and",
        "as",
        "class",
        "elif",
        "else",
        "enum",
        "false",
        "fn",
        "for",
        "from",
        "if",
        "implements",
        "import",
        "in",
        "interface",
        "is",
        "match",
        "nil",
        "not",
        "or",
        "raise",
        "return",
        "super",
        "this",
        "true",
        "try",
        "except",
        "finally",
        "type",
        "val",
        "var",
        "while",
    }


def _symbol_kind(kind: str) -> int:
    """Mapeia o kind do SymbolIndex para o SymbolKind do LSP."""
    return {
        "class": 5,
        "method": 6,
        "field": 8,
        "enum": 10,
        "interface": 11,
        "function": 12,
        "variable": 13,
        "variant": 22,
        "type": 26,
    }.get(kind, 13)
