# SPDX-License-Identifier: MIT OR Apache-2.0
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
        property_labels = {item["label"] for item in read(process)["result"]["items"]}
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
    source = 'fn f() -> Nil {\n  val unused = 1\n  prin("x")\n}\n'
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        initialized = read(process)
        code_action = initialized["result"]["capabilities"]["codeActionProvider"]
        assert code_action["codeActionKinds"] == [
            "quickfix",
            "source.fixAll",
            "source.fixAll.loxia",
        ]
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
        assert initialized["result"]["capabilities"]["renameProvider"] == {"prepareProvider": True}
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


def test_lsp_rename_cross_file(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text("fn foo() -> Int {\n  return 1\n}\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("from mod import foo\nprint(foo())\n", encoding="utf-8")
    uri = module.as_uri()
    process = start()
    try:
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"rootUri": tmp_path.as_uri()},
            },
        )
        read(process)
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
                        "text": module.read_text(encoding="utf-8"),
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
                "method": "textDocument/rename",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 0, "character": 4},
                    "newName": "bar",
                },
            },
        )
        response = read(process)
        changes = response["result"]["changes"]
        assert set(changes) == {module.as_uri(), main.as_uri()}
        assert all(edit["newText"] == "bar" for edits in changes.values() for edit in edits)
        assert len(changes[main.as_uri()]) == 2

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_workspace_symbol(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text("fn foo() -> Int {\n  return 1\n}\n", encoding="utf-8")
    (tmp_path / "other.lx").write_text("class Bar {\n}\n", encoding="utf-8")
    process = start()
    try:
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"rootUri": tmp_path.as_uri()},
            },
        )
        initialized = read(process)
        assert initialized["result"]["capabilities"]["workspaceSymbolProvider"] is True
        send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "workspace/symbol",
                "params": {"query": "fo"},
            },
        )
        response = read(process)
        symbols = response["result"]
        assert [item["name"] for item in symbols] == ["foo"]
        assert symbols[0]["kind"] == 12
        assert symbols[0]["location"]["uri"] == (tmp_path / "mod.lx").as_uri()

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_completion_de_modulo_std(tmp_path: Path) -> None:
    uri = (tmp_path / "comp.lx").as_uri()
    source = "import std.strings as strings\nval x = strings.\n"
    process = start()
    try:
        send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read(process)
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
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/completion",
                "params": {
                    "textDocument": {"uri": uri},
                    "position": {"line": 1, "character": 16},
                },
            },
        )
        labels = {item["label"] for item in read(process)["result"]["items"]}
        assert "upper" in labels
        assert all("$" not in label for label in labels)

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _start_with_root(root: Path, options: dict[str, Any] | None = None) -> subprocess.Popen[bytes]:
    process = start()
    params: dict[str, Any] = {"rootUri": root.as_uri()}
    if options is not None:
        params["initializationOptions"] = options
    send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params})
    read(process)
    send(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
    return process


def _open_document(process: subprocess.Popen[bytes], path: Path, text: str) -> dict[str, Any]:
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


def _request(
    process: subprocess.Popen[bytes], request_id: int, method: str, params: dict[str, Any]
) -> object:
    send(
        process,
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
    )
    return read(process)["result"]


def test_lsp_completion_herdada_inclui_superclasse_e_interface(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text(
        "class Base {\n  fn greet() -> Nil {}\n}\ninterface Named {\n  fn name() -> String\n}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    source = (
        "from mod import Base, Named\n"
        "class Child(Base) implements Named {\n"
        '  fn name() -> String { return "child" }\n'
        "}\n"
        "val c = Child()\n"
        "c.\n"
    )
    main.write_text(source, encoding="utf-8")
    super_file = tmp_path / "super.lx"
    super_source = (
        "from mod import Base\nclass Child(Base) {\n  fn call() -> Nil {\n    super.\n  }\n}\n"
    )
    super_file.write_text(super_source, encoding="utf-8")
    process = _start_with_root(tmp_path)
    try:
        _open_document(process, main, source)
        completion = cast(
            dict[str, Any],
            _request(
                process,
                2,
                "textDocument/completion",
                {
                    "textDocument": {"uri": main.as_uri()},
                    "position": {"line": 5, "character": 2},
                },
            ),
        )
        labels = {item["label"] for item in completion["items"]}
        assert {"greet", "name"} <= labels
        assert all("$" not in str(label) for label in labels)

        _open_document(process, super_file, super_source)
        inherited = cast(
            dict[str, Any],
            _request(
                process,
                3,
                "textDocument/completion",
                {
                    "textDocument": {"uri": super_file.as_uri()},
                    "position": {"line": 3, "character": 10},
                },
            ),
        )
        super_labels = {item["label"] for item in inherited["items"]}
        assert "greet" in super_labels
        assert "name" not in super_labels

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_settings_controlam_completion_herdada(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text("class Base {\n  fn greet() -> Nil {}\n}\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    source = (
        "from mod import Base\nclass Child(Base) {\n  fn own() -> Nil {}\n}\nval c = Child()\nc.\n"
    )
    main.write_text(source, encoding="utf-8")
    process = _start_with_root(tmp_path, {"completion": {"inheritedMembers": False}})
    try:
        _open_document(process, main, source)
        position = {"line": 5, "character": 2}
        first = cast(
            dict[str, Any],
            _request(
                process,
                2,
                "textDocument/completion",
                {"textDocument": {"uri": main.as_uri()}, "position": position},
            ),
        )
        assert "greet" not in {item["label"] for item in first["items"]}
        assert "own" in {item["label"] for item in first["items"]}

        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeConfiguration",
                "params": {"settings": {"completion": {"inheritedMembers": True}}},
            },
        )
        second = cast(
            dict[str, Any],
            _request(
                process,
                3,
                "textDocument/completion",
                {"textDocument": {"uri": main.as_uri()}, "position": position},
            ),
        )
        assert "greet" in {item["label"] for item in second["items"]}

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_signature_help_importado_herdado_e_construtor(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text(
        "class Point {\n"
        "  val x: Int\n"
        "  init(x: Int) { this.x = x }\n"
        "  fn dist(other: Int) -> Int { return 1 }\n"
        "}\n"
        "fn add(a: Int, b: Int) -> Int { return a + b }\n"
        "class Base {\n  fn greet(who: String) -> Nil {}\n}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    source = (
        "from mod import Point, add, Base\n"
        "val p = Point(1)\n"
        "val q = p.dist(1)\n"
        "print(add(1, 2))\n"
        "class Child(Base) {\n}\n"
        "val c = Child()\n"
        'c.greet("x")\n'
    )
    main.write_text(source, encoding="utf-8")
    process = _start_with_root(tmp_path)
    try:
        _open_document(process, main, source)

        def signature(line: int, character: int) -> dict[str, Any]:
            return cast(
                dict[str, Any],
                _request(
                    process,
                    line + 10,
                    "textDocument/signatureHelp",
                    {
                        "textDocument": {"uri": main.as_uri()},
                        "position": {"line": line, "character": character},
                    },
                ),
            )

        add = signature(3, 10)
        assert add["signatures"][0]["label"] == "fn add(a: Int, b: Int) -> Int"
        assert add["activeParameter"] == 0

        dist = signature(2, 15)
        assert "fn dist(other: Int) -> Int" in dist["signatures"][0]["label"]

        constructor = signature(1, 14)
        assert constructor["signatures"][0]["label"] == "class Point(x: Int)"

        inherited = signature(7, 8)
        assert inherited["signatures"][0]["label"] == "fn greet(who: String) -> Nil"
        assert "$" not in str(add)

        send(process, {"jsonrpc": "2.0", "id": 20, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_inlay_hints_de_tipos_inferidos(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text(
        "class Point {\n  val x: Int\n  init(x: Int) { this.x = x }\n}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    source = (
        "from mod import Point\n"
        "val a = 1\n"
        "val b: Int = 2\n"
        'var s = "x"\n'
        "val p = Point(1)\n"
        "for n in [1, 2] {\n"
        "  print(n)\n"
        "}\n"
        "class C {\n"
        "  val field = 3\n"
        "}\n"
    )
    main.write_text(source, encoding="utf-8")
    process = _start_with_root(tmp_path, {"inlayHints": {"enabled": False}})
    try:
        _open_document(process, main, source)
        request = {
            "textDocument": {"uri": main.as_uri()},
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 20, "character": 0},
            },
        }
        disabled = _request(process, 2, "textDocument/inlayHint", request)
        assert disabled == []

        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeConfiguration",
                "params": {"settings": {"inlayHints": {"enabled": True}}},
            },
        )
        hints = cast(
            list[dict[str, Any]],
            _request(process, 3, "textDocument/inlayHint", request),
        )
        by_line = {hint["position"]["line"]: hint["label"] for hint in hints}
        assert by_line == {
            1: ": Int",
            3: ": String",
            4: ": Point",
            5: ": Int",
            9: ": Int",
        }
        assert all(hint["kind"] == 1 for hint in hints)

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_diagnostics_match_check_json(tmp_path: Path) -> None:
    script = tmp_path / "parity.lx"
    source = 'val x: Int = "a"\nprint(x)\n'
    script.write_text(source, encoding="utf-8")

    expected_result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--check", "--error-format=json", str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(expected_result.stdout)
    expected = payload["diagnostics"]

    process = _start_with_root(tmp_path)
    try:
        published = _open_document(process, script, source)
        diagnostics = cast(list[dict[str, Any]], published["params"]["diagnostics"])

        def position(line: int, column: int) -> dict[str, int]:
            text = source.splitlines()[line - 1]
            return {
                "line": line - 1,
                "character": len(text[: column - 1].encode("utf-16-le")) // 2,
            }

        normalized = [
            {
                "code": item["code"],
                "message": item["message"],
                "range": {
                    "start": position(
                        item["span"]["start"]["line"], item["span"]["start"]["column"]
                    ),
                    "end": position(item["span"]["end"]["line"], item["span"]["end"]["column"]),
                },
            }
            for item in expected
        ]
        actual = [
            {"code": item["code"], "message": item["message"], "range": item["range"]}
            for item in diagnostics
        ]

        def key(item: dict[str, Any]) -> tuple[str, int]:
            return (item["code"], item["range"]["start"]["line"])

        assert sorted(actual, key=key) == sorted(normalized, key=key)

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_rename_cross_file_semantico_ignora_homonimo(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text("fn foo() -> Int {\n  return 1\n}\n", encoding="utf-8")
    other = tmp_path / "other.lx"
    other.write_text("fn foo() -> Int {\n  return 2\n}\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("from mod import foo\nprint(foo())\n", encoding="utf-8")
    process = _start_with_root(tmp_path)
    try:
        _open_document(process, module, module.read_text(encoding="utf-8"))
        result = cast(
            dict[str, Any],
            _request(
                process,
                2,
                "textDocument/rename",
                {
                    "textDocument": {"uri": module.as_uri()},
                    "position": {"line": 0, "character": 4},
                    "newName": "bar",
                },
            ),
        )
        changes = cast(dict[str, list[dict[str, Any]]], result["changes"])
        assert set(changes) == {module.as_uri(), main.as_uri()}
        assert other.as_uri() not in changes
        assert len(changes[module.as_uri()]) == 1
        assert len(changes[main.as_uri()]) == 2
        assert all(edit["newText"] == "bar" for edits in changes.values() for edit in edits)

        _open_document(process, main, main.read_text(encoding="utf-8"))
        prepared = cast(
            dict[str, Any],
            _request(
                process,
                3,
                "textDocument/prepareRename",
                {
                    "textDocument": {"uri": main.as_uri()},
                    "position": {"line": 1, "character": 7},
                },
            ),
        )
        assert prepared["placeholder"] == "foo"
        assert prepared["range"]["start"] == {"line": 1, "character": 6}

        send(process, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_rename_cross_file_preserva_alias_e_namespace(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text("fn foo() -> Int {\n  return 1\n}\n", encoding="utf-8")
    alias_file = tmp_path / "alias.lx"
    alias_source = "from mod import foo as f\nprint(f())\n"
    alias_file.write_text(alias_source, encoding="utf-8")
    namespace_file = tmp_path / "namespace.lx"
    namespace_file.write_text("import mod\nprint(mod.foo())\n", encoding="utf-8")
    process = _start_with_root(tmp_path)
    try:
        _open_document(process, module, module.read_text(encoding="utf-8"))
        result = cast(
            dict[str, Any],
            _request(
                process,
                2,
                "textDocument/rename",
                {
                    "textDocument": {"uri": module.as_uri()},
                    "position": {"line": 0, "character": 4},
                    "newName": "bar",
                },
            ),
        )
        changes = cast(dict[str, list[dict[str, Any]]], result["changes"])
        alias_edits = changes[alias_file.as_uri()]
        assert len(alias_edits) == 1
        assert alias_edits[0]["range"]["start"] == {"line": 0, "character": 16}
        assert alias_edits[0]["newText"] == "bar"
        namespace_edits = changes[namespace_file.as_uri()]
        assert len(namespace_edits) == 1
        assert namespace_edits[0]["range"]["start"] == {"line": 1, "character": 10}

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_rename_cross_file_de_tipo_atualiza_anotacao(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text(
        "class Point {\n  val x: Int\n  init(x: Int) { this.x = x }\n}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text(
        "from mod import Point\nval p: Point = Point(1)\nprint(p.x)\n",
        encoding="utf-8",
    )
    process = _start_with_root(tmp_path)
    try:
        _open_document(process, module, module.read_text(encoding="utf-8"))
        result = cast(
            dict[str, Any],
            _request(
                process,
                2,
                "textDocument/rename",
                {
                    "textDocument": {"uri": module.as_uri()},
                    "position": {"line": 0, "character": 7},
                    "newName": "Q",
                },
            ),
        )
        changes = cast(dict[str, list[dict[str, Any]]], result["changes"])
        assert set(changes) == {module.as_uri(), main.as_uri()}
        main_positions = {
            (edit["range"]["start"]["line"], edit["range"]["start"]["character"])
            for edit in changes[main.as_uri()]
        }
        assert main_positions == {
            (0, 16),
            (1, 7),
            (1, 15),
        }

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_lsp_rename_cross_file_recusa_colisao(tmp_path: Path) -> None:
    module = tmp_path / "mod.lx"
    module.write_text("fn foo() -> Int {\n  return 1\n}\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("from mod import foo\nval bar = 1\nprint(foo())\n", encoding="utf-8")
    process = _start_with_root(tmp_path)
    try:
        _open_document(process, module, module.read_text(encoding="utf-8"))
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/rename",
                "params": {
                    "textDocument": {"uri": module.as_uri()},
                    "position": {"line": 0, "character": 4},
                    "newName": "bar",
                },
            },
        )
        response = read(process)
        assert "already used" in response["error"]["message"]

        send(process, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        read(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
