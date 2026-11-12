"""Manifesto do corpus diferencial por nível (ADR-0031, decisão 11).

Um caso só entra aqui quando o backend do nível o compila **e** reproduz stdout, stderr
e exit code do interpretador. A promoção é monotônica: caso que passou não sai do
manifesto sem quebrar o build.

Níveis futuros (`l2`, `l3`, ...) entram como chaves novas; `l0` nunca encolhe.
"""

from __future__ import annotations

LEVELS: dict[str, tuple[str, ...]] = {
    "l0": (
        "tests/cases/comments.lox",
        "tests/cases/comparison.lox",
        "tests/cases/int_division.lox",
        "tests/cases/unary.lox",
    ),
    "l1": (
        "tests/cases/arithmetic.lox",
        "tests/cases/numbers.lox",
        "tests/cases/precedence.lox",
    ),
}


def all_cases() -> list[tuple[str, str]]:
    """Pares (nível, caminho) para o teste diferencial do manifesto."""
    return [
        (level, case) for level, cases in LEVELS.items() for case in cases
    ]
