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
from loxia.cli import Loxia
from loxia.completion import complete as completion_items
from loxia.formatter import format_source
from loxia.symbols import SymbolIndex, token_key
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
from loxia_core.frontend.ty import display

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
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def _response(message_id: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": message_id, "result": result}


def _error(
    message_id: object, code: int, message: str
) -> dict[str, Any]:
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


def _position(
    line: int, column: int | None, source: str
) -> dict[str, int]:
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


def _severity(severity: Severity) -> int:
    return 1 if severity is Severity.ERROR else 2


class Server:
    def __init__(self, stdin: IO[bytes], stdout: IO[bytes]) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.documents: dict[str, Document] = {}
        self.indexes: dict[str, SymbolIndex] = {}
        self.source_maps: dict[str, object] = {}
        self.root: Path | None = None
        self.shutdown = False

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
        if method == "initialize":
            params = message.get("params")
            if isinstance(params, dict):
                root_uri = params.get("rootUri")
                if isinstance(root_uri, str):
                    self.root = _uri_to_path(root_uri)
            _send(
                self.stdout,
                _response(
                    message_id,
                    {
                        "capabilities": {
                            "textDocumentSync": 1,
                            "hoverProvider": True,
                            "definitionProvider": True,
                            "workspaceSymbolProvider": True,
                            "renameProvider": {"prepareProvider": True},
                            "documentSymbolProvider": True,
                            "completionProvider": {
                                "triggerCharacters": [".", ":"],
                                "resolveProvider": False,
                            },
                            "signatureHelpProvider": {
                                "triggerCharacters": ["(", ","]
                            },
                            "documentFormattingProvider": True,
                            "codeActionProvider": True,
                            "semanticTokensProvider": {
                                "legend": {
                                    "tokenTypes": list(SEMANTIC_TOKEN_TYPES),
                                    "tokenModifiers": [],
                                },
                                "full": True,
                            },
                            "diagnosticProvider": {
                                "interFileDependencies": False,
                                "workspaceDiagnostics": False,
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
            _send(
                self.stdout, _response(message_id, self._definition(message))
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
            _send(
                self.stdout, _response(message_id, self._formatting(message))
            )
            return

        if method == "workspace/symbol":
            _send(
                self.stdout,
                _response(message_id, self._workspace_symbols(message)),
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
                self.documents.pop(uri, None)
                self.indexes.pop(uri, None)
                _send(
                    self.stdout,
                    _notification(
                        "textDocument/publishDiagnostics",
                        {"uri": uri, "diagnostics": []},
                    ),
                )

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
            lox._file = display_path(str(document.path))
            lox._module_root = document.path.parent
        else:
            lox._file = "<lsp>"
        lox.check(document.text, emit=False)
        batch = lox.reporter.batch()
        sources = lox._sources
        self.source_maps[document.uri] = sources
        self.indexes[document.uri] = SymbolIndex(
            lox.last_statements or [],
            source=document.text,
            checker=lox.last_checker,
            resolver=lox.last_resolver,
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
                if self.root is not None:
                    uri = _path_to_uri(self.root / span.file)
                elif document.path is not None:
                    uri = _path_to_uri(document.path.parent / span.file)
            rng = _range(span, source)

        related = []
        for label in diagnostic.labels:
            label_source = _source_for(sources, label.span.file, source)
            label_uri = uri
            if span is not None and label.span.file != span.file:
                if self.root is not None:
                    label_uri = _path_to_uri(self.root / label.span.file)
                elif document.path is not None:
                    label_uri = _path_to_uri(
                        document.path.parent / label.span.file
                    )
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
        if self.root is not None:
            return _path_to_uri(self.root / span.file), source
        if document.path is not None:
            return _path_to_uri(document.path.parent / span.file), source
        return document.uri, source

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
        return {
            token_key(token): token
            for token in Scanner(text, reporter).scan_tokens()
        }

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
        if self._rename_target(index, token) is None and not self._is_top_level(
            index, token
        ):
            return None
        return {
            "range": _token_range(token, document.text),
            "placeholder": token.lexeme,
        }

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
        target = self._rename_target(index, token)
        if target is None:
            if self._is_top_level(index, token):
                return self._workspace_rename(document, token, new_name)
            return "Rename is only supported for local variables, parameters and top-level declarations."
        _declaration, occurrences = target
        tokens = self._tokens_by_key(document.text)
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
                        **(
                            {"containerName": symbol.container}
                            if symbol.container
                            else {}
                        ),
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
        return symbol.kind in {"function", "class", "enum", "interface", "type"}

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
            if any(
                part.startswith(".") or part in {"node_modules"}
                for part in path.parts
            ):
                continue
            if path not in files:
                try:
                    files[path] = path.read_text(encoding="utf-8")
                except OSError:
                    continue
        return sorted(files.items())

    def _workspace_rename(
        self, document: Document, token: Token, new_name: str
    ) -> object:
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
                if (
                    symbol.container is None
                    and symbol.kind
                    in {"function", "class", "enum", "interface", "type"}
                ):
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
        actions: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for diagnostic in diagnostics:
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
                    changes.setdefault(uri, []).append(
                        {"range": edit_range, "newText": new_text}
                    )
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
        return actions

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

    def _token_at(
        self, document: Document, position: object
    ) -> Token | None:
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
            parts.append(f"```lox\n{display(ty)}\n```")
        else:
            return None

        return {
            "contents": {"kind": "markdown", "value": "\n\n".join(parts)},
            "range": _token_range(token, document.text),
        }

    def _definition(
        self, message: dict[str, Any]
    ) -> dict[str, object] | None:
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
            return None

        target_uri = self._uri_for_token(symbol.token, document)
        target_source = document.text
        if (
            symbol.token.file
            and document.path is not None
            and symbol.token.file != document.path.name
        ):
            target_source = _source_for(
                self.source_maps.get(uri), symbol.token.file, document.text
            )
        return {
            "uri": target_uri,
            "range": _token_range(symbol.token, target_source),
        }

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
        if (
            not isinstance(uri, str)
            or not isinstance(line, int)
            or not isinstance(character, int)
        ):
            return empty
        document = self.documents.get(uri)
        if document is None:
            return empty
        index = self._index_for(uri)
        offset = self._offset_at(document.text, line, character)
        return {
            "isIncomplete": False,
            "items": completion_items(
                document.text, document.path, offset, index
            ),
        }

    def _signature_help(
        self, message: dict[str, Any]
    ) -> dict[str, object] | None:
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
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", before)
        if match is None:
            return None
        name = match.group(1)
        start = match.start(1)
        token_character = len(before[:start].encode("utf-16-le")) // 2
        token = self._token_at(
            document, {"line": line, "character": token_character}
        )
        if token is None:
            return None
        index = self._index_for(uri)
        if index is None:
            return None
        symbol = index.symbol_at(token)
        signature = symbol.signature if symbol is not None else None
        if signature is None:
            builtin = next(
                (item for item in BUILTIN_DOCS if item.name == name), None
            )
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
        if result is None:
            return []
        lines = document.text.splitlines() or [""]
        last_line = len(lines) - 1
        last_text = lines[last_line]
        last_character = len(last_text.encode("utf-16-le")) // 2
        return [
            {
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {
                        "line": last_line,
                        "character": last_character,
                    },
                },
                "newText": result.text,
            }
        ]

    def _semantic_tokens(
        self, message: dict[str, Any]
    ) -> dict[str, object]:
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
            if line < previous_line or (
                line == previous_line and character < previous_character
            ):
                continue
            delta_line = line - previous_line
            delta_character = (
                character if delta_line else character - previous_character
            )
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

    def _uri_for_token(self, token: Token, document: Document) -> str:
        if not token.file or document.path is None:
            return document.uri
        if token.file == display_path(str(document.path)):
            return document.uri
        if self.root is not None:
            return _path_to_uri(self.root / token.file)
        return _path_to_uri(document.path.parent / token.file)

    # -- símbolos --------------------------------------------------------

    def _document_symbols(
        self, message: dict[str, Any]
    ) -> list[dict[str, object]]:
        params = message.get("params")
        if not isinstance(params, dict):
            return []
        document = params.get("textDocument")
        if not isinstance(document, dict) or not isinstance(
            document.get("uri"), str
        ):
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
            symbol
            for statement in statements
            for symbol in _symbols_for(statement, current.text)
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


def _symbols_for(
    statement: Stmt, source: str
) -> list[dict[str, object]]:
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
        "and", "as", "class", "elif", "else", "enum", "false", "fn", "for",
        "from", "if", "implements", "import", "in", "interface", "is", "match",
        "nil", "not", "or", "raise", "return", "super", "this", "true", "try",
        "except", "finally", "type", "val", "var", "while",
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
