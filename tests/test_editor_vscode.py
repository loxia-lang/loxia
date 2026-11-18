# SPDX-License-Identifier: MIT OR Apache-2.0
"""Extensão VS Code: manifesto, grammar e cliente LSP autocontido."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VSCODE = ROOT / "editors" / "vscode"


def test_manifesto_aponta_para_o_cliente_e_o_servidor() -> None:
    manifest = json.loads((VSCODE / "package.json").read_text(encoding="utf-8"))
    assert manifest["main"] == "./extension.js"
    assert "onLanguage:loxia" in manifest["activationEvents"]
    assert manifest["contributes"]["languages"][0]["id"] == "loxia"
    grammar = manifest["contributes"]["grammars"][0]
    assert (VSCODE / grammar["path"]).is_file()
    properties = manifest["contributes"]["configuration"]["properties"]
    assert properties["loxia.server.path"]["default"] == ""
    assert properties["loxia.server.args"]["default"] == ["lsp"]
    assert properties["loxia.inlayHints.enabled"]["default"] is True
    assert properties["loxia.completion.inheritedMembers"]["default"] is True
    assert manifest["contributes"]["commands"][0]["command"] == "loxia.restartServer"


def test_cliente_cobre_os_metodos_do_servidor() -> None:
    source = (VSCODE / "extension.js").read_text(encoding="utf-8")
    for method in (
        "textDocument/formatting",
        "textDocument/hover",
        "textDocument/definition",
        "textDocument/completion",
        "textDocument/signatureHelp",
        "textDocument/inlayHint",
        "textDocument/codeAction",
        "textDocument/prepareRename",
        "textDocument/rename",
        "textDocument/documentSymbol",
        "workspace/symbol",
        "textDocument/publishDiagnostics",
    ):
        assert method in source
    assert "vscode-languageclient" not in source
    assert "python3" in source
    assert "uv" in source
    assert "vscode.languages.registerWorkspaceSymbolProvider" in source
    assert "vscode.workspace.registerWorkspaceSymbolProvider" not in source
    assert "vscode.languages.registerInlayHintsProvider" in source
    assert "initializationOptions" in source
    assert "workspace/didChangeConfiguration" in source


def test_cliente_tem_sintaxe_valida() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node não instalado")
    result = subprocess.run(
        [node, "--check", str(VSCODE / "extension.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
