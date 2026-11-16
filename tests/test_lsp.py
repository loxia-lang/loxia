from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

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
    payload = json.loads(process.stdout.read(length))
    return cast(dict[str, Any], payload)


def start() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(ENTRYPOINT), "lsp"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_lsp_initialize_diagnostics_symbols_and_shutdown(tmp_path: Path) -> None:
    uri = (tmp_path / "api.lx").as_uri()
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        initialized = read(process)
        assert initialized["result"]["capabilities"]["documentSymbolProvider"] is True
        assert initialized["result"]["capabilities"]["textDocumentSync"] == 1

        send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": '/// F.\nfn f() -> Int {\n  return 1\n}\nval x: Int = "a"\n',
                    }
                },
            },
        )
        published = read(process)
        assert published["method"] == "textDocument/publishDiagnostics"
        diagnostics = published["params"]["diagnostics"]
        assert diagnostics[0]["code"] == "E3001"
        assert diagnostics[0]["source"] == "loxia"

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/documentSymbol",
                "params": {"textDocument": {"uri": uri}},
            },
        )
        symbols = read(process)["result"]
        names = [symbol["name"] for symbol in symbols]
        assert "f" in names
        assert "x" in names

        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {"uri": uri, "version": 2},
                    "contentChanges": [{"text": "print(1)\n"}],
                },
            },
        )
        cleared = read(process)
        assert cleared["method"] == "textDocument/publishDiagnostics"
        assert cleared["params"]["diagnostics"] == []

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        assert read(process)["result"] is None
        send(process, {"jsonrpc": "2.0", "method": "exit", "params": {}})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lsp_document_symbols_include_class_children(tmp_path: Path) -> None:
    uri = (tmp_path / "point.lx").as_uri()
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": "class Point {\n  val x: Int\n  fn get() -> Int { return this.x }\n}\n",
                    }
                },
            },
        )
        read(process)  # publishDiagnostics inicial
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/documentSymbol",
                "params": {"textDocument": {"uri": uri}},
            },
        )
        symbols = read(process)["result"]
        point = next(symbol for symbol in symbols if symbol["name"] == "Point")
        assert point["kind"] == 5
        assert [child["name"] for child in point["children"]] == ["x", "get"]

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lsp_hover_and_definition_for_function_and_variable(tmp_path: Path) -> None:
    uri = (tmp_path / "hover.lx").as_uri()
    text = (
        "/// Adds.\n"
        "fn add(a: Int, b: Int) -> Int {\n"
        "  return a + b\n"
        "}\n"
        "val x = add(1, 2)\n"
        "print(x)\n"
    )
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": text,
                    }
                },
            },
        )
        read(process)  # publishDiagnostics

        # `add` na chamada (linha 4, coluna 8 em 0-based).
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/hover",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 4, "character": 8},
                },
            },
        )
        hover = read(process)["result"]
        assert "fn add(a: Int, b: Int) -> Int" in hover["contents"]["value"]
        assert "Adds." in hover["contents"]["value"]

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/definition",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 4, "character": 8},
                },
            },
        )
        definition = read(process)["result"]
        assert definition["uri"] == uri
        assert definition["range"]["start"] == {"line": 1, "character": 3}

        # `x` na chamada de print: tipo e definição.
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "textDocument/hover",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 5, "character": 6},
                },
            },
        )
        hover_x = read(process)["result"]
        assert "Int" in hover_x["contents"]["value"]

        send(process, {"jsonrpc": "2.0", "id": 5, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lsp_hover_field_via_class_type(tmp_path: Path) -> None:
    uri = (tmp_path / "field.lx").as_uri()
    text = (
        "class Point {\n"
        "  val x: Int\n"
        "  init(x: Int) { this.x = x }\n"
        "  fn get() -> Int { return this.x }\n"
        "}\n"
        "val p = Point(1)\n"
        "print(p.x)\n"
    )
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": text,
                    }
                },
            },
        )
        read(process)

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/hover",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 6, "character": 8},
                },
            },
        )
        hover = read(process)["result"]
        assert "val x: Int" in hover["contents"]["value"]

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/definition",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 6, "character": 8},
                },
            },
        )
        definition = read(process)["result"]
        assert definition["range"]["start"] == {"line": 1, "character": 6}

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lsp_formatting_returns_full_document_edit(tmp_path: Path) -> None:
    uri = (tmp_path / "fmt.lx").as_uri()
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": "fn f() -> Int {\n    return 1;\n}\n",
                    }
                },
            },
        )
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/formatting",
                "params": {"textDocument": {"uri": uri}, "options": {}},
            },
        )
        edits = read(process)["result"]
        assert edits[0]["newText"] == "fn f() -> Int {\n  return 1\n}\n"
        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lsp_completion_global_and_property(tmp_path: Path) -> None:
    uri = (tmp_path / "comp.lx").as_uri()
    text = (
        "class Point {\n"
        "  val x: Int\n"
        "  init(x: Int) { this.x = x }\n"
        "}\n"
        "val p = Point(1)\n"
        "val n = 1\n"
        "print(p.x)\n"
    )
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": text,
                    }
                },
            },
        )
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/completion",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 5, "character": 9},
                },
            },
        )
        labels = {item["label"] for item in read(process)["result"]["items"]}
        assert {"Point", "p", "n", "add"} <= labels or {"Point", "p", "n"} <= labels
        assert {"print", "len", "fn"} <= labels

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/completion",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 6, "character": 8},
                },
            },
        )
        property_labels = {
            item["label"] for item in read(process)["result"]["items"]
        }
        assert {"x", "init"} <= property_labels

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lsp_signature_help_and_semantic_tokens(tmp_path: Path) -> None:
    uri = (tmp_path / "sig.lx").as_uri()
    text = "fn add(a: Int, b: Int) -> Int { return a + b }\nprint(add(1, 2))\n"
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": text,
                    }
                },
            },
        )
        read(process)
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/signatureHelp",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 1, "character": 13},
                },
            },
        )
        signature = read(process)["result"]
        assert "fn add(a: Int, b: Int) -> Int" in signature["signatures"][0]["label"]
        assert signature["activeParameter"] == 1

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/semanticTokens/full",
                "params": {"textDocument": {"uri": uri}},
            },
        )
        data = read(process)["result"]["data"]
        assert data
        assert len(data) % 5 == 0

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_lsp_code_action_expoe_fixes(tmp_path: Path) -> None:
    uri = (tmp_path / "fix.lx").as_uri()
    source = (
        "fn f() -> Nil {\n"
        "  val unused = 1\n"
        '  prin("x")\n'
        "}\n"
    )
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        initialized = read(process)
        assert initialized["result"]["capabilities"]["codeActionProvider"] is True
        send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": source,
                    }
                },
            },
        )
        published = read(process)
        diagnostics = published["params"]["diagnostics"]
        codes = {item["code"] for item in diagnostics}
        assert codes == {"W1001", "E3003"}
        assert all(item["data"]["fixes"] for item in diagnostics)

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/codeAction",
                "params": {
                    "textDocument": {"uri": uri},
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 4, "character": 0},
                    },
                    "context": {"diagnostics": diagnostics},
                },
            },
        )
        response = read(process)
        actions = response["result"]
        assert len(actions) == 2
        preferred = {action["isPreferred"]: action for action in actions}
        assert preferred[True]["title"].startswith("Rename to")
        assert preferred[False]["title"].startswith("Replace with")
        assert preferred[True]["kind"] == "quickfix"

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_rename_local(tmp_path: Path) -> None:
    uri = (tmp_path / "rename.lx").as_uri()
    source = "fn f() -> Int {\n  val x = 1\n  return x + x\n}\n"
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        initialized = read(process)
        assert initialized["result"]["capabilities"]["renameProvider"] == {
            "prepareProvider": True
        }
        send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": source,
                    }
                },
            },
        )
        read(process)
        position = {"line": 1, "character": 6}
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/prepareRename",
                "params": {"textDocument": {"uri": uri}, "position": position},
            },
        )
        prepared = read(process)
        assert prepared["result"]["placeholder"] == "x"

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/rename",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": position,
                    "newName": "y",
                },
            },
        )
        renamed = read(process)
        edits = renamed["result"]["changes"][uri]
        assert len(edits) == 3
        assert all(edit["newText"] == "y" for edit in edits)

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
