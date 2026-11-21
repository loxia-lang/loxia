# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tabela única de primitivas (ADR-0071)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.primitives import (
    GROUP_BUDGET,
    KERNEL_BUDGET,
    NATIVE_MODULE_BUDGET,
    PRIMITIVES,
    Primitive,
    PrimitiveCallable,
    budget_violations,
    primitive_group,
)
from loxia_core.frontend.ty import INT, NIL, STRING, ListTy


def test_tabela_tem_ordem_e_assinaturas_estaveis() -> None:
    assert [primitive.lox for primitive in PRIMITIVES] == [
        "substr",
        "join",
        "charCodeAt",
        "fromCodePoint",
        "args",
        "io.readFile",
        "io.readAll",
        "io.write",
        "io.writeErr",
        "io.writeFile",
        "io.readLine",
        "io.readUtf8",
        "io.flush",
        "fs.exists",
        "fs.listDir",
        "fs.open",
        "fs.read",
        "fs.write",
        "fs.close",
        "os.exit",
        "os.getenv",
        "process.spawn",
        "process.stdin",
        "process.stdout",
        "process.stderr",
        "process.wait",
        "process.kill",
        "process.close",
        "process.read",
        "process.write",
        "process.poll",
        "time.now",
        "time.sleep",
    ]
    signatures = {primitive.lox: (primitive.params, primitive.result) for primitive in PRIMITIVES}
    assert signatures["substr"] == ((STRING, INT, INT), STRING)
    assert signatures["join"] == ((ListTy(STRING), STRING), STRING)
    assert signatures["charCodeAt"] == ((STRING, INT), INT)
    assert signatures["fromCodePoint"] == ((INT,), STRING)


def test_adaptador_respeita_aridade_da_tabela() -> None:
    for primitive in PRIMITIVES:
        callable_ = PrimitiveCallable(primitive)
        assert callable_.min_arity() == len(primitive.params)
        assert callable_.max_arity() == len(primitive.params)


def test_oraculo_de_arquivo(tmp_path: Path) -> None:
    from loxia_core.execution.primitives import PRIMITIVE_BY_LOX

    path = tmp_path / "saida.txt"
    write = PRIMITIVE_BY_LOX["io.writeFile"].py
    read = PRIMITIVE_BY_LOX["io.readFile"].py

    assert write(str(path), "olá\n") is True
    assert read(str(path)) == "olá\n"


def test_oraculo_de_exists_e_list_dir(tmp_path: Path) -> None:
    from loxia_core.execution.primitives import PRIMITIVE_BY_LOX

    directory = tmp_path / "entrada"
    directory.mkdir()
    (directory / "b.txt").write_text("", encoding="utf-8")
    (directory / "a.txt").write_text("", encoding="utf-8")

    exists = PRIMITIVE_BY_LOX["fs.exists"].py
    list_dir = PRIMITIVE_BY_LOX["fs.listDir"].py

    assert exists(str(directory)) is True
    assert exists(str(tmp_path / "nao-existe")) is False
    result = list_dir(str(directory))
    assert isinstance(result, LoxList)
    assert result.elements == ["a.txt", "b.txt"]
    assert list_dir(str(tmp_path / "nao-existe")) is None
    assert list_dir(str(directory / "a.txt")) is None


def test_oraculo_de_args_usa_o_interpretador() -> None:
    from loxia_core.execution.primitives import PRIMITIVE_BY_LOX

    class _Interpreter:
        def __init__(self) -> None:
            self.argv = ["a", "b"]

    result = PRIMITIVE_BY_LOX["args"].py(_Interpreter())
    assert isinstance(result, LoxList)
    assert result.elements == ["a", "b"]


def test_grupo_e_o_namespace_da_primitiva() -> None:
    assert primitive_group("substr") == "core"
    assert primitive_group("io.write") == "io"
    assert primitive_group("process.spawn") == "proc"
    assert primitive_group("digest.sha256") == "digest"


def test_orcamento_do_kernel_por_grupo() -> None:
    assert budget_violations(PRIMITIVES, GROUP_BUDGET, KERNEL_BUDGET) == []

    counts = Counter(primitive.group for primitive in PRIMITIVES)
    assert counts == {"core": 5, "io": 8, "fs": 6, "os": 2, "proc": 10, "time": 2}
    assert sum(counts.values()) == len(PRIMITIVES) == 33
    assert sum(GROUP_BUDGET.values()) == KERNEL_BUDGET


def test_orcamento_de_modulo_nativo_e_separado() -> None:
    assert "sqlite3" not in GROUP_BUDGET
    assert NATIVE_MODULE_BUDGET == {"sqlite3": 20}
    assert {primitive.group for primitive in PRIMITIVES}.isdisjoint(NATIVE_MODULE_BUDGET)


def test_orcamento_detecta_estouro_de_grupo_e_de_total() -> None:
    def fake(name: str) -> Primitive:
        return Primitive(name, "lox_fake", (), NIL, lambda: None)

    overflow = [fake("io.fake") for _ in range(9)]
    assert budget_violations(overflow, {"io": 8}, 8) == [
        "group 'io' has 9, budget 8",
        "kernel has 9 primitives, budget 8",
    ]
    assert budget_violations([fake("nope.fake")], {"io": 8}) == ["group 'nope' has no budget"]
