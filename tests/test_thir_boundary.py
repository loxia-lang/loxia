# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fronteira do lowering: o backend consome o THIR, nunca o AST nem o checker.

Três invariantes da fatia 3 da F2 (ADR-0149/ADR-0154):

1. nenhum módulo do backend importa os nós de `frontend.expr`/`frontend.stmt`;
2. o lowering não mantém tabelas por identidade de nó (`self.types`, `self.flow_types`,
   `self.depths`, `self.generic_instances`, …) — o tipo/binding viajam no nó;
3. na rota de compilação, `build_thir` é o único consumidor das tabelas do checker:
   as leituras aparecem só como argumentos da própria chamada. REPL/LSP continuam
   lendo `checker.types` para tooling — isso não alimenta o lowering.

O teste é estático (AST) para não depender de llvmlite e para pegar uma reintrodução
acidental mesmo em um caminho que o corpus não cobre.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "loxia_core" / "backend"
PRODUCTION = (ROOT / "loxia_core", ROOT / "loxia")

AST_MODULES = frozenset({"loxia_core.frontend.expr", "loxia_core.frontend.stmt"})
# Tabelas por identidade de nó que o checker publica e que morrem na fronteira.
NODE_TABLES = frozenset(
    {
        "types",
        "flow_types",
        "depths",
        "generic_instances",
        "generic_class_sites",
        "generic_classes",
    }
)
# Atributos do `Checker` que só o produtor do THIR pode ler.
CHECKER_TABLES = frozenset(
    {
        "storage_types",
        "types",
        "generic_fn_instances",
        "generic_class_sites",
        "function_types",
        "concrete_class_types",
        "type_aliases",
        "global_scope",
        "entry",
    }
)


def _backend_modules() -> list[Path]:
    return sorted(BACKEND.rglob("*.py"))


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
            # `from loxia_core.frontend import expr` importa o módulo de nós por
            # outro caminho: o `module` é o pacote, e o submódulo vem em `names`.
            if node.module in {"loxia_core.frontend", "loxia_core"}:
                modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def test_backend_does_not_import_ast_nodes() -> None:
    offenders = []
    for path in _backend_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            if module in AST_MODULES:
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")
    assert not offenders, "o backend voltou a importar nós da AST:\n" + "\n".join(offenders)


def test_backend_has_no_node_identity_tables() -> None:
    offenders = []
    for path in _backend_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in NODE_TABLES
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: self.{node.attr}")
    assert not offenders, (
        "o lowering voltou a ler uma tabela por identidade de nó "
        "(use o tipo/Ref do próprio nó):\n" + "\n".join(offenders)
    )


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _is_build_thir_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "build_thir") or (
        isinstance(func, ast.Attribute) and func.attr == "build_thir"
    )


def _checker_reads(tree: ast.AST) -> list[ast.Attribute]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in CHECKER_TABLES
        and isinstance(node.value, ast.Name)
        and node.value.id == "checker"
    ]


def test_build_thir_is_the_only_checker_reader() -> None:
    """As tabelas do checker não vazam para o `loxia_core` nem para a compilação."""
    offenders: list[str] = []
    for path in (ROOT / "loxia_core").rglob("*.py"):
        if path.name == "thir_build.py":
            continue
        for node in _checker_reads(ast.parse(path.read_text(encoding="utf-8"))):
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: checker.{node.attr}")

    engine = ROOT / "loxia" / "engine.py"
    tree = ast.parse(engine.read_text(encoding="utf-8"))
    parents = _parents(tree)
    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "compile_prepared"
        ),
        None,
    )
    assert function is not None, "compile_prepared não encontrado em loxia/engine.py"
    inside = list(ast.walk(function))
    for ast_node in inside:
        if not (
            isinstance(ast_node, ast.Attribute)
            and ast_node.attr in CHECKER_TABLES
            and isinstance(ast_node.value, ast.Name)
            and ast_node.value.id == "checker"
        ):
            continue
        cursor = cast("ast.AST", ast_node)
        allowed = False
        while cursor in parents:
            cursor = parents[cursor]
            if _is_build_thir_call(cursor):
                allowed = True
                break
        if not allowed:
            offenders.append(f"loxia/engine.py:{ast_node.lineno}: checker.{ast_node.attr}")

    assert not offenders, (
        "tabela do checker lida fora de build_thir na rota de compilação; o THIR "
        "é o único contrato com os motores:\n" + "\n".join(offenders)
    )
