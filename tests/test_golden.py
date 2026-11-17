# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from tests.runner import check_case, discover_cases

CASES = discover_cases()


@pytest.mark.parametrize(
    "case", CASES, ids=lambda p: str(p.relative_to(Path(__file__).parent / "cases"))
)
def test_golden_case(case: Path) -> None:
    problems = check_case(case)
    assert not problems, "\n".join(problems)


def test_golden_suite_nao_esta_vazia() -> None:
    assert len(CASES) >= 15, "a suíte golden deve cobrir o mínimo da linguagem"
