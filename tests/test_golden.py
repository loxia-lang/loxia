# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from tests.runner import check_case, discover_cases, missing_requirements

CASES = discover_cases()


@pytest.mark.parametrize(
    "case", CASES, ids=lambda p: str(p.relative_to(Path(__file__).parent / "cases"))
)
def test_golden_case(case: Path) -> None:
    missing = missing_requirements(case)
    if missing:
        pytest.skip(f"requer {', '.join(sorted(missing))}")
    problems = check_case(case)
    assert not problems, "\n".join(problems)


def test_golden_suite_nao_esta_vazia() -> None:
    assert len(CASES) >= 15, "a suíte golden deve cobrir o mínimo da linguagem"


def test_golden_regex_cases_run_isolated(tmp_path: Path) -> None:
    from loxia_core.execution import regex_runtime
    from tests.inprocess import run_cli

    fresh = tmp_path / "fresh.lx"
    fresh.write_text(
        "# requires: rust\nprint(regex_engine.groupNames(1))\n"
        "# expect runtime error: regex handle is closed or unknown.\n",
        encoding="utf-8",
    )
    if missing_requirements(fresh):
        pytest.skip("requer rust")

    leaker = tmp_path / "leaker.lx"
    leaker.write_text('val h = regex_engine.compile("a", 0, 0)\nprint(h)\n', encoding="utf-8")
    leaked = run_cli(str(leaker))
    assert leaked.returncode == 0
    try:
        # Sem o isolamento por processo, o handle 1 do leaker vaza e o caso
        # "fresco" imprimiria os grupos em vez do erro de handle desconhecido.
        problems = check_case(fresh)
        assert not problems, "\n".join(problems)
    finally:
        regex_runtime.free_pattern(1)
