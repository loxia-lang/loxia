"""Orçamentos de execução: profundidade de chamadas e heap do binário.

Os números são contrato (ADR-0077 e ADR-0087). O runtime C recebe as mesmas
constantes via `-D` do driver; mudar aqui e não lá é erro de build coberto por
teste. O interpretador usa `PYTHON_RECURSION_BUDGET` apenas como orçamento
interno: o limite observável continua sendo `MAX_CALL_DEPTH`.
"""

from __future__ import annotations

import sys

# ADR-0077: chamadas Lox ativas. Profundidade 1..MAX_CALL_DEPTH; a próxima é R1015.
MAX_CALL_DEPTH = 10_000

# Orçamento declarado de pilha para o binário (ADR-0077). A reserva do SO é maior
# para absorver frames gordos e o runtime; o contrato é o par (profundidade, budget).
STACK_BUDGET_BYTES = 64 * 1024 * 1024
NATIVE_STACK_RESERVE_BYTES = 128 * 1024 * 1024

# ~13 frames Python por chamada Lox; 200k dá margem para 10k chamadas + try/finally.
PYTHON_RECURSION_BUDGET = 200_000

# ADR-0087: hard cap de heap do binário. `--max-heap` pode aumentar/diminuir no build.
DEFAULT_HEAP_BYTES = 512 * 1024 * 1024
MIN_HEAP_BYTES = 32 * 1024 * 1024
MAX_HEAP_BYTES = 8 * 1024 * 1024 * 1024


def ensure_recursion_budget() -> None:
    """Eleva o limite do Python para o orçamento interno (nunca diminui)."""
    if sys.getrecursionlimit() < PYTHON_RECURSION_BUDGET:
        sys.setrecursionlimit(PYTHON_RECURSION_BUDGET)
