# SPDX-License-Identifier: MIT OR Apache-2.0
"""Modo gradual do check (ADR-0142): anotação ausente vira aviso, erro real continua erro."""

from __future__ import annotations

from loxia.engine import Loxia
from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.diagnostic import Severity

UNANNOTATED = "fn f(x) { return x }\nprint(f(1))\n"
TYPE_ERROR = 'fn f(x: Int) -> Int { return x }\nprint(f("a"))\n'


def check(source: str, *, gradual: bool) -> Loxia:
    lox = Loxia(max_errors=0, gradual=gradual)
    lox.use_file("gradual.lx")
    lox.check(source)
    return lox


def test_strict_check_rejects_missing_annotations() -> None:
    lox = check(UNANNOTATED, gradual=False)

    assert lox.reporter.had_error is True
    assert any(item.code is Code.MISSING_ANNOTATION for item in lox.reporter.batch().diagnostics)


def test_gradual_check_warns_and_keeps_checking() -> None:
    lox = check(UNANNOTATED, gradual=True)

    assert lox.reporter.had_error is False
    diagnostics = lox.reporter.batch().diagnostics
    assert diagnostics
    assert all(item.severity is Severity.WARNING for item in diagnostics)
    assert all(item.code is Code.MISSING_ANNOTATION for item in diagnostics)


def test_gradual_check_still_rejects_real_type_errors() -> None:
    lox = check(TYPE_ERROR, gradual=True)

    assert lox.reporter.had_error is True
    assert any(item.code is Code.TYPE_MISMATCH for item in lox.reporter.batch().diagnostics)
