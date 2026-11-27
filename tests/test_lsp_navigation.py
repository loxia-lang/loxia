# SPDX-License-Identifier: MIT OR Apache-2.0
"""LSP: referências, navegação de tipos, hierarquia, tags e fix-all (issue #46)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest

from loxia import lsp as lsp_module
from loxia import rename as rename_module
from loxia.lsp import REQUEST_METHODS, Document, Server
from loxia_core.loader.module_cache import ModuleCache

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def send(process: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
    assert process.stdin is not None
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    process.stdin.write(body)
    process.stdin.flush()


def read(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    assert process.stdout is not None
    headers: dict[str, str] = {}
    while True:
        line = process.stdout.readline()
        assert line, "LSP encerrou sem resposta"
        if line in (b"\r\n", b"\n"):
            break
        name, _, value = line.decode("ascii").partition(":")
        headers[name.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    return cast(dict[str, Any], json.loads(process.stdout.read(length)))


def start() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(ENTRYPOINT), "lsp"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def start_with_root(root: Path) -> subprocess.Popen[bytes]:
    process = start()
    send(
        process,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"rootUri": root.as_uri()},
        },
    )
    read(process)
    send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
    return process


def open_document(process: subprocess.Popen[bytes], path: Path, text: str) -> dict[str, Any]:
    send(
        process,
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": path.as_uri(),
                    "languageId": "loxia",
                    "version": 1,
                    "text": text,
                }
            },
        },
    )
    return read(process)


def request(
    process: subprocess.Popen[bytes], request_id: int, method: str, params: dict[str, Any]
) -> object:
    send(process, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
    return read(process)["result"]


def stop(process: subprocess.Popen[bytes]) -> None:
    try:
        send(process, {"jsonrpc": "2.0", "id": 99, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_capabilities_and_handlers_do_not_drift(tmp_path: Path) -> None:
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        capabilities = read(process)["result"]["capabilities"]
        assert "diagnosticProvider" not in capabilities

        expected = {
            "textDocument/hover",
            "textDocument/definition",
            "textDocument/references",
            "textDocument/documentHighlight",
            "textDocument/typeDefinition",
            "textDocument/implementation",
            "textDocument/prepareTypeHierarchy",
            "typeHierarchy/supertypes",
            "typeHierarchy/subtypes",
            "workspace/symbol",
            "workspace/willRenameFiles",
            "textDocument/rename",
            "textDocument/prepareRename",
            "textDocument/documentSymbol",
            "textDocument/completion",
            "textDocument/signatureHelp",
            "textDocument/formatting",
            "textDocument/codeAction",
            "textDocument/inlayHint",
            "textDocument/semanticTokens/full",
        }
        assert REQUEST_METHODS - {"initialize", "shutdown"} == expected

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/notAHandler",
                "params": {},
            },
        )
        error = read(process)["error"]
        assert error["code"] == -32601

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_references_and_document_highlight_local(tmp_path: Path) -> None:
    path = tmp_path / "local.lx"
    text = "val x = 1\nprint(x)\n"
    process = start_with_root(tmp_path)
    try:
        open_document(process, path, text)
        references = cast(
            list[dict[str, Any]],
            request(
                process,
                2,
                "textDocument/references",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": {"line": 0, "character": 4},
                    "context": {"includeDeclaration": True},
                },
            ),
        )
        assert len(references) == 2
        assert {item["uri"] for item in references} == {path.as_uri()}

        references_without_declaration = cast(
            list[dict[str, Any]],
            request(
                process,
                3,
                "textDocument/references",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": {"line": 0, "character": 4},
                    "context": {"includeDeclaration": False},
                },
            ),
        )
        assert len(references_without_declaration) == 1
        assert references_without_declaration[0]["range"]["start"]["line"] == 1

        highlights = cast(
            list[dict[str, Any]],
            request(
                process,
                4,
                "textDocument/documentHighlight",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": {"line": 1, "character": 6},
                },
            ),
        )
        assert len(highlights) == 2
        assert {item["kind"] for item in highlights} == {2, 3}
    finally:
        stop(process)


def test_lsp_references_cross_file(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text("fn foo() -> Int {\n  return 1\n}\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("from mod import foo\nprint(foo())\n", encoding="utf-8")
    process = start_with_root(tmp_path)
    try:
        open_document(process, module, module.read_text(encoding="utf-8"))
        open_document(process, main, main.read_text(encoding="utf-8"))
        references = cast(
            list[dict[str, Any]],
            request(
                process,
                2,
                "textDocument/references",
                {
                    "textDocument": {"uri": module.as_uri()},
                    "position": {"line": 0, "character": 3},
                    "context": {"includeDeclaration": True},
                },
            ),
        )
        assert len(references) == 3
        assert {item["uri"] for item in references} == {
            module.as_uri(),
            main.as_uri(),
        }
    finally:
        stop(process)


def test_lsp_type_definition_and_implementation(tmp_path: Path) -> None:
    module = tmp_path / "types.lx"
    module.write_text(
        "interface Shape {\n"
        "  fn area() -> Int\n"
        "}\n"
        "class Square implements Shape {\n"
        "  fn area() -> Int { return 1 }\n"
        "}\n"
        "class Sub(Square) {\n"
        "}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text(
        "from types import Shape\n"
        "from types import Square\n"
        "val s: Shape = Square()\n"
        "print(s.area())\n",
        encoding="utf-8",
    )
    process = start_with_root(tmp_path)
    try:
        open_document(process, module, module.read_text(encoding="utf-8"))
        open_document(process, main, main.read_text(encoding="utf-8"))

        type_definition = request(
            process,
            2,
            "textDocument/typeDefinition",
            {
                "textDocument": {"uri": main.as_uri()},
                "position": {"line": 2, "character": 4},
            },
        )
        targets = cast(
            list[dict[str, Any]],
            type_definition if isinstance(type_definition, list) else [type_definition],
        )
        assert any(item["uri"] == module.as_uri() for item in targets)

        implementation = request(
            process,
            3,
            "textDocument/implementation",
            {
                "textDocument": {"uri": module.as_uri()},
                "position": {"line": 0, "character": 10},
            },
        )
        implementations = cast(
            list[dict[str, Any]],
            implementation if isinstance(implementation, list) else [implementation],
        )
        assert {item["uri"] for item in implementations} == {module.as_uri()}
        assert {item["range"]["start"]["line"] for item in implementations} == {3, 6}
    finally:
        stop(process)


def test_lsp_type_hierarchy(tmp_path: Path) -> None:
    path = tmp_path / "hierarchy.lx"
    text = (
        "class A {}\n"
        "class B(A) {}\n"
        "interface I {\n"
        "  fn f() -> Int\n"
        "}\n"
        "class C implements I {\n"
        "  fn f() -> Int { return 1 }\n"
        "}\n"
    )
    process = start_with_root(tmp_path)
    try:
        open_document(process, path, text)

        prepared = cast(
            list[dict[str, Any]],
            request(
                process,
                2,
                "textDocument/prepareTypeHierarchy",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": {"line": 1, "character": 6},
                },
            ),
        )
        assert [item["name"] for item in prepared] == ["B"]

        supertypes = cast(
            list[dict[str, Any]],
            request(process, 3, "typeHierarchy/supertypes", {"item": prepared[0]}),
        )
        assert [item["name"] for item in supertypes] == ["A"]

        prepared_a = cast(
            list[dict[str, Any]],
            request(
                process,
                4,
                "textDocument/prepareTypeHierarchy",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": {"line": 0, "character": 6},
                },
            ),
        )
        subtypes = cast(
            list[dict[str, Any]],
            request(process, 5, "typeHierarchy/subtypes", {"item": prepared_a[0]}),
        )
        assert [item["name"] for item in subtypes] == ["B"]

        prepared_i = cast(
            list[dict[str, Any]],
            request(
                process,
                6,
                "textDocument/prepareTypeHierarchy",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": {"line": 2, "character": 10},
                },
            ),
        )
        implementors = cast(
            list[dict[str, Any]],
            request(process, 7, "typeHierarchy/subtypes", {"item": prepared_i[0]}),
        )
        assert [item["name"] for item in implementors] == ["C"]
    finally:
        stop(process)


def test_lsp_diagnostics_tag_unnecessary(tmp_path: Path) -> None:
    path = tmp_path / "unused.lx"
    text = 'fn f() -> Nil {\n  val unused = 1\n  print("x")\n}\n'
    process = start_with_root(tmp_path)
    try:
        published = open_document(process, path, text)
        diagnostics = published["params"]["diagnostics"]
        unused = [item for item in diagnostics if item["code"] == "W1001"]
        assert unused and unused[0]["tags"] == [1]
        assert all(item["severity"] == 2 for item in unused)
    finally:
        stop(process)


def test_lsp_code_action_fix_all_applies_safe_fixes(tmp_path: Path) -> None:
    path = tmp_path / "fixall.lx"
    text = 'fn f() -> Nil {\n  val a = 1\n  val b = 2\n  print("x")\n}\n'
    process = start_with_root(tmp_path)
    try:
        published = open_document(process, path, text)
        diagnostics = published["params"]["diagnostics"]
        actions = cast(
            list[dict[str, Any]],
            request(
                process,
                2,
                "textDocument/codeAction",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 5, "character": 0},
                    },
                    "context": {"diagnostics": diagnostics, "only": ["source.fixAll"]},
                },
            ),
        )
        assert [action["kind"] for action in actions] == ["source.fixAll.loxia"]
        edits = actions[0]["edit"]["changes"][path.as_uri()]
        assert len(edits) == 2
        assert all(edit["newText"].startswith("_") for edit in edits)

        quickfix_only = cast(
            list[dict[str, Any]],
            request(
                process,
                3,
                "textDocument/codeAction",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 5, "character": 0},
                    },
                    "context": {"diagnostics": diagnostics, "only": ["quickfix"]},
                },
            ),
        )
        assert quickfix_only
        assert all(action["kind"] == "quickfix" for action in quickfix_only)
    finally:
        stop(process)


def test_lsp_features_survive_syntax_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.lx"
    text = "fn f() -> Int {\n  return 1\n}\nval ok: Int = f()\nval broken =\n"
    process = start_with_root(tmp_path)
    try:
        published = open_document(process, path, text)
        assert published["params"]["diagnostics"]

        hover = request(
            process,
            2,
            "textDocument/hover",
            {
                "textDocument": {"uri": path.as_uri()},
                "position": {"line": 0, "character": 3},
            },
        )
        assert hover is not None

        definition = request(
            process,
            3,
            "textDocument/definition",
            {
                "textDocument": {"uri": path.as_uri()},
                "position": {"line": 3, "character": 14},
            },
        )
        results = cast(
            list[dict[str, Any]],
            definition if isinstance(definition, list) else [definition],
        )
        assert [item["uri"] for item in results] == [path.as_uri()]
        assert results[0]["range"]["start"]["line"] == 0
    finally:
        stop(process)


def test_lsp_unsaved_module_text_feeds_importers(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text("fn f() -> Int {\n  return 1\n}\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("from mod import f\nval x: Int = f()\n", encoding="utf-8")
    process = start_with_root(tmp_path)
    try:
        open_document(process, module, module.read_text(encoding="utf-8"))
        opened = open_document(process, main, main.read_text(encoding="utf-8"))
        assert opened["params"]["diagnostics"] == []

        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {"uri": module.as_uri(), "version": 2},
                    "contentChanges": [{"text": 'fn f() -> String {\n  return "x"\n}\n'}],
                },
            },
        )
        changed = read(process)
        assert changed["params"]["uri"] == module.as_uri()
        assert changed["params"]["diagnostics"] == []

        importer = read(process)
        assert importer["params"]["uri"] == main.as_uri()
        codes = {item["code"] for item in importer["params"]["diagnostics"]}
        assert "E3001" in codes
    finally:
        stop(process)


def test_lsp_will_rename_files_rewrites_imports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    module = package / "a.lx"
    module.write_text("fn foo() -> Int {\n  return 1\n}\n", encoding="utf-8")
    main = package / "main.lx"
    main.write_text(
        "import pkg.a\nfrom pkg.a import foo\nprint(foo())\n",
        encoding="utf-8",
    )
    process = start_with_root(tmp_path)
    try:
        open_document(process, main, main.read_text(encoding="utf-8"))
        renamed = package / "b.lx"
        result = cast(
            dict[str, Any],
            request(
                process,
                2,
                "workspace/willRenameFiles",
                {"files": [{"oldUri": module.as_uri(), "newUri": renamed.as_uri()}]},
            ),
        )
        changes = cast(dict[str, list[dict[str, Any]]], result["changes"])
        assert set(changes) == {main.as_uri()}
        assert [edit["newText"] for edit in changes[main.as_uri()]] == [
            "pkg.b",
            "pkg.b",
        ]
    finally:
        stop(process)


def _open_in_process(
    tmp_path: Path, text: str, filename: str = "nav.lx"
) -> tuple[Server, Document]:
    path = tmp_path / filename
    path.write_text(text, encoding="utf-8")
    uri = path.as_uri()
    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path
    document = Document(text=text, version=1, path=path, uri=uri)
    server.documents[uri] = document
    server._diagnostics(document)
    return server, document


def test_analyze_updates_caches_without_publishing(tmp_path: Path) -> None:
    path = tmp_path / "quiet.lx"
    text = "val x: Int = 1\n"
    path.write_text(text, encoding="utf-8")
    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path
    document = Document(text=text, version=1, path=path, uri=path.as_uri())

    analysis = server._analyze(document)

    assert analysis.version == 1
    assert analysis.diagnostics == ()
    assert server.analyses[document.uri] is analysis
    # O índice de símbolos só nasce na primeira navegação.
    assert server.indexes == {}
    assert server.clean[document.uri] is True
    assert cast(BytesIO, server.stdout).getvalue() == b""

    assert server._index_for(document.uri) is not None
    assert document.uri in server.indexes


def _published(output: BytesIO) -> list[dict[str, Any]]:
    raw = output.getvalue()
    messages: list[dict[str, Any]] = []
    while raw:
        head, _, rest = raw.partition(b"\r\n\r\n")
        if not head or not rest:
            break
        length = int(head.decode("ascii").split(":", 1)[1])
        messages.append(cast(dict[str, Any], json.loads(rest[:length])))
        raw = rest[length:]
    return messages


def test_change_defers_analysis_until_flush(tmp_path: Path) -> None:
    server, document = _open_in_process(tmp_path, "val x: Int = 1\n")
    output = cast(BytesIO, server.stdout)

    server._change(
        {
            "textDocument": {"uri": document.uri, "version": 2},
            "contentChanges": [{"text": "val x: Int = 2\n"}],
        }
    )

    assert output.getvalue() == b""
    assert document.text == "val x: Int = 2\n"
    assert document.uri in server._dirty

    server._flush_dirty()

    published = _published(output)
    assert [item["params"]["version"] for item in published] == [2]
    assert published[0]["params"]["diagnostics"] == []
    assert server._dirty == {}


def test_change_applies_range_edits_in_order(tmp_path: Path) -> None:
    server, document = _open_in_process(tmp_path, "val x: Int = 1\nval y: Int = 2\n")

    server._change(
        {
            "textDocument": {"uri": document.uri, "version": 2},
            "contentChanges": [
                {
                    "range": {
                        "start": {"line": 0, "character": 13},
                        "end": {"line": 0, "character": 14},
                    },
                    "text": "10",
                },
                {
                    "range": {
                        "start": {"line": 1, "character": 13},
                        "end": {"line": 1, "character": 14},
                    },
                    "text": "20",
                },
            ],
        }
    )

    assert document.text == "val x: Int = 10\nval y: Int = 20\n"


def test_change_range_uses_utf16_columns(tmp_path: Path) -> None:
    server, document = _open_in_process(tmp_path, 'val s = "😀"\n')
    start = len('val s = "'.encode("utf-16-le")) // 2

    server._change(
        {
            "textDocument": {"uri": document.uri, "version": 2},
            "contentChanges": [
                {
                    "range": {
                        "start": {"line": 0, "character": start},
                        "end": {"line": 0, "character": start + 2},
                    },
                    "text": "x",
                }
            ],
        }
    )

    assert document.text == 'val s = "x"\n'


def test_lsp_reuses_module_parse_across_edits(tmp_path: Path) -> None:
    lib = tmp_path / "lib.lx"
    lib.write_text("fn f() -> Int { return 1 }\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    text = "from lib import f\nval x: Int = f()\n"
    main.write_text(text, encoding="utf-8")
    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path
    document = Document(text=text, version=1, path=main, uri=main.as_uri())
    server.documents[document.uri] = document

    server._analyze(document)
    assert len(server.parse_cache) == 1

    edited = text + "val y: Int = 2\n"
    server._change(
        {
            "textDocument": {"uri": document.uri, "version": 2},
            "contentChanges": [{"text": edited}],
        }
    )
    server._flush_dirty()

    # Editar a entrada não invalida o parse do módulo importado.
    assert len(server.parse_cache) == 1
    assert server.clean[document.uri] is True

    lib.write_text('fn f() -> String { return "x" }\n', encoding="utf-8")
    server._change(
        {
            "textDocument": {"uri": document.uri, "version": 3},
            "contentChanges": [{"text": edited}],
        }
    )
    server._flush_dirty()

    # Conteúdo novo do módulo vira uma entrada nova e o diagnóstico muda.
    assert len(server.parse_cache) == 2
    assert server.clean[document.uri] is False


def _position_of(text: str, needle: str, start: int = 0) -> tuple[dict[str, int], int]:
    offset = text.index(needle, start)
    line = text.count("\n", 0, offset)
    last_newline = text.rfind("\n", 0, offset)
    return {"line": line, "character": offset - last_newline - 1}, offset


def _request_params(document: Document, position: dict[str, int]) -> dict[str, Any]:
    return {
        "textDocument": {"uri": document.uri},
        "position": position,
    }


def _columns(text: str, offset: int, length: int) -> tuple[int, int]:
    last_newline = text.rfind("\n", 0, offset)
    start = offset - last_newline - 1
    return start, start + length


def test_lsp_navigation_uses_exact_type_name_span(tmp_path: Path) -> None:
    text = "class Foo {}\nval xs: List[Foo] = []\n"
    server, document = _open_in_process(tmp_path, text)
    position, offset = _position_of(text, "Foo", text.index("["))
    index = server.source_indexes[document.uri]
    span = index.at(offset, file=server.source_files[document.uri])
    assert span is not None
    assert span.kind == "type"
    assert index.text_of(span) == "Foo"

    token = server._token_at(document, position)
    assert token is not None
    assert token.lexeme == "Foo"
    navigation = cast(dict[str, Any], server._range_for(document, token))
    start, end = _columns(text, offset, len("Foo"))
    assert navigation["start"]["character"] == start
    assert navigation["end"]["character"] == end
    # Nunca o span da anotação inteira (`List[Foo]`).
    list_token = server._token_at(document, _position_of(text, "List")[0])
    assert list_token is not None
    assert server._range_for(document, list_token) != navigation


def test_lsp_prepare_rename_uses_type_name_span_from_imported_type(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text("class Foo {}\n", encoding="utf-8")
    text = "from mod import Foo\nval xs: List[Foo] = []\n"
    server, document = _open_in_process(tmp_path, text, "main.lx")
    position, offset = _position_of(text, "Foo", text.index("["))
    token = server._token_at(document, position)
    assert token is not None

    prepared = cast(
        dict[str, Any],
        server._prepare_rename({"params": _request_params(document, position)}),
    )
    navigation = cast(dict[str, Any], server._range_for(document, token))
    assert prepared["range"] == navigation
    start, end = _columns(text, offset, len("Foo"))
    assert navigation["start"]["character"] == start
    assert navigation["end"]["character"] == end


def test_lsp_rename_type_annotation_edits_only_the_type_name(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text("class Foo {}\n", encoding="utf-8")
    text = "from mod import Foo\nval xs: List[Foo] = []\n"
    server, document = _open_in_process(tmp_path, text, "main.lx")
    position, _ = _position_of(text, "Foo", text.index("["))

    result = cast(
        dict[str, Any],
        server._rename(
            {
                "params": {
                    **_request_params(document, position),
                    "newName": "Bar",
                }
            }
        ),
    )
    edits = cast(list[dict[str, Any]], result["changes"][document.uri])
    assert edits
    for edit in edits:
        rng = cast(dict[str, Any], edit["range"])
        assert rng["start"]["line"] == rng["end"]["line"]
        assert rng["end"]["character"] - rng["start"]["character"] == len("Foo")


def test_lsp_navigation_uses_exact_declaration_name_span(tmp_path: Path) -> None:
    text = "fn soma(a: Int) -> Int {\n  return a\n}\nprint(soma(1))\n"
    server, document = _open_in_process(tmp_path, text)
    position, offset = _position_of(text, "soma")
    index = server.source_indexes[document.uri]
    span = index.at(offset, file=server.source_files[document.uri])
    assert span is not None and span.kind == "name"
    token = server._token_at(document, position)
    assert token is not None

    start, end = _columns(text, offset, len("soma"))
    navigation = cast(dict[str, Any], server._range_for(document, token))
    assert navigation["start"]["character"] == start
    assert navigation["end"]["character"] == end

    prepared = cast(
        dict[str, Any],
        server._prepare_rename({"params": _request_params(document, position)}),
    )
    assert prepared["range"] == navigation

    references = cast(
        list[dict[str, Any]],
        server._references(
            {
                "params": {
                    **_request_params(document, position),
                    "context": {"includeDeclaration": True},
                }
            }
        ),
    )
    assert len(references) == 2
    for reference in references:
        rng = reference["range"]
        assert rng["end"]["character"] - rng["start"]["character"] == len("soma")


def test_lsp_navigation_falls_back_for_expression_and_syntax_error(tmp_path: Path) -> None:
    text = "val total = 1\nprint(total)\n"
    server, document = _open_in_process(tmp_path, text)
    position, offset = _position_of(text, "total", text.index("("))
    span = server.source_indexes[document.uri].at(offset, file=server.source_files[document.uri])
    assert span is not None and span.kind == "node"
    token = server._token_at(document, position)
    assert token is not None
    assert server._range_for(document, token) == {
        "start": {"line": 1, "character": 6},
        "end": {"line": 1, "character": 11},
    }

    broken = "val x: List[= 1\n"
    broken_server, broken_document = _open_in_process(tmp_path, broken, "broken.lx")
    assert broken_document.uri not in broken_server.source_indexes
    broken_position, _ = _position_of(broken, "List")
    broken_token = broken_server._token_at(broken_document, broken_position)
    assert broken_token is not None
    assert broken_server._range_for(broken_document, broken_token) == {
        "start": {"line": 0, "character": 7},
        "end": {"line": 0, "character": 11},
    }


def test_lsp_upgrade_semantic_edits_uses_exact_type_span(tmp_path: Path) -> None:
    text = "class Foo {}\nval xs: List[Foo] = []\n"
    server, document = _open_in_process(tmp_path, text)
    position, offset = _position_of(text, "Foo", text.index("["))
    end = {"line": position["line"], "character": position["character"] + len("Foo]")}
    result: dict[str, object] = {
        "changes": {
            document.uri: [
                {"range": {"start": position, "end": end}, "newText": "Bar"},
            ]
        }
    }

    upgraded = server._upgrade_semantic_edits(document, result)
    changes = cast(dict[str, list[dict[str, Any]]], upgraded["changes"])
    edit_range = changes[document.uri][0]["range"]
    start, expected_end = _columns(text, offset, len("Foo"))

    assert edit_range["start"]["character"] == start
    assert edit_range["end"]["character"] == expected_end


def test_lsp_navigation_handles_utf8_and_multiline_offsets(tmp_path: Path) -> None:
    text = "# é\nfn f(\n  x: List[Foo],\n) -> Int { return 0 }\n"
    server, document = _open_in_process(tmp_path, text)
    position, offset = _position_of(text, "Foo")
    token = server._token_at(document, position)
    assert token is not None

    navigation = cast(dict[str, Any], server._range_for(document, token))
    start, end = _columns(text, offset, len("Foo"))
    assert navigation["start"] == {"line": 2, "character": start}
    assert navigation["end"] == {"line": 2, "character": end}


def test_lsp_references_reuse_workspace_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "lib.lx").write_text("class Foo {}\n", encoding="utf-8")
    text = "from lib import Foo\nval xs: List[Foo] = []\n"
    server, document = _open_in_process(tmp_path, text, "main.lx")
    builds: list[int] = []
    original = rename_module._build_workspace

    def counting(
        root: Path,
        files: dict[Path, str],
        module_cache: ModuleCache | None = None,
        **kwargs: object,
    ) -> object:
        builds.append(1)
        return original(root, files, module_cache, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(rename_module, "_build_workspace", counting)
    position, _ = _position_of(text, "Foo", text.index("["))
    params = {
        "textDocument": {"uri": document.uri},
        "position": position,
        "context": {"includeDeclaration": True},
    }

    first = cast(list[dict[str, Any]], server._references({"params": params}))
    second = cast(list[dict[str, Any]], server._references({"params": params}))

    assert first and second
    assert len(builds) == 1

    server._invalidate(document.uri)
    third = cast(list[dict[str, Any]], server._references({"params": params}))
    assert third
    assert len(builds) == 2


def test_lsp_does_not_build_source_index_for_diagnostics(tmp_path: Path) -> None:
    text = "val x: Int = 1\nprint(x)\n"
    server, document = _open_in_process(tmp_path, text)
    index = server.source_indexes[document.uri]
    assert index._built is False

    position, _ = _position_of(text, "Int")
    token = server._token_at(document, position)
    assert token is not None
    server._range_for(document, token)

    assert index._built is True


def test_lsp_workspace_files_prunes_hidden_and_vendored(tmp_path: Path) -> None:
    (tmp_path / "ok.lx").write_text("val ok = 1\n", encoding="utf-8")
    (tmp_path / ".hidden.lx").write_text("val hidden = 1\n", encoding="utf-8")
    for name in (".hidden", "node_modules"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "skip.lx").write_text("val skip = 1\n", encoding="utf-8")
    for name in ("build", "dist", "target"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "src.lx").write_text("val src = 1\n", encoding="utf-8")

    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path
    files = server._workspace_files()

    # `build`/`dist`/`target` não são podados por nome: podem ser fonte legítima.
    assert {path.name for path, _ in files} == {"ok.lx", "src.lx"}


def test_lsp_workspace_files_disk_cache_sees_content_changes(tmp_path: Path) -> None:
    path = tmp_path / "a.lx"
    path.write_text("val a = 1\n", encoding="utf-8")
    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path

    assert dict(server._workspace_files())[path].startswith("val a")
    path.write_text("val b = 2\n", encoding="utf-8")
    assert dict(server._workspace_files())[path].startswith("val b")


def test_lsp_workspace_files_disk_cache_detects_restored_mtime(tmp_path: Path) -> None:
    path = tmp_path / "a.lx"
    path.write_text("val a = 1\n", encoding="utf-8")
    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path
    before = path.stat()
    assert dict(server._workspace_files())[path].startswith("val a")

    path.write_text("val b = 2\n", encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert dict(server._workspace_files())[path].startswith("val b")


def test_lsp_disk_cache_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("a.lx", "b.lx"):
        (tmp_path / name).write_text(f"val {name[0]} = 1\n", encoding="utf-8")
    monkeypatch.setattr(lsp_module, "_DISK_FILES_LIMIT", 1)
    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path

    server._workspace_files()
    server._workspace_files()

    assert len(server._disk_files) == 1


def test_dependent_recheck_rebuilds_the_symbol_index(tmp_path: Path) -> None:
    lib = tmp_path / "lib.lx"
    lib.write_text("fn f() -> Int {\n  return 1\n}\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    text = "from lib import f\nval x: Int = f()\n"
    main.write_text(text, encoding="utf-8")
    server = Server(BytesIO(), BytesIO())
    server.root = tmp_path
    lib_document = Document(
        text=lib.read_text(encoding="utf-8"), version=1, path=lib, uri=lib.as_uri()
    )
    main_document = Document(text=text, version=1, path=main, uri=main.as_uri())
    server.documents[lib_document.uri] = lib_document
    server.documents[main_document.uri] = main_document
    params = {
        "textDocument": {"uri": main_document.uri},
        "position": {"line": 1, "character": 13},
    }

    server._analyze(main_document)
    before = server._hover({"params": params})
    assert before is not None
    assert "-> Int" in cast(dict[str, Any], before["contents"])["value"]

    # Editar a assinatura no módulo importado recheca o importador; o índice lazy
    # construído para o texto anterior não pode sobreviver ao recheck.
    server._change(
        {
            "textDocument": {"uri": lib_document.uri, "version": 2},
            "contentChanges": [{"text": 'fn f() -> String {\n  return "x"\n}\n'}],
        }
    )
    server._flush_dirty()

    after = server._hover({"params": params})
    assert after is not None
    assert "-> String" in cast(dict[str, Any], after["contents"])["value"]


STD_TEXT = """import std.lists as lists

