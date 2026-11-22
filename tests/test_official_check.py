# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cobertura de `--check` para os casos positivos da suíte oficial.

Os arquivos oficiais ficam intactos; `official_annotations.annotate` aplica a
camada dinâmica (`Any`) sobre a fonte adaptada. Casos negativos (erro esperado)
e os `xfail` de campos dinâmicos não entram.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.inprocess import run_cli
from tests.official_annotations import annotate_case
from tests.test_official_suite import (
    CASES,
    DYNAMIC_FIELD_TESTS,
    NONTEST_RE,
    adapt_source,
    parse_expectations,
)

# Sintaxe antiga de superclasse (`< (Foo)`) testada de propósito: não é
# adaptável para a nossa gramática.
_CHECK_XFAIL = set(DYNAMIC_FIELD_TESTS) | {"inheritance/parenthesized_superclass.lx"}


def _positive_cases() -> list[pytest.ParameterSet]:
    cases: list[pytest.ParameterSet] = []

    for path in sorted(CASES.rglob("*.lx")):
        source = path.read_text(encoding="utf-8")
        if NONTEST_RE.search(source):
            continue

        relative = str(path.relative_to(CASES))
        expectations = parse_expectations(source)
        if expectations.compile_errors or expectations.runtime_error:
            continue
        if relative in _CHECK_XFAIL:
            continue

        cases.append(pytest.param(path, relative, id=relative))

    return cases


CHECK_CASES = _positive_cases()


def test_todos_os_positivos_estao_cobertos() -> None:
    assert len(CHECK_CASES) == 59


@pytest.mark.parametrize(("path", "relative"), CHECK_CASES)
def test_oficial_positivo_passa_no_check(path: Path, relative: str, tmp_path: Path) -> None:
    adapted = adapt_source(path.read_text(encoding="utf-8"))
    annotated = annotate_case(relative, adapted)
    script = tmp_path / "caso.lx"
    script.write_text(annotated, encoding="utf-8")

    result = run_cli("--check", str(script))

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
