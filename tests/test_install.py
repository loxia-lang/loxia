# SPDX-License-Identifier: MIT OR Apache-2.0
"""Instalação real: wheel fora do repo, comando `loxia` e stdlib (ADR-0088).

Fora da suíte padrão (`-m install`): builda o wheel e cria um venv. É o teste que
prova que `pip install loxia` entrega comando + `std/` + `runtime.c`, e não só o clone.
"""

from __future__ import annotations

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

    # Um `std/` só: a sdist carrega a pasta na raiz e o wheel a move para dentro
    # do pacote (force-include do hatchling). Cópia nos dois lugares = instalação
    # com dois módulos e build não determinístico.
    assert not any(name.startswith("std/") for name in names)

    sdist = next(dist.glob("loxia-*.tar.gz"))
    with tarfile.open(sdist) as archive:
        sdist_names = archive.getnames()

    assert any(name.endswith("/std/json.lx") and "/loxia_core/" not in name for name in sdist_names)
    assert not any("/loxia_core/std/" in name for name in sdist_names)

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
