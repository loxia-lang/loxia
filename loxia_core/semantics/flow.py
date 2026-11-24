# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fluxo de refinamentos do checker: chave, merge, contexto de laço e política (ADR-0141).

O contrato: um refino só vale se for dominado por um teste em **todos** os caminhos que
chegam ao uso. Na dúvida, o refino é derrubado; o checker nunca inventa um refino que o
caminho não provou.

`STMT_FLOW`/`EXPR_FLOW` declaram o que cada nó faz com o estado de fluxo. Um nó novo sem
entrada quebra `tests/test_checker_flow.py` — esquecer a política é erro de CI, não bug em
produção (o mesmo mecanismo do ADR-0117 para visitantes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from loxia_core.frontend import expr as ast_expr
from loxia_core.frontend import stmt as ast_stmt
from loxia_core.frontend.ty import NEVER, Ty, union

RefinementKey = tuple[int, str, tuple[tuple[str, object], ...]]
"""Chave de refinamento: índice do escopo de declaração + raiz + caminho."""

RefinementState = dict[RefinementKey, Ty]
"""Refinamentos vivos em um ponto do programa."""


class FlowPolicy(Enum):
    """O que um nó de AST faz com o estado de fluxo."""

    TRANSPARENT = "transparent"
    """Não abre caminhos; pode atualizar ou matar refinos no lugar (ex.: `Assign`)."""

    FORK = "fork"
    """Cada ramo parte do estado de entrada; a saída é o merge dos ramos que caem."""

    LOOP = "loop"
    """Corpo zero-ou-mais; `break` concorre à saída e a condição falsa só vale no
    fallthrough (não quando há `break`)."""

    JUMP = "jump"
    """`break`/`continue`: sai para o contexto de laço mais interno."""

    TERMINATOR = "terminator"
    """`return`/`raise`: não cai para a instrução seguinte."""

    ISOLATED = "isolated"
    """Corpo com estado de fluxo (e pilha de laços) próprio: função/lambda."""


STMT_FLOW: dict[type, FlowPolicy] = {
    ast_stmt.Import: FlowPolicy.TRANSPARENT,
    ast_stmt.Block: FlowPolicy.TRANSPARENT,
    ast_stmt.Class: FlowPolicy.TRANSPARENT,
    ast_stmt.TypeAlias: FlowPolicy.TRANSPARENT,
    ast_stmt.Interface: FlowPolicy.TRANSPARENT,
    ast_stmt.EnumDecl: FlowPolicy.TRANSPARENT,
    ast_stmt.Try: FlowPolicy.FORK,
    ast_stmt.Raise: FlowPolicy.TERMINATOR,
    ast_stmt.ErrorStmt: FlowPolicy.TRANSPARENT,
    ast_stmt.Expression: FlowPolicy.TRANSPARENT,
    ast_stmt.Function: FlowPolicy.ISOLATED,
    ast_stmt.ForIn: FlowPolicy.LOOP,
    ast_stmt.If: FlowPolicy.FORK,
    ast_stmt.Return: FlowPolicy.TERMINATOR,
    ast_stmt.Break: FlowPolicy.JUMP,
    ast_stmt.Continue: FlowPolicy.JUMP,
    ast_stmt.Var: FlowPolicy.TRANSPARENT,
    ast_stmt.Destructure: FlowPolicy.TRANSPARENT,
    ast_stmt.While: FlowPolicy.LOOP,
}

EXPR_FLOW: dict[type, FlowPolicy] = {
    ast_expr.Binary: FlowPolicy.TRANSPARENT,
    ast_expr.Grouping: FlowPolicy.TRANSPARENT,
    ast_expr.Is: FlowPolicy.TRANSPARENT,
    ast_expr.As: FlowPolicy.TRANSPARENT,
    ast_expr.ErrorExpr: FlowPolicy.TRANSPARENT,
    ast_expr.Literal: FlowPolicy.TRANSPARENT,
    ast_expr.InterpolatedString: FlowPolicy.TRANSPARENT,
    ast_expr.Lambda: FlowPolicy.ISOLATED,
    ast_expr.ListLiteral: FlowPolicy.TRANSPARENT,
    ast_expr.MapLiteral: FlowPolicy.TRANSPARENT,
    ast_expr.Index: FlowPolicy.TRANSPARENT,
    ast_expr.IndexSet: FlowPolicy.TRANSPARENT,
    ast_expr.Match: FlowPolicy.FORK,
    ast_expr.TupleLiteral: FlowPolicy.TRANSPARENT,
    ast_expr.Range: FlowPolicy.TRANSPARENT,
    ast_expr.Unary: FlowPolicy.TRANSPARENT,
    ast_expr.Assign: FlowPolicy.TRANSPARENT,
    ast_expr.Call: FlowPolicy.TRANSPARENT,
    ast_expr.Conditional: FlowPolicy.FORK,
    ast_expr.Get: FlowPolicy.TRANSPARENT,
    ast_expr.Logical: FlowPolicy.FORK,
    ast_expr.Set: FlowPolicy.TRANSPARENT,
    ast_expr.Super: FlowPolicy.TRANSPARENT,
    ast_expr.This: FlowPolicy.TRANSPARENT,
    ast_expr.Variable: FlowPolicy.TRANSPARENT,
}


@dataclass(frozen=True)
class Invalidation:
    """Operação de invalidação de refino, para replay em outro estado de fluxo.

    `try`/`finally` roda antes de um `break`/`continue`/`return` concluir o salto: o
    estado gravado no salto precisa receber as invalidações do `finally` (ADR-0141).
    Só invalidações são replicadas; refinos (narrowing) do `finally` podem depender do
    caminho de entrada e por isso não são reaplicados.
    """

    kind: str
    index: int = 0
    name: str = ""
    key: RefinementKey | None = None


def join_states(left: RefinementState, right: RefinementState) -> RefinementState:
    """Merge conservador: só sobrevive a chave presente nos dois, com tipo unificado."""
    result: RefinementState = {}
    for key in left.keys() & right.keys():
        left_ty = left[key]
        right_ty = right[key]
        if left_ty == right_ty:
            result[key] = left_ty
            continue
        merged = union(left_ty, right_ty)
        if merged is not NEVER:
            result[key] = merged
    return result


def join_exits(*states: RefinementState) -> RefinementState:
    """Merge de todas as saídas que chegam ao mesmo ponto (ordem: entrada primeiro)."""
    if not states:
        return {}
    merged = dict(states[0])
    for state in states[1:]:
        merged = join_states(merged, state)
    return merged


@dataclass
class LoopContext:
    """Saídas do laço mais interno que chegam ao merge pós-laço.

    `break` registra o estado do ponto do salto; `continue` volta ao topo e não concorre
    à saída. Sem fixpoint de laço, o estado é conservador, nunca inventado.
    """

    breaks: list[RefinementState] = field(default_factory=list)

    @property
    def has_break(self) -> bool:
        return bool(self.breaks)
