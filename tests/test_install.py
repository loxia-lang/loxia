# SPDX-License-Identifier: MIT OR Apache-2.0
"""Instalação real: wheel fora do repo, comando `loxia` e stdlib (ADR-0088).

Fora da suíte padrão (`-m install`): builda o wheel e cria um venv. É o teste que
prova que `pip install loxia` entrega comando + `std/` + `runtime.c`, e não só o clone.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True, timeout=600)


@pytest.mark.install
def test_wheel_instala_fora_do_repo_e_roda_stdlib(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv não está no PATH")

    dist = tmp_path / "dist"
    _run("uv", "build", "--out-dir", str(dist), cwd=ROOT)

    wheel = next(dist.glob("loxia-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()

    assert any(name.endswith("loxia_core/std/json.lx") for name in names)
    assert any(name.endswith("loxia_core/runtime/lox_runtime.h") for name in names)
    assert any(name.endswith("loxia_core/runtime/kernel.c") for name in names)
    # Módulo embutido e fontes do crate (ADR-0126/0131): sem eles o `import regex`
    # instalado quebra e o build on-demand não tem o que compilar.
    assert any(name.endswith("loxia_core/bundled/regex.lx") for name in names)
    assert any(name.endswith("loxia_core/native/regex/Cargo.toml") for name in names)
    assert any(name.endswith("loxia_core/native/regex/Cargo.lock") for name in names)
    assert any("loxia_core/native/regex/vendor/" in name for name in names)
    assert not any("/native/regex/target/" in name for name in names)
    # O índice de docs é um artefato gerado e precisa viajar no wheel (ADR-0111).
    assert any(name.endswith("loxia/_spec/index.json") for name in names)
    assert any(name.endswith("loxia/mcp.py") for name in names)
    entry_points = next(name for name in names if name.endswith("entry_points.txt"))
    with zipfile.ZipFile(wheel) as archive:
        entry_text = archive.read(entry_points).decode("utf-8")
    assert "loxia-mcp = loxia.mcp:main" in entry_text

    # Um `std/` só: a sdist carrega a pasta na raiz e o wheel a move para dentro
    # do pacote (force-include do hatchling). Cópia nos dois lugares = instalação
    # com dois módulos e build não determinístico.
    assert not any(name.startswith("std/") for name in names)

    sdist = next(dist.glob("loxia-*.tar.gz"))
    with tarfile.open(sdist) as archive:
        sdist_names = archive.getnames()

    assert any(name.endswith("/std/json.lx") and "/loxia_core/" not in name for name in sdist_names)
    assert any(name.endswith("/bundled/regex.lx") for name in sdist_names)
    assert any(name.endswith("/native/regex/Cargo.toml") for name in sdist_names)
    assert any(name.endswith("/server.json") for name in sdist_names)
    assert not any("/loxia_core/std/" in name for name in sdist_names)
    assert not any("/loxia_core/native/" in name for name in sdist_names)
    assert not any("/native/regex/target/" in name for name in sdist_names)

    venv = tmp_path / "venv"
    _run("uv", "venv", str(venv), "--python", "3.13", cwd=tmp_path)
    python = venv / "bin" / "python"
    _run(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--no-deps",
        str(wheel),
        cwd=tmp_path,
    )

    work = tmp_path / "work"
    work.mkdir()
    (work / "programa.lx").write_text(
        'import std.json as json\nprint(json.stringify({"ok": true}))\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(venv / "bin" / "loxia"), str(work / "programa.lx")],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '{"ok":true}'

    # O entry point e o índice de docs também precisam funcionar fora do repo.
    mcp = subprocess.run(
        [str(venv / "bin" / "loxia-mcp")],
        cwd=work,
        input=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "loxia_version",
                    "arguments": {},
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientCapabilities": {},
                    },
                },
            }
        )
        + "\n",
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert mcp.returncode == 0, mcp.stderr
    version = json.loads(mcp.stdout)["result"]["structuredContent"]
    assert version["protocol_version"] == "2026-07-28"
    assert version["docs_pages"] > 0
