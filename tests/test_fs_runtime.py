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


def test_rename_remove_mkdir_e_stat(tmp_path: Path) -> None:
    from loxia_core.diagnostics.errors import NativeError
    from loxia_core.execution.lox_tuple import LoxTuple
    from loxia_core.execution.primitives import PRIMITIVE_BY_LOX

    mkdir = PRIMITIVE_BY_LOX["fs.mkdir"].py
    stat = PRIMITIVE_BY_LOX["fs.stat"].py
    rename = PRIMITIVE_BY_LOX["fs.rename"].py
    remove = PRIMITIVE_BY_LOX["fs.remove"].py

    directory = tmp_path / "d"
    mkdir(str(directory))
    with pytest.raises(NativeError, match="alreadyExists"):
        mkdir(str(directory))

    target = directory / "a.txt"
    target.write_text("olá", encoding="utf-8")
    info = stat(str(target))
    assert isinstance(info, LoxTuple)
    size, mtime_ms, is_dir = info.items
    assert isinstance(size, int)
    assert isinstance(mtime_ms, int)
    assert isinstance(is_dir, bool)
    assert size == 4
    assert is_dir is False
    assert mtime_ms > 0
    directory_info = stat(str(directory))
    assert isinstance(directory_info, LoxTuple)
    assert directory_info.items[2] is True

    moved = directory / "b.txt"
    rename(str(target), str(moved))
    assert not target.exists()
    assert moved.exists()

    remove(str(moved))
    assert not moved.exists()
    with pytest.raises(NativeError, match="notFound"):
        stat(str(moved))
    with pytest.raises(NativeError, match="isDirectory"):
        remove(str(directory))


def test_std_fs_stat_e_write_atomic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()
    lox.use_file("<fs>", module_root=tmp_path)
    target = tmp_path / "a" / "b" / "out.txt"

    lox.run(
        "import std.fs as fs\n"
        "import std.results as results\n"
        f'val made = fs.mkdirAll("{target.parent}")\n'
        "print(results.isOk(made))\n"
        f'val wrote = fs.writeAtomic("{target}", "olá")\n'
        "print(results.isOk(wrote))\n"
        'print(match fs.stat("' + str(target) + '") '
        "{ Result.Ok(meta) => meta.size, Result.Err(_) => -1 })\n"
        f'print(fs.exists("{target}.tmp"))\n'
    )

    assert capsys.readouterr().out == "true\ntrue\n4\nfalse\n"
