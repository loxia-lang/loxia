# SPDX-License-Identifier: MIT OR Apache-2.0
"""LSP: referências, navegação de tipos, hierarquia, tags e fix-all (issue #46)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from loxia.lsp import REQUEST_METHODS

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
