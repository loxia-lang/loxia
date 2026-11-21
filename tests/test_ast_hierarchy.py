# SPDX-License-Identifier: MIT OR Apache-2.0
"""Guarda a hierarquia da AST e a cobertura dos visitantes.

`AstPrinter` herda os protocols de `Visitor`, então o mypy passa a exigir todos os
`visit_*`; este teste impede que a base seja removida sem ninguém notar. A mesma ideia
vale para os nós: todo nó concreto precisa herdar `Expr`/`Stmt`.
"""

from __future__ import annotations

import inspect
from types import ModuleType

from loxia_core.frontend import expr, stmt
from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.expr import Visitor as ExprVisitor
from loxia_core.frontend.stmt import Visitor as StmtVisitor


def _concrete_nodes(module: ModuleType) -> list[type[object]]:
    return [
        cls
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if cls.__module__ == module.__name__ and hasattr(cls, "accept")
    ]


def test_expr_nodes_inherit_expr() -> None:
    nodes = _concrete_nodes(expr)

    assert nodes
    for cls in nodes:
        if cls is expr.Expr:
            continue
        assert expr.Expr in cls.__mro__, cls.__name__


def test_stmt_nodes_inherit_stmt() -> None:
    nodes = _concrete_nodes(stmt)

    assert nodes
    for cls in nodes:
        if cls is stmt.Stmt:
            continue
        assert stmt.Stmt in cls.__mro__, cls.__name__


def test_ast_printer_inherits_visitor_protocols() -> None:
    assert ExprVisitor in AstPrinter.__mro__
    assert StmtVisitor in AstPrinter.__mro__
