# SPDX-License-Identifier: MIT OR Apache-2.0
"""Capturas e células: o contrato que o THIR publica para os motores (ADR-0046).

O passe `backend/captures.py` existia só enquanto o lowering lia o AST. Com o THIR,
a decisão mora em `Decl.cell` e `TFunction.captures` (ordem canônica) e é o próprio
produtor que a toma; estes testes fixam o comportamento no produtor.
"""

from __future__ import annotations

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.execution.interpreter import Interpreter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.semantics.checker import Checker
from loxia_core.semantics.resolver import Resolver
from loxia_core.semantics.thir_build import build_thir
from loxia_core.thir import Decl, DeclKind, TFunction, TModule


def _module(source: str) -> TModule:
    """THIR de um fonte sem anotações: o checker gradual publica os tipos."""
    reporter = ErrorReporter()
    statements = Parser(Scanner(source, reporter).scan_tokens(), reporter=reporter).parse()
    assert statements is not None, "parse falhou"
    assert not reporter.had_error, "erro de sintaxe no caso de teste"
    Resolver(Interpreter(reporter), reporter).resolve(statements)
    checker = Checker(reporter, gradual=True, warn_missing=False)
    checker.check(statements)
    assert not reporter.had_fatal_error, "erro fatal no caso de teste"
    return build_thir(
        statements,
        storage_types=checker.storage_types,
        flow_types=checker.types,
        generic_instances=checker.generic_fn_instances,
        generic_classes=checker.concrete_class_types(),
        generic_class_sites=checker.generic_class_sites,
        type_aliases=checker.type_aliases(),
        function_types=checker.function_types,
        source_path="case.lx",
    )


def _functions(module: TModule) -> list[TFunction]:
    found: list[TFunction] = []

    def walk(value: object) -> None:
        if isinstance(value, TFunction):
            found.append(value)
            for statement in value.body:
                walk(statement)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
            return
        if hasattr(value, "__dataclass_fields__"):
            for name in value.__dataclass_fields__:
                walk(getattr(value, name))

    walk(module.statements)
    return found


def _function(module: TModule, name: str) -> TFunction:
    matches = [function for function in _functions(module) if function.display_name == name]
    assert len(matches) == 1, f"função '{name}' não encontrada uma única vez"
    return matches[0]


def _capture_names(function: TFunction) -> list[str]:
    return [capture.name for capture in function.captures]


def _decl(module: TModule, name: str, kind: DeclKind | None = None) -> Decl:
    matches = [
        decl for decl in module.decls if decl.name == name and (kind is None or decl.kind is kind)
    ]
    assert len(matches) == 1, f"declaração '{name}' não encontrada uma única vez"
    return matches[0]


def test_captured_var_becomes_cell_and_enters_env() -> None:
    module = _module(
        """
        fn make() {
          var i = 0;
          fn count() {
            i = i + 1;
          }
        }
        """
    )

    assert _capture_names(_function(module, "count")) == ["i"]
    assert _decl(module, "i", DeclKind.VAR).cell


def test_uncaptured_local_is_not_boxed() -> None:
    module = _module(
        """
        fn make() {
          var i = 0;
          print(i);
        }
        """
    )

    assert not _decl(module, "i", DeclKind.VAR).cell


def test_capture_propagates_through_intermediate_function() -> None:
    module = _module(
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

    assert _capture_names(_function(module, "middle")) == ["x"]
    assert _capture_names(_function(module, "inner")) == ["x"]
    assert _decl(module, "x", DeclKind.VAR).cell


def test_global_is_not_captured() -> None:
    module = _module(
        """
        var a = 1;
        fn show() {
          print(a);
        }
        """
    )

    assert _capture_names(_function(module, "show")) == []


def test_captured_parameter_is_boxed() -> None:
    module = _module(
        """
        fn f(x) {
          fn g() {
            print(x);
          }
        }
        """
    )

    assert _capture_names(_function(module, "g")) == ["x"]
    assert _decl(module, "x", DeclKind.PARAM).cell


def test_self_recursive_local_function_captures_its_own_binding() -> None:
    module = _module(
        """
        {
          fn f() {
            f();
          }
        }
        """
    )

    assert _capture_names(_function(module, "f")) == ["f"]
    assert _decl(module, "f", DeclKind.FUNCTION).cell


def test_lambda_captures_enclosing_local() -> None:
    module = _module(
        """
        fn outer() {
          var x = 1;
          val f = fn() => x;
        }
        """
    )

    lambda_ = _function(module, "<lambda>")
    assert _capture_names(lambda_) == ["x"]
    assert _decl(module, "x", DeclKind.VAR).cell


def test_captures_are_ordered_by_name_not_by_declaration_order() -> None:
    """A ordem é canônica (nome): `z` declarado antes de `a` sai como `["a", "z"]`."""
    module = _module(
        """
        fn outer() {
          var z = 1;
          var a = 2;
          val f = fn() => z + a;
        }
        """
    )

    lambda_ = _function(module, "<lambda>")
    assert _capture_names(lambda_) == ["a", "z"]
    assert _decl(module, "z", DeclKind.VAR).cell
    assert _decl(module, "a", DeclKind.VAR).cell


def test_shadowed_name_captures_the_visible_declaration() -> None:
    """Com dois `x` no mesmo frame (blocos distintos), a lambda captura o interno."""
    module = _module(
        """
        fn outer() {
          var x = 1;
          {
            var x = 2;
            val f = fn() => x;
          }
        }
        """
    )

    lambda_ = _function(module, "<lambda>")
    assert _capture_names(lambda_) == ["x"]

    # Só o `x` interno (o mais próximo lexicalmente) é célula; o externo fica em slot.
    decls = [decl for decl in module.decls if decl.name == "x" and decl.kind is DeclKind.VAR]
    cells = [decl for decl in decls if decl.cell]
    assert len(decls) == 2
    assert len(cells) == 1
    assert cells[0].span is not None and cells[0].span.start.line == 5
