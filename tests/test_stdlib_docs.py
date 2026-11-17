# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loxia.builtins_docs import BY_NAME
from loxia_core.bundle import bundle_dir
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.execution.prelude import BUILTIN_NAMES
from loxia_core.execution.primitives import PRIMITIVE_BY_LOX
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import (
    Class,
    EnumDecl,
    Field,
    Function,
    Interface,
    Stmt,
    TypeAlias,
    Var,
)

ROOT = Path(__file__).resolve().parents[1]
STD = bundle_dir("std")


def _parse(path: Path) -> list[Stmt]:
    reporter = ErrorReporter()
    statements = Parser(
        Scanner(path.read_text(encoding="utf-8"), reporter).scan_tokens(),
        reporter=reporter,
    ).parse()
    assert statements is not None
    return statements


PublicDecl = Function | Class | EnumDecl | Interface | TypeAlias | Var | Field


def _public_declarations(statements: list[Stmt]) -> list[PublicDecl]:
    result: list[PublicDecl] = []
    for statement in statements:
        if isinstance(statement, (Function, EnumDecl, Interface, TypeAlias, Var)):
            if not statement.name.lexeme.startswith("_"):
                result.append(statement)
        elif isinstance(statement, Class):
            if statement.name.lexeme.startswith("_"):
                continue
            result.append(statement)
            result.extend(
                field for field in statement.fields if not field.name.lexeme.startswith("_")
            )
            result.extend(
                method for method in statement.methods if not method.name.lexeme.startswith("_")
            )
    return result


def test_every_public_stdlib_declaration_has_doc() -> None:
    missing: list[str] = []
    for path in sorted(STD.glob("*.lx")):
        for declaration in _public_declarations(_parse(path)):
            if getattr(declaration, "doc", None) is None:
                missing.append(f"{path.name}:{declaration.name.lexeme}")
    assert missing == [], f"sem doc: {missing}"


def test_builtin_docs_cover_every_public_builtin() -> None:
    names = set(BUILTIN_NAMES) | set(PRIMITIVE_BY_LOX)
    names |= {"Int.parse", "Float.parse"}
    names |= {
        f"math.{name}"
        for name in ("abs", "min", "max", "clamp", "floor", "ceil", "round", "trunc", "sqrt")
    }
    missing = sorted(name for name in names if name not in BY_NAME)
    assert missing == [], f"builtins sem doc: {missing}"


def test_generated_stdlib_docs_are_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "docs" / "_hooks" / "stdlib.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_stdlib_docs_hide_private_helpers() -> None:
    strings = (ROOT / "docs" / "stdlib" / "strings.md").read_text(encoding="utf-8")
    json_page = (ROOT / "docs" / "stdlib" / "json.md").read_text(encoding="utf-8")

    assert "_isSpace" not in strings
    assert "_Parser" not in json_page
    assert "`fn trim" in strings
