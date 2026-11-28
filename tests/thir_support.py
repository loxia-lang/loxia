# SPDX-License-Identifier: MIT OR Apache-2.0
"""Helpers compartilhados dos testes do THIR (produtor, serialização e snapshot)."""

from __future__ import annotations

from pathlib import Path

from loxia.engine import Loxia
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.execution.interpreter import Interpreter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Stmt
from loxia_core.semantics.checker import Checker
from loxia_core.semantics.resolver import Resolver
from loxia_core.semantics.thir_build import build_thir
from loxia_core.thir import TModule

ROOT = Path(__file__).resolve().parents[1]


def analyze_source(source: str, *, file: str = "<stdin>") -> tuple[list[Stmt], Checker]:
    """Parse + resolve + check de um fonte isolado, sem loader."""
    reporter = ErrorReporter()
    statements = Parser(Scanner(source, reporter).scan_tokens(), reporter=reporter).parse()
    assert statements is not None, "parse falhou"
    assert not reporter.had_error, "erro de sintaxe no caso de teste"
    Resolver(Interpreter(reporter), reporter).resolve(statements)
    checker = Checker(reporter, entry_file=file)
    checker.check(statements)
    assert not reporter.had_fatal_error, "erro fatal no caso de teste"
    return statements, checker


def module_for(statements: list[Stmt], checker: Checker, *, source_path: str) -> TModule:
    return build_thir(
        statements,
        storage_types=checker.storage_types,
        flow_types=checker.types,
        generic_instances=checker.generic_fn_instances,
        generic_classes=checker.concrete_class_types(),
        generic_class_sites=checker.generic_class_sites,
        type_aliases=checker.type_aliases(),
        function_types=checker.function_types,
        entry=checker.entry,
        globals_scope=checker.global_scope,
        source_path=source_path,
    )


def module_for_source(source: str, *, source_path: str = "case.lx") -> TModule:
    statements, checker = analyze_source(source)
    return module_for(statements, checker, source_path=source_path)


def analyze_case(case: str) -> tuple[list[Stmt], Checker]:
    """Statements + checker de um caso do corpus, com o loader (imports/mangling)."""
    path = ROOT / case
    engine = Loxia()
    # Caminho de exibição relativo, como no CLI: span.file não pode ser absoluto (I3).
    engine.use_file(case, module_root=ROOT)
    statements = engine._parse(path.read_text(encoding="utf-8"))
    assert statements is not None
    resolver = Resolver(engine.interpreter, engine.reporter)
    resolver.resolve(statements)
    checker = Checker(
        engine.reporter,
        captured_mutables=resolver.captured_mutables,
        captured_globals=resolver.captured_global_names,
        entry_file=str(path),
    )
    checker.check(statements)
    assert not engine.reporter.had_error, f"{case}: corpus deveria passar no check"
    return statements, checker


def module_for_case(case: str) -> TModule:
    """THIR de um caso do corpus, com o loader do caminho real."""
    statements, checker = analyze_case(case)
    return module_for(statements, checker, source_path=case)
