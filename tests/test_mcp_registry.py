# SPDX-License-Identifier: MIT OR Apache-2.0
"""Contrato mínimo do `server.json` para o MCP Registry.

Não valida o JSON Schema inteiro (não adicionamos dependência); polia o que o registry
verifica: nome, versão, pacote PyPI, transporte, argumento e o marcador `mcp-name` no
README.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any, cast

from loxia import __version__

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server.json"


def _manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(SERVER.read_text(encoding="utf-8")))


def test_manifest_matches_project_and_readme() -> None:
    manifest = _manifest()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert manifest["$schema"].startswith("https://static.modelcontextprotocol.io/")
    assert manifest["name"] == "io.github.loxia-lang/loxia"
    assert manifest["version"] == __version__ == project["project"]["version"]
    assert f"mcp-name: {manifest['name']}" in readme
    assert manifest["websiteUrl"] == "https://loxia-lang.github.io/loxia/"
    assert manifest["repository"] == {
        "url": "https://github.com/loxia-lang/loxia",
        "source": "github",
    }


def test_pypi_package_runs_the_stdio_server() -> None:
    manifest = _manifest()
    packages = manifest["packages"]
    assert isinstance(packages, list) and len(packages) == 1
    package = packages[0]
    assert isinstance(package, dict)
    assert package["registryType"] == "pypi"
    assert package["identifier"] == "loxia"
    assert package["version"] == __version__
    assert package["runtimeHint"] == "uvx"
    assert package["transport"] == {"type": "stdio"}
    assert package["packageArguments"] == [{"type": "positional", "value": "mcp"}]
