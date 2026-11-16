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
