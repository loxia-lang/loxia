# SPDX-License-Identifier: MIT OR Apache-2.0
"""THIR: modelo, produtor e o contrato de binding/captura (ADR-0149 §2, F2).

Estes testes fixam o que os motores podem assumir do THIR: tipo no nó, binding
resolvido (local/captura/global), célula marcada na declaração, span preservado e ids
determinísticos. O teste de corpus prova que o produtor cobre a linguagem inteira.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia.engine import Loxia
from loxia_core.backend.captures import analyze_captures
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.execution.interpreter import Interpreter
from loxia_core.frontend.expr import Lambda
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.spans import node_span
from loxia_core.frontend.stmt import Function, Stmt
from loxia_core.frontend.ty import INT, STRING, display
from loxia_core.semantics.checker import Checker
from loxia_core.semantics.resolver import Resolver
from loxia_core.semantics.thir_build import build_thir
from loxia_core.thir import (
    Decl,
    DeclKind,
    Ref,
    Storage,
    TBinary,
    TCall,
    TClassDecl,
    TDestructureStmt,
    TExpr,
    TExprStmt,
    TFnDecl,
    TForIn,
    TFunction,
    TLambda,
    TMatch,
    TModule,
    TNamePattern,
    TTuplePattern,
    TVar,
    TVariantPattern,
)
from tests.corpus_manifest import LEVELS

ROOT = Path(__file__).resolve().parents[1]


def _analyze(source: str) -> tuple[list[Stmt], Checker]:
    """Parse + resolve + check de um fonte isolado (sem loader)."""
    reporter = ErrorReporter()
    statements = Parser(Scanner(source, reporter).scan_tokens(), reporter=reporter).parse()
    assert statements is not None, "parse falhou"
    assert not reporter.had_error, "erro de sintaxe no caso de teste"
    Resolver(Interpreter(reporter), reporter).resolve(statements)
    checker = Checker(reporter, entry_file="<stdin>")
    checker.check(statements)
    assert not reporter.had_fatal_error, "erro fatal no caso de teste"
    return statements, checker


def _thir(source: str) -> TModule:
    statements, checker = _analyze(source)
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
        source_path="case.lx",
    )


def _functions(module: TModule) -> list[TFunction]:
    """Todas as `TFunction` do módulo, em pré-ordem (declarações e lambdas)."""
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
        if isinstance(value, (TLambda, TFnDecl)):
            walk(value.fn)
            return
        if isinstance(value, TClassDecl):
            for method in value.klass.methods:
                walk(method)
            return
        if hasattr(value, "__dataclass_fields__"):
            for name in value.__dataclass_fields__:
                walk(getattr(value, name))

    walk(module.statements)
    return found


def _decl(module: TModule, name: str) -> list[Decl]:
    return [decl for decl in module.decls if decl.name == name]


def _expr_statements(module: TModule) -> list[TExpr]:
    found: list[TExpr] = []

    def walk(value: object) -> None:
        if isinstance(value, TExprStmt):
            found.append(value.expression)
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


# --- binding ------------------------------------------------------------------


def test_global_reference_is_global() -> None:
    module = _thir(
        """
        val x = 1
        fn f() -> Int { return x }
        """
    )
    function = _functions(module)[0]
    assert function.name == "f"
    refs = _refs(function)
    assert refs
    assert all(ref.storage is Storage.GLOBAL for ref in refs)


def test_local_reference_is_local() -> None:
    module = _thir(
        """
        fn f() -> Int {
          val x = 1
          return x
        }
        """
    )
    refs = _refs(_functions(module)[0])
    assert refs
    assert all(ref.storage is Storage.LOCAL for ref in refs)
    assert all(decl.cell is False for decl in _decl(module, "x"))


def test_captured_local_is_cell_and_capture() -> None:
    module = _thir(
        """
        fn outer() -> Nil {
          var total = 1
          val soma = fn(x: Int) -> Int { return x + total }
          total = soma(1)
          return nil
        }
        """
    )
    functions = _functions(module)
    outer = functions[0]
    inner = functions[1]
    assert outer.name == "outer"
    assert inner.name is None
    assert [capture.name for capture in inner.captures] == ["total"]
    (total,) = _decl(module, "total")
    assert total.cell is True
    capture_refs = [ref for ref in _refs(inner) if ref.storage is Storage.CAPTURE]
    assert [ref.decl for ref in capture_refs] == [total.id]


def test_shadowing_does_not_become_capture() -> None:
    module = _thir(
        """
        val x = 1
        fn f() -> Int {
          val x = 2
          return x
        }
        """
    )
    function = _functions(module)[0]
    refs = _refs(function)
    assert len(refs) == 1
    assert refs[0].storage is Storage.LOCAL
    same_name = [decl for decl in module.decls if decl.name == "x"]
    assert len(same_name) == 2
    assert all(decl.cell is False for decl in same_name)
    assert refs[0].decl == same_name[1].id


def test_for_in_variable_is_declared_in_its_own_scope() -> None:
    module = _thir(
        """
        var total = 0
        for i in 0..3 {
          total = total + i
        }
        """
    )
    for_stmt = next(statement for statement in module.statements if isinstance(statement, TForIn))
    (loop_var,) = [decl for decl in module.decls if decl.id == for_stmt.decl]
    assert loop_var.name == "i"
    body_refs = _refs(for_stmt.body)
    assert any(ref.decl == loop_var.id and ref.storage is Storage.LOCAL for ref in body_refs)


def test_unresolved_name_is_not_invented() -> None:
    # O checker adia `1 + true` como panic site; o produtor não pode inventar binding.
    statements, checker = _analyze(
        """
        print(1 + true)
        """
    )
    module = build_thir(
        statements,
        storage_types=checker.storage_types,
        flow_types=checker.types,
        source_path="case.lx",
    )
    assert isinstance(module, TModule)


# --- tipos e spans ------------------------------------------------------------


def test_narrowing_flows_on_the_node_not_on_the_decl() -> None:
    module = _thir(
        """
        val x: Int? = 1
        if (x != nil) {
          print(x + 1)
        }
        """
    )
    (decl,) = _decl(module, "x")
    assert decl.ty is not None and decl.ty != INT

    refs = [expr for expr in _all_exprs(module) if isinstance(expr, TVar)]
    assert any(ref.ty == INT for ref in refs), "o uso estreitado precisa carregar Int no nó"
    assert any(ref.storage_ty is not None and ref.storage_ty != INT for ref in refs), (
        "o tipo de armazenamento não pode ter sido estreitado"
    )


def test_span_of_node_points_at_the_source() -> None:
    module = _thir(
        """
        fn f() -> Int {
          return 1 + 2
        }
        """
    )
    binary = next(expr for expr in _all_exprs(module) if isinstance(expr, TBinary))
    assert binary.span is not None
    assert binary.span.start.line == 3
    assert binary.op_span is not None
    assert binary.op_span.start.line == 3


# --- desugaring mínimo (v1) ---------------------------------------------------


def test_grouping_is_erased() -> None:
    module = _thir("print(((1 + 2)))")
    (expression,) = _expr_statements(module)
    call = expression
    assert isinstance(call, TCall)
    assert isinstance(call.arguments[0], TBinary)


def test_nested_destructure_keeps_the_pattern() -> None:
    module = _thir(
        """
        val (a, (b, c)) = (1, (2, 3))
        print(a + b + c)
        """
    )
    destructure = next(
        statement for statement in module.statements if isinstance(statement, TDestructureStmt)
    )
    assert isinstance(destructure.pattern, TTuplePattern)
    assert len(destructure.pattern.elements) == 2
    nested = destructure.pattern.elements[1]
    assert isinstance(nested, TTuplePattern)
    assert len(nested.elements) == 2
    for element in (destructure.pattern.elements[0], *nested.elements):
        assert isinstance(element, TNamePattern)
        (decl,) = [decl for decl in module.decls if decl.id == element.decl]
        assert decl.ty == INT, f"{decl.name} deveria ser Int, veio {decl.ty}"


def test_destructure_annotation_is_distributed_per_element() -> None:
    module = _thir(
        """
        val (c, d): (Int, String) = (3, "x")
        print(c)
        print(d)
        """
    )
    destructure = next(
        statement for statement in module.statements if isinstance(statement, TDestructureStmt)
    )
    assert isinstance(destructure.pattern, TTuplePattern)
    first, second = destructure.pattern.elements
    assert isinstance(first, TNamePattern) and isinstance(second, TNamePattern)
    (c,) = [decl for decl in module.decls if decl.id == first.decl]
    (d,) = [decl for decl in module.decls if decl.id == second.decl]
    assert c.ty == INT
    assert d.ty == STRING


def test_instances_are_ordered_canonically() -> None:
    module = _thir(
        """
        class Box[T] {
          val item: T
          init(item: T) { this.item = item }
        }
        fn identidade[T](x: T) -> T { return x }
        print(identidade(1))
        val caixa = Box(1)
        print(caixa.item)
        """
    )
    keys = [
        (instance.name, tuple(display(argument) for argument in instance.type_args))
        for instance in module.instances
    ]
    assert keys == sorted(keys)
    assert {name for name, _ in keys} >= {"Box", "identidade"}


def test_match_arms_bind_their_own_decls() -> None:
    module = _thir(
        """
        enum Opt {
          Some(Int),
          None
        }
        fn f(o: Opt) -> Int {
          return match o {
            Opt.Some(v) => v,
            Opt.None => 0
          }
        }
        """
    )
    match = next(expr for expr in _all_exprs(module) if isinstance(expr, TMatch))
    pattern = match.arms[0].pattern
    assert isinstance(pattern, TVariantPattern)
    (binding_id,) = pattern.bindings
    (binding,) = [decl for decl in module.decls if decl.id == binding_id]
    assert binding.kind is DeclKind.PATTERN
    assert binding.name == "v"
    body = match.arms[0].body
    assert isinstance(body, TVar)
    assert body.ref.decl == binding.id
    assert body.ref.storage is Storage.LOCAL


# --- genéricos ----------------------------------------------------------------


def test_generic_call_carries_its_instantiation() -> None:
    module = _thir(
        """
        fn identidade[T](x: T) -> T { return x }
        print(identidade(1))
        """
    )
    calls = [expr for expr in _all_exprs(module) if isinstance(expr, TCall)]
    instantiated = [call for call in calls if call.instance is not None]
    assert instantiated
    instance = instantiated[0].instance
    assert instance is not None
    assert instance.name == "identidade"
    assert instance.type_args
    assert any(instance.name == "identidade" for instance in module.instances)


# --- ids e determinismo -------------------------------------------------------


def test_decl_ids_are_unique_and_sequential() -> None:
    module = _thir(
        """
        class P {
          val nome: String
          init(n: String) { this.nome = n }
        }
        val p = P("a")
        val f = fn(x: Int) -> Int { return x }
        print(p.nome)
        """
    )
    ids = [decl.id for decl in module.decls]
    assert ids == list(range(1, len(ids) + 1))


def test_build_is_deterministic() -> None:
    source = """
    class P {
      var nome: String
      init(n: String) { this.nome = n }
      fn ola() -> String { return "oi " + this.nome }
    }
    var total = 0
    for i in 0..3 { total = total + i }
    val f = fn(x: Int) -> Int { return x + total }
    print(P("a").ola() + str(f(1)))
    """
    statements, checker = _analyze(source)
    first = _build(statements, checker)
    second = _build(statements, checker)
    assert first == second


def test_entry_is_recorded() -> None:
    module = _thir(
        """
        fn main() -> Result[Nil, String] {
          return Result.Ok(nil)
        }
        """
    )
    assert module.entry is not None
    (entry,) = [decl for decl in module.decls if decl.id == module.entry]
    assert entry.name == "main"
    assert entry.kind is DeclKind.FUNCTION


# --- corpus -------------------------------------------------------------------


def _build(statements: list[Stmt], checker: Checker, path: str = "case.lx") -> TModule:
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
        source_path=path,
    )


def _corpus_cases() -> list[str]:
    return sorted({case for level in LEVELS.values() for case in level})


@pytest.mark.parametrize("case", _corpus_cases(), ids=lambda case: Path(case).stem)
def test_corpus_produces_thir(case: str) -> None:
    """Todo caso que compila produz THIR; capturas e células concordam com o backend."""
    path = Path(case)
    engine = Loxia()
    engine.use_file(str(path), module_root=ROOT)
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

    module = _build(statements, checker, path=case)
    analysis = analyze_captures(statements)

    thir_captures = {
        (str(function.decl_span), tuple(capture.name for capture in function.captures))
        for function in _functions(module)
    }
    ast_captures = {
        (str(node_span(node)), tuple(capture.name for capture in analysis.captures_of(node)))
        for node in _ast_functions(statements)
    }
    assert thir_captures == ast_captures, f"{case}: capturas divergem do backend"
    assert sum(1 for decl in module.decls if decl.cell) == len(analysis.captured_decls), (
        f"{case}: número de células diverge do backend"
    )
    unresolved = {ref.name for ref in _refs(module) if ref.storage is Storage.UNRESOLVED}
    assert not unresolved, f"{case}: nomes não resolvidos em programa check-limpo: {unresolved}"


def _ast_functions(statements: list[Stmt]) -> list[Function | Lambda]:
    found: list[Function | Lambda] = []
    seen: set[int] = set()

    def walk(value: object) -> None:
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, (Function, Lambda)):
            found.append(value)
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
            return
        if hasattr(value, "__dataclass_fields__"):
            for name in value.__dataclass_fields__:
                walk(getattr(value, name))

    walk(statements)
    return found


def _all_exprs(module: TModule) -> list[TExpr]:
    found: list[TExpr] = []

    def walk(value: object) -> None:
        if isinstance(value, TExpr):
            found.append(value)
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
            return
        if hasattr(value, "__dataclass_fields__"):
            for name in value.__dataclass_fields__:
                walk(getattr(value, name))

    walk(module.statements)
    return found


def _refs(value: object) -> list[Ref]:
    collected: list[Ref] = []

    def walk(node: object) -> None:
        if isinstance(node, Ref):
            collected.append(node)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        if hasattr(node, "__dataclass_fields__"):
            for name in node.__dataclass_fields__:
                walk(getattr(node, name))

    walk(value)
    return collected
