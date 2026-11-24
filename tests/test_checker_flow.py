# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fluxo do checker: política por nó de AST e soundness de saltos (ADR-0141)."""

from __future__ import annotations

import pytest

from loxia.engine import Loxia
from loxia_core.diagnostics.codes import Code
from loxia_core.frontend import expr as ast_expr
from loxia_core.frontend import stmt as ast_stmt
from loxia_core.semantics.flow import EXPR_FLOW, STMT_FLOW, FlowPolicy


def check(source: str) -> Loxia:
    lox = Loxia(max_errors=0)
    lox.use_file("flow.lx")
    lox.check(source)
    return lox


def _subclasses(base: type) -> set[type]:
    found: set[type] = set()
    pending: list[type] = [base]
    while pending:
        children: list[type] = pending.pop().__subclasses__()
        for child in children:
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def test_every_statement_has_a_flow_policy() -> None:
    missing = sorted(cls.__name__ for cls in _subclasses(ast_stmt.Stmt) - set(STMT_FLOW))
    assert missing == [], f"declare a FlowPolicy para: {missing}"


def test_every_expression_has_a_flow_policy() -> None:
    missing = sorted(cls.__name__ for cls in _subclasses(ast_expr.Expr) - set(EXPR_FLOW))
    assert missing == [], f"declare a FlowPolicy para: {missing}"


def test_flow_tables_have_no_stale_entries() -> None:
    stale = sorted(
        cls.__name__
        for table, base in ((STMT_FLOW, ast_stmt.Stmt), (EXPR_FLOW, ast_expr.Expr))
        for cls in table
        if cls not in _subclasses(base)
    )
    assert stale == []


@pytest.mark.parametrize(
    ("node", "policy"),
    [
        (ast_stmt.If, FlowPolicy.FORK),
        (ast_stmt.While, FlowPolicy.LOOP),
        (ast_stmt.ForIn, FlowPolicy.LOOP),
        (ast_stmt.Try, FlowPolicy.FORK),
        (ast_stmt.Break, FlowPolicy.JUMP),
        (ast_stmt.Continue, FlowPolicy.JUMP),
        (ast_stmt.Return, FlowPolicy.TERMINATOR),
        (ast_stmt.Raise, FlowPolicy.TERMINATOR),
        (ast_expr.Match, FlowPolicy.FORK),
        (ast_expr.Lambda, FlowPolicy.ISOLATED),
    ],
)
def test_control_flow_nodes_have_the_expected_policy(node: type, policy: FlowPolicy) -> None:
    assert (STMT_FLOW.get(node) or EXPR_FLOW.get(node)) is policy


SOUNDNESS_CASES: list[tuple[str, str]] = [
    (
        "break_loop_condition",
        "var x: String? = nil\nwhile (x == nil) {\n  break\n}\nprint(len(x))\n",
    ),
    (
        "match_last_arm_leak",
        "var x: String? = nil\nval k = 1\n"
        'val r = match k {\n  0 => (x = "s")\n  _ => "t"\n}\nprint(len(x))\n',
    ),
]


@pytest.mark.parametrize(("case", "source"), SOUNDNESS_CASES)
def test_check_rejects_a_program_that_would_fail_at_runtime(case: str, source: str) -> None:
    lox = check(source)
    assert lox.reporter.had_error is True, case
    assert any(item.code is Code.INVALID_OPERANDS for item in lox.reporter.batch().diagnostics), (
        case,
        [item.message for item in lox.reporter.batch().diagnostics],
    )


PRECISION_CASES: list[str] = [
    # Os dois braços atribuem String: o join mantém o refino.
    "var x: String? = nil\nval k = 1\n"
    'val r = match k {\n  0 => (x = "a")\n  _ => (x = "b")\n}\nprint(len(x))\n',
    # Sem `break`, a saída do `while` continua refinando pela condição falsa.
    'var x: String? = "a"\nwhile (x == nil) { x = "b" }\nprint(len(x))\n',
    # `break` do laço interno não desliga o refino do laço externo.
    'var x: String? = "a"\nwhile (x == nil) {\n  while (true) { break }\n  x = "b"\n}\nprint(len(x))\n',
    # Código depois do `break` é inalcançável e não contamina o estado de saída.
    'var s: String? = nil\ns = "a"\nwhile (s != nil) {\n  break\n  s = nil\n}\nprint(len(s))\n',
]


@pytest.mark.parametrize("source", PRECISION_CASES)
def test_soundness_fix_keeps_the_common_refinement(source: str) -> None:
    lox = check(source)
    assert lox.reporter.had_error is False, [
        (item.code.name, item.message) for item in lox.reporter.batch().diagnostics
    ]
