# SPDX-License-Identifier: MIT OR Apache-2.0
"""Testes do passe de captura do backend (ADR-0046)."""

from __future__ import annotations

from loxia_core.backend.captures import CaptureAnalysis, analyze_captures
from loxia_core.frontend.expr import Lambda
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Block, Function, Stmt, Var


def _parse(source: str) -> list[Stmt]:
    statements = Parser(Scanner(source).scan_tokens()).parse()
    assert statements is not None
    return statements


def _capture_names(analysis: CaptureAnalysis, node: Function | Lambda) -> list[str]:
    return [capture.name for capture in analysis.captures_of(node)]


def test_captured_var_becomes_cell_and_enters_env() -> None:
    statements = _parse(
        """
        fn make() {
          var i = 0;
          fn count() {
            i = i + 1;
          }
        }
        """
    )
    make = statements[0]
    assert isinstance(make, Function)
    declared = make.body[0]
    count = make.body[1]
    assert isinstance(declared, Var)
    assert isinstance(count, Function)

    analysis = analyze_captures(statements)

    assert _capture_names(analysis, count) == ["i"]
    assert analysis.is_captured(declared)


def test_uncaptured_local_is_not_boxed() -> None:
    statements = _parse(
        """
        fn make() {
          var i = 0;
          print(i);
        }
        """
    )
    make = statements[0]
    assert isinstance(make, Function)
    declared = make.body[0]
    assert isinstance(declared, Var)

    analysis = analyze_captures(statements)

    assert not analysis.is_captured(declared)


def test_capture_propagates_through_intermediate_function() -> None:
    statements = _parse(
        """
        fn outer() {
          var x = 1;
          fn middle() {
            fn inner() {
              print(x);
            }
          }
        }
        """
    )
    outer = statements[0]
    assert isinstance(outer, Function)
    declared = outer.body[0]
    middle = outer.body[1]
    assert isinstance(declared, Var)
    assert isinstance(middle, Function)
    inner = middle.body[0]
    assert isinstance(inner, Function)

    analysis = analyze_captures(statements)

    assert _capture_names(analysis, middle) == ["x"]
    assert _capture_names(analysis, inner) == ["x"]
    assert analysis.is_captured(declared)


def test_global_is_not_captured() -> None:
    statements = _parse(
        """
        var a = 1;
        fn show() {
          print(a);
        }
        """
    )
    show = statements[1]
    assert isinstance(show, Function)

    analysis = analyze_captures(statements)

    assert _capture_names(analysis, show) == []


def test_captured_parameter_is_boxed() -> None:
    statements = _parse(
        """
        fn f(x) {
          fn g() {
            print(x);
          }
        }
        """
    )
    function = statements[0]
    assert isinstance(function, Function)
    param = function.params[0]
    nested = function.body[0]
    assert isinstance(nested, Function)

    analysis = analyze_captures(statements)

    assert _capture_names(analysis, nested) == ["x"]
    assert analysis.is_captured(param)


def test_self_recursive_local_function_captures_its_own_binding() -> None:
    statements = _parse(
        """
        {
          fn f() {
            f();
          }
        }
        """
    )
    block = statements[0]
    assert isinstance(block, Block)
    function = block.statements[0]
    assert isinstance(function, Function)

    analysis = analyze_captures(statements)

    assert _capture_names(analysis, function) == ["f"]
    assert analysis.is_captured(function)


def test_lambda_captures_enclosing_local() -> None:
    statements = _parse(
        """
        fn outer() {
          var x = 1;
          val f = fn() => x;
        }
        """
    )
    outer = statements[0]
    assert isinstance(outer, Function)
    declared = outer.body[0]
    binding = outer.body[1]
    assert isinstance(declared, Var)
    assert isinstance(binding, Var)
    lambda_ = binding.initializer
    assert isinstance(lambda_, Lambda)

    analysis = analyze_captures(statements)

    assert _capture_names(analysis, lambda_) == ["x"]
    assert analysis.is_captured(declared)