val xs = [1, 2, 3]
val total: Int = lists.sum(xs)
"""


def _std_reference_position() -> dict[str, int]:
    position, _ = _position_of(STD_TEXT, "sum(xs)")
    return position


def test_lsp_references_module_outside_root_returns_locations(tmp_path: Path) -> None:
    server, document = _open_in_process(tmp_path, STD_TEXT, "main.lx")
    params = {
        **_request_params(document, _std_reference_position()),
        "context": {"includeDeclaration": True},
    }

    locations = cast(list[dict[str, Any]], server._references({"params": params}))

    uris = {item["uri"] for item in locations}
    # `std/` fica fora do root: a referência precisa resolver e não derrubar o servidor.
    assert any(uri.endswith("/std/lists.lx") for uri in uris)
    assert document.uri in uris


def test_lsp_prepare_rename_refuses_module_outside_root(tmp_path: Path) -> None:
    server, document = _open_in_process(tmp_path, STD_TEXT, "main.lx")

    prepared = server._prepare_rename(
        {"params": _request_params(document, _std_reference_position())}
    )

    assert prepared is None


def test_lsp_rename_module_outside_root_returns_message(tmp_path: Path) -> None:
    server, document = _open_in_process(tmp_path, STD_TEXT, "main.lx")
    params = {**_request_params(document, _std_reference_position()), "newName": "soma"}

    result = server._rename({"params": params})

    assert isinstance(result, str)
    assert "outside the workspace root" in result


MANIFEST = """[package]
name = "proj"
version = "0.1.0"

