"""Servidor LSP mínimo (ADR-0090), JSON-RPC sobre stdio, sem dependências.

LSP-0: full sync, `publishDiagnostics` e `documentSymbol`. Hover/definition/completion
dependem de spans de expressão/SymbolIndex (LSP-1) e ainda não existem.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any
from urllib.parse import unquote, urlparse

from loxia import __version__
from loxia.cli import Loxia
from loxia_core.diagnostics.diagnostic import (
    Diagnostic,
    Severity,
    Span,
)
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.source import display_path
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import (
    Class,
    EnumDecl,
    Function,
    Interface,
    Stmt,
    TypeAlias,
    Var,
)
from loxia_core.frontend.tokens import Token

JSONRPC_VERSION = "2.0"
SCHEMA_VERSION = 1

# DocumentSymbolKind da LSP.
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
                            "documentSymbolProvider": True,
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
