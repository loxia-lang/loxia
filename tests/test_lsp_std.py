# SPDX-License-Identifier: MIT OR Apache-2.0
"""LSP: definição e hover de funções/módulos da stdlib empacotada.

O `token.file` do loader é lógico (`std/io.lx`); o servidor precisa resolvê-lo para o
arquivo real (clone ou wheel), não para `<workspace>/std/io.lx`.
"""

from __future__ import annotations

from pathlib import Path

from loxia.lsp import _uri_to_path
from loxia_core.bundle import bundle_dir
from tests.test_lsp import _open_document, _start_with_root, read, send


def test_definition_reaches_bundled_std_module(tmp_path: Path) -> None:
    main = tmp_path / "main.lx"
    text = 'import std.io as io\n\nio.write("x")\n'
    main.write_text(text, encoding="utf-8")
    expected = (bundle_dir("std") / "io.lx").resolve()

    process = _start_with_root(tmp_path)
    try:
        _open_document(process, main, text)

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/definition",
                "params": {
                    "textDocument": {"uri": main.as_uri()},
                    "position": {"line": 2, "character": 4},
                },
            },
        )
        definition = read(process)["result"]
        target = _uri_to_path(definition["uri"])
        assert target is not None and target.resolve() == expected
        assert definition["range"]["start"] == {"line": 10, "character": 3}

        # No alias do import (`io`), a definição aponta para o arquivo do módulo.
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/definition",
                "params": {
                    "textDocument": {"uri": main.as_uri()},
                    "position": {"line": 2, "character": 1},
                },
            },
        )
        module = read(process)["result"]
        module_target = _uri_to_path(module["uri"])
        assert module_target is not None and module_target.resolve() == expected

        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "textDocument/hover",
                "params": {
                    "textDocument": {"uri": main.as_uri()},
                    "position": {"line": 2, "character": 4},
                },
            },
        )
        hover = read(process)["result"]["contents"]["value"]
        assert "fn std.io.write(text: String) -> Nil" in hover
        assert "$" not in hover

        send(process, {"jsonrpc": "2.0", "id": 5, "method": "shutdown", "params": {}})
        read(process)
        send(process, {"jsonrpc": "2.0", "method": "exit"})
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