[modules]
paths = ["../shared"]
"""

EXTERNAL_LIB = """fn soma(a: Int, b: Int) -> Int {
  return a + b
}
"""

EXTERNAL_MAIN = """from lib import soma

val total: Int = soma(1, 2)
"""


def test_lsp_references_see_external_module_edit(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shared = tmp_path / "shared"
    project.mkdir()
    shared.mkdir()
    (project / "loxia.toml").write_text(MANIFEST, encoding="utf-8")
    (shared / "lib.lx").write_text(EXTERNAL_LIB, encoding="utf-8")
    server, document = _open_in_process(project, EXTERNAL_MAIN, "main.lx")
    position, _ = _position_of(EXTERNAL_MAIN, "soma(1")
    params = {
        "textDocument": {"uri": document.uri},
        "position": position,
        "context": {"includeDeclaration": True},
    }

    first = cast(list[dict[str, Any]], server._references({"params": params}))
    assert any(item["uri"].endswith("/shared/lib.lx") for item in first)

    # Edição externa no disco (o arquivo não está aberto): o fingerprint do cache
    # inclui os insumos de resolução, então a nova ocorrência aparece sem stale.
    (shared / "lib.lx").write_text(
        EXTERNAL_LIB + "\nfn outro() -> Int {\n  return soma(1, 2)\n}\n",
        encoding="utf-8",
    )
    second = cast(list[dict[str, Any]], server._references({"params": params}))

    assert len(second) == len(first) + 1
    external_lines = sorted(
        cast(dict[str, dict[str, int]], item["range"])["start"]["line"]
        for item in second
        if item["uri"].endswith("/shared/lib.lx")
    )
    assert 5 in external_lines


def test_lsp_rename_outside_root_keeps_the_server_alive(tmp_path: Path) -> None:
    text = "import std.lists as lists\n\nval xs = [1, 2, 3]\nval total: Int = lists.sum(xs)\n"
    path = tmp_path / "main.lx"
    path.write_text(text, encoding="utf-8")
    process = start_with_root(tmp_path)
    try:
        open_document(process, path, text)
        position, _ = _position_of(text, "sum(xs)")
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "textDocument/rename",
                "params": {
                    "textDocument": {"uri": path.as_uri()},
                    "position": position,
                    "newName": "soma",
                },
            },
        )

        response = read(process)

        assert "error" in response
        assert response["error"]["code"] == -32602
        assert "outside the workspace root" in response["error"]["message"]
        # Antes do ADR-0151 o KeyError matava o processo (exit 1).
        assert process.poll() is None
    finally:
        stop(process)
