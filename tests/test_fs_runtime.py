# SPDX-License-Identifier: MIT OR Apache-2.0
"""Contratos de handles de `std.fs` no tree-walk (ADR-0119)."""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia.engine import Loxia
from loxia_core.execution.fs_runtime import FileTable


def test_read_utf8_pending_respeita_o_teto_de_bytes(tmp_path: Path) -> None:
    target = tmp_path / "utf8.txt"
    target.write_text("éxABCD", encoding="utf-8")
    table = FileTable()
    identifier = table.open(str(target), "r")

    try:
        assert table.read(identifier, 1) == ""
        assert table.read(identifier, 2) == "é"
        assert table.read(identifier, 1) == "x"
        assert table.read(identifier, 2) == "AB"
        assert table.read(identifier, 2) == "CD"
        assert table.read(identifier, 1) is None
    finally:
        table.close_all()


def test_handles_nao_sobrevivem_entre_execucoes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "dados.txt"
    target.write_text("abc", encoding="utf-8")
    lox = Loxia()

    lox.use_file("<um>", module_root=tmp_path)
    lox.run(
        "import std.fs as fs\n"
        f'val r = fs.open("{target}", "r")\n'
        "val f = match r { Result.Ok(h) => h, Result.Err(_) => nil }\n"
        "print(f != nil)\n"
    )
    capsys.readouterr()

    lox.use_file("<dois>", module_root=tmp_path)
    lox.run(
        "import std.fs as fs\n"
        "val antigo = fs.File(1)\n"
        'print(match antigo.read(1) { Result.Ok(_) => "vivo", Result.Err(e) => e.kind })\n'
    )

    assert "closed" in capsys.readouterr().out
