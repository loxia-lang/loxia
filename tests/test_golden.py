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
    import re

    from loxia_core.execution import regex_runtime
    from tests.inprocess import run_cli

    leaker = tmp_path / "leaker.lx"
    leaker.write_text(
        '# requires: rust\nval h = regex_engine.compile("a", 0, 0)\nprint(h)\n',
        encoding="utf-8",
    )
    if missing_requirements(leaker):
        pytest.skip("requer rust")

    leaked = run_cli(str(leaker))
    assert leaked.returncode == 0
    match = re.search(r"\[1, (\d+)\]", leaked.stdout)
    assert match is not None
    handle = int(match.group(1))
    fresh = tmp_path / "fresh.lx"
    fresh.write_text(
        f"# requires: rust\nprint(regex_engine.groupNames({handle}))\n"
        "# expect runtime error: regex handle is closed or unknown.\n",
        encoding="utf-8",
    )
    try:
        # Sem o isolamento por processo, o handle do leaker vaza e este caso
        # imprimiria os grupos em vez do erro de handle desconhecido.
        problems = check_case(fresh)
        assert not problems, "\n".join(problems)
    finally:
        regex_runtime.free_pattern(handle)
