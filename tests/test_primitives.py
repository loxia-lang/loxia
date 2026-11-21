# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tabela única de primitivas (ADR-0071)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.primitives import (
    GROUP_BUDGET,
    KERNEL_BUDGET,
    NATIVE_MODULE_BUDGET,
    PRIMITIVE_BY_LOX,
    PRIMITIVES,
    Primitive,
    PrimitiveCallable,
    budget_violations,
    is_sandbox_denied,
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
        "fs.readBytes",
        "fs.write",
        "fs.close",
        "fs.rename",
        "fs.remove",
        "fs.mkdir",
        "fs.stat",
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
        "digest.sha256",
        "digest.sha256Bytes",
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
    assert counts == {"core": 5, "io": 8, "fs": 11, "os": 2, "proc": 10, "time": 2, "digest": 2}
    assert sum(counts.values()) == len(PRIMITIVES) == 40
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


def _primitive(*, ambient: bool = False, native_only: bool = False) -> Primitive:
    return Primitive(
        "fake.fn",
        "lox_fake",
        (),
        NIL,
        lambda: None,
        ambient=ambient,
        native_only=native_only,
    )


def test_camada_deriva_dos_dois_eixos() -> None:
    assert _primitive().layer == "core"
    assert _primitive(ambient=True).layer == "ambient"
    assert _primitive(native_only=True).layer == "native-only"
    # Nativo e ambient (ex.: thread) continua native-only: o rótulo projeta o motor.
    assert _primitive(ambient=True, native_only=True).layer == "native-only"


def test_sandbox_nega_native_only(monkeypatch: pytest.MonkeyPatch) -> None:
    assert is_sandbox_denied("io.readFile")
    assert is_sandbox_denied("process.spawn")
    assert is_sandbox_denied("fs.rename")
    assert is_sandbox_denied("fs.remove")
    assert is_sandbox_denied("fs.mkdir")
    assert is_sandbox_denied("fs.stat")
    assert is_sandbox_denied("fs.readBytes")
    assert not is_sandbox_denied("io.write")
    assert not is_sandbox_denied("digest.sha256")

    monkeypatch.setitem(PRIMITIVE_BY_LOX, "fake.fn", _primitive(native_only=True))
    assert is_sandbox_denied("fake.fn")


def test_backstop_recusa_native_only_no_dispatch() -> None:
    with pytest.raises(NativeError, match="not supported by the interpreter"):
        PrimitiveCallable(_primitive(native_only=True)).call(None, [])


def test_oraculo_de_sha256_bytes_bate_com_hashlib() -> None:
    import hashlib

    sha256_bytes = PRIMITIVE_BY_LOX["digest.sha256Bytes"].py

    for data in [b"", b"abc", "olá".encode()]:
        assert sha256_bytes(data) == hashlib.sha256(data).digest()


def test_oraculo_de_sha256_bate_com_hashlib() -> None:
    import hashlib

    sha256 = PRIMITIVE_BY_LOX["digest.sha256"].py

    for text in ["", "abc", "olá", "a" * 1000]:
        assert sha256(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
