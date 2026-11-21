# SPDX-License-Identifier: MIT OR Apache-2.0
"""Camadas de motor (ADR-0128): core, ambient e native-only.

A camada é derivada de **dois eixos independentes**: `ambient` (determinismo) e
`native_only` (motor). O rótulo é só a projeção para humanos e docs, com
precedência `native-only` > `ambient` > `core`; assim uma capacidade nativa e
ambient (thread) ou nativa e determinística (SIMD puro) não mente em nenhum eixo.

O passe daqui é o lado "UX" da recusa: roda antes de executar e produz `E3021` no
call site. O backstop de runtime fica em `PrimitiveCallable.call`, para o caso de a
capacidade escapar por alias/sombreamento.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, is_dataclass

from loxia_core.execution.primitives import API_LAYERS, PRIMITIVES, Primitive
from loxia_core.frontend.expr import Expr, Get, Variable
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.tokens import Token

NATIVE_ONLY = "native-only"


@dataclass(frozen=True)
class NativeOnlyUse:
    """Referência a uma capacidade que o interpretador não tem."""

    name: str
    token: Token


def layer_index(
    primitives: Iterable[Primitive] = PRIMITIVES,
    api_layers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Nome qualificado (`namespace.member` ou `modulo.funcao`) → camada."""
    index = {primitive.lox: primitive.layer for primitive in primitives}
    index.update(API_LAYERS if api_layers is None else api_layers)
    return index


def native_only_uses(
    statements: Iterable[Stmt],
    locals: Mapping[Expr, int],
    *,
    index: Mapping[str, str] | None = None,
) -> list[NativeOnlyUse]:
    """Usos de capacidade native-only, na ordem da árvore.

    `locals` é o mapa do resolver (`Expr` → distância): um nome local que sombreia
    um namespace (permitido pelo ADR-0016) não conta. Nome global é reservado e o
    `--check` recusa a redefinição; `run` sem check não cobre esse caso.
    """
    table = index if index is not None else layer_index()
    uses: list[NativeOnlyUse] = []
    for statement in statements:
        _walk(statement, table, locals, uses)
    return uses


def _walk(
    node: object,
    table: Mapping[str, str],
    locals: Mapping[Expr, int],
    uses: list[NativeOnlyUse],
) -> None:
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, table, locals, uses)
        return
    if (
        isinstance(node, Get)
        and isinstance(node.object, Variable)
        and locals.get(node.object) is None
    ):
        qualified = f"{node.object.name.lexeme}.{node.name.lexeme}"
        if table.get(qualified) == NATIVE_ONLY:
            uses.append(NativeOnlyUse(qualified, node.name))
    # `Expr`/`Stmt` são Protocols (não runtime_checkable); os nós são dataclasses.
    if is_dataclass(node) and not isinstance(node, type):
        for value in vars(node).values():
            _walk(value, table, locals, uses)
