# SPDX-License-Identifier: MIT OR Apache-2.0
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

# Stack trace (ADR-0089): mostra os `TRACE_HEAD` frames mais internos e os
# `TRACE_TAIL` mais externos; o miolo vira uma linha de elisão. O runtime C recebe os
# mesmos números via `-D` do driver.
TRACE_HEAD = 5
TRACE_TAIL = 5

# Orçamento declarado de pilha para o binário (ADR-0077). A reserva do SO é maior
# para absorver frames gordos e o runtime; o contrato é o par (profundidade, budget).
STACK_BUDGET_BYTES = 64 * 1024 * 1024
NATIVE_STACK_RESERVE_BYTES = 128 * 1024 * 1024

# Cada `try/finally` aninhado acrescenta frames Python por ativação Lox. O
# contrato é 10.000 ativações independentemente da aninhagem; 500k cobre o pior
# caso do corpus (3 try aninhados) com folga.
PYTHON_RECURSION_BUDGET = 500_000

# ADR-0087: hard cap de heap do binário. `--max-heap` pode aumentar/diminuir no build.
DEFAULT_HEAP_BYTES = 512 * 1024 * 1024
MIN_HEAP_BYTES = 32 * 1024 * 1024
MAX_HEAP_BYTES = 8 * 1024 * 1024 * 1024


def ensure_recursion_budget() -> None:
    """Eleva o limite do Python para o orçamento interno (nunca diminui)."""
    if sys.getrecursionlimit() < PYTHON_RECURSION_BUDGET:
        sys.setrecursionlimit(PYTHON_RECURSION_BUDGET)
