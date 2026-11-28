# SPDX-License-Identifier: MIT OR Apache-2.0
"""THIR: modelo, produtor e o contrato de binding/captura (ADR-0149 §2, F2).

Estes testes fixam o que os motores podem assumir do THIR: tipo no nó, binding
resolvido (local/captura/global), célula marcada na declaração, span preservado e ids
determinísticos. O teste de corpus prova que o produtor cobre a linguagem inteira.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.execution.interpreter import Interpreter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.ty import INT, STRING, display
from loxia_core.semantics.checker import Checker
from loxia_core.semantics.resolver import Resolver
from loxia_core.semantics.thir_build import build_thir
from loxia_core.thir import (
    Decl,
    DeclKind,
    Ref,
    Storage,
    TAs,
    TBinary,
    TCall,
    TClassDecl,
    TDestructureStmt,
    TExpr,
    TExprStmt,
    TFnDecl,
    TForIn,
    TFunction,
    TInterfaceDecl,
    TIs,
    TLambda,
    TLogical,
    TMatch,
    TModule,
    TNamePattern,
    TRange,
    TTuplePattern,
    TVar,
    TVariantPattern,
)
from loxia_core.thir.serialize import canonical, dumps, loads
from tests.corpus_manifest import LEVELS
from tests.thir_support import analyze_case, module_for

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "thir" / "manifest.json"


def _snapshot() -> dict[str, str]:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert isinstance(cases, dict)
    return cases


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


def test_unresolved_name_stays_unresolved() -> None:
    """Nome que o checker não resolve não ganha binding inventado (vira panic site)."""
    reporter = ErrorReporter()
    statements = Parser(Scanner("print(nope)", reporter).scan_tokens(), reporter=reporter).parse()
    assert statements is not None
    Resolver(Interpreter(reporter), reporter).resolve(statements)
    checker = Checker(reporter, entry_file="<stdin>")
    checker.check(statements)
    assert reporter.had_error, "o caso de teste precisa de um nome indefinido"

    module = build_thir(
        statements,
        storage_types=checker.storage_types,
        flow_types=checker.types,
        function_types=checker.function_types,
        globals_scope=checker.global_scope,
        source_path="case.lx",
    )
    refs = {ref.name: ref for ref in _refs(module)}
    assert refs["nope"].storage is Storage.UNRESOLVED
    assert refs["nope"].decl is None
    assert refs["print"].storage is Storage.BUILTIN


def test_builtins_are_builtin_not_unresolved() -> None:
    module = _thir(
        """
        print(len("ab"))
        """
    )
    refs = {ref.name: ref for ref in _refs(module)}
    assert refs["print"].storage is Storage.BUILTIN
    assert refs["print"].decl is None
    assert refs["len"].storage is Storage.BUILTIN


def test_forward_reference_resolves_to_the_global_decl() -> None:
    module = _thir(
        """
        fn a() -> Int { return b() }
        fn b() -> Int { return 1 }
        print(a())
        """
    )
    functions = {function.name: function for function in _functions(module)}
    refs = [ref for ref in _refs(functions["a"]) if ref.name == "b"]
    assert len(refs) == 1
    assert refs[0].storage is Storage.GLOBAL
    (b_decl,) = [decl for decl in module.decls if decl.name == "b"]
    assert refs[0].decl == b_decl.id


def test_global_declared_later_is_not_called_builtin() -> None:
    """Programa que o `--check` recusa: o nome tem `Decl`, então não é `BUILTIN`."""
    reporter = ErrorReporter()
    source = "fn f() -> Int { return x }\nval x = 1\nprint(f())"
    statements = Parser(Scanner(source, reporter).scan_tokens(), reporter=reporter).parse()
    assert statements is not None
    Resolver(Interpreter(reporter), reporter).resolve(statements)
    checker = Checker(reporter, entry_file="<stdin>")
    checker.check(statements)

    module = build_thir(
        statements,
        storage_types=checker.storage_types,
        flow_types=checker.types,
        function_types=checker.function_types,
        globals_scope=checker.global_scope,
        source_path="case.lx",
    )
    refs = {ref.name: ref for ref in _refs(module)}
    assert refs["x"].storage is Storage.UNRESOLVED
    assert refs["x"].decl is None


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


def test_interface_signature_and_empty_default_differ_by_abstract() -> None:
    """`fn m()` é assinatura (`abstract`); `fn m() {}` é default de corpo vazio."""
    module = _thir("interface I {\n  fn sig() -> Nil\n  fn def_() -> Nil {}\n}\n")
    declared = next(s for s in module.statements if isinstance(s, TInterfaceDecl))
    by_name = {method.name: method for method in declared.interface.methods}

    assert by_name["sig"].abstract
    assert not by_name["def_"].abstract
    # Os dois têm corpo vazio: o discriminante é `abstract`, não a ausência de nós.
    assert by_name["sig"].body == ()
    assert by_name["def_"].body == ()


def test_operator_spans_survive_on_every_operator() -> None:
    """`op_span` é o site do operador (panic/erro), não o início do nó."""
    module = _thir("val x: Any = 1\nx as Int\nx is Int\n1..3\ntrue and false\ntrue or false\n")
    as_expr, is_expr, range_expr, and_expr, or_expr = _expr_statements(module)
    for expr, token, line, column in (
        (as_expr, "as", 2, 3),
        (is_expr, "is", 3, 3),
        (range_expr, "..", 4, 2),
        (and_expr, "and", 5, 6),
        (or_expr, "or", 6, 6),
    ):
        assert isinstance(expr, TAs | TIs | TRange | TLogical), token
        assert expr.op_span is not None, f"{token}: op_span perdido"
        assert expr.op_span.start.line == line, token
        assert expr.op_span.start.column == column, token
        # A posição do nó continua sendo o início do operando esquerdo.
        assert expr.span is not None
        assert expr.span.start.column == 1, token


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


def test_ids_follow_predeclaration_then_source_order() -> None:
    module = _thir(
        """
        val a = 1
        fn b() -> Int { return 2 }
        print(a + b())
        """
    )
    ids = {
        decl.name: decl.id
        for decl in module.decls
        if decl.kind in (DeclKind.VAR, DeclKind.FUNCTION)
    }
    assert ids["b"] < ids["a"], "fn/class de topo são pré-declarados como no checker"


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


def test_class_superclass_carries_its_span() -> None:
    module = _thir(
        """
        class A {}
        class B(A) {}
        print(B())
        """
    )
    classes = [statement for statement in module.statements if isinstance(statement, TClassDecl)]
    subclass = next(statement.klass for statement in classes if statement.klass.name == "B")
    assert subclass.superclass == "A"
    assert subclass.superclass_span is not None
    assert subclass.superclass_span.start.line == 3
    base = next(statement.klass for statement in classes if statement.klass.name == "A")
    assert base.superclass is None
    assert base.superclass_span is None


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
    statements, checker = analyze_case(case)
    module = module_for(statements, checker, source_path=case)

    # A captura é canônica (nome) e a célula mora na declaração; não há segunda
    # implementação a comparar depois que o backend passou a consumir o THIR.
    unresolved = {ref.name for ref in _refs(module) if ref.storage is Storage.UNRESOLVED}
    assert not unresolved, f"{case}: nomes não resolvidos em programa check-limpo: {unresolved}"

    # O THIR é contrato serializado: round-trip e hash do snapshot (ADR-0154).
    assert loads(dumps(module)) == module, f"{case}: round-trip mudou o THIR"
    digest = hashlib.sha256(canonical(module).encode("utf-8")).hexdigest()
    assert digest == _snapshot()[case], (
        f"{case}: snapshot do THIR divergente; se a mudança é intencional, "
        "rode `make thir-snapshot` e revise o diff"
    )


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
