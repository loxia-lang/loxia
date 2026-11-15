"""Tabela única de primitivas (ADR-0071)."""

from __future__ import annotations

from pathlib import Path

from src.execution.lox_list import LoxList
from src.execution.primitives import PRIMITIVES, PrimitiveCallable
from src.frontend.ty import INT, STRING, ListTy


def test_tabela_tem_ordem_e_assinaturas_estaveis() -> None:
    assert [primitive.lox for primitive in PRIMITIVES] == [
        "substr",
        "join",
        "charCodeAt",
        "fromCodePoint",
        "args",
        "io.readFile",
        "io.write",
        "io.writeErr",
        "io.writeFile",
        "io.readLine",
        "os.exit",
        "os.getenv",
        "time.now",
        "time.sleep",
    ]
    signatures = {
        primitive.lox: (primitive.params, primitive.result)
        for primitive in PRIMITIVES
    }
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
    from src.execution.primitives import PRIMITIVE_BY_LOX

    path = tmp_path / "saida.txt"
    write = PRIMITIVE_BY_LOX["io.writeFile"].py
    read = PRIMITIVE_BY_LOX["io.readFile"].py

    assert write(str(path), "olá\n") is True
    assert read(str(path)) == "olá\n"


def test_oraculo_de_args_usa_o_interpretador() -> None:
    from src.execution.primitives import PRIMITIVE_BY_LOX

    class _Interpreter:
        def __init__(self) -> None:
            self.argv = ["a", "b"]

    result = PRIMITIVE_BY_LOX["args"].py(_Interpreter())
    assert isinstance(result, LoxList)
    assert result.elements == ["a", "b"]
