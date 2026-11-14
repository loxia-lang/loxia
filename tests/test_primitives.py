"""Tabela única de primitivas (ADR-0071)."""

from __future__ import annotations

from src.execution.primitives import PRIMITIVES, PrimitiveCallable
from src.frontend.ty import INT, STRING, ListTy


def test_tabela_tem_ordem_e_assinaturas_estaveis() -> None:
    assert [primitive.lox for primitive in PRIMITIVES] == [
        "substr",
        "join",
        "charCodeAt",
        "fromCodePoint",
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
