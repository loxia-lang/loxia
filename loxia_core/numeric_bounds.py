# SPDX-License-Identifier: MIT OR Apache-2.0
"""Limites do `Int` (i64) compartilhados pelo scanner e pelo modelo numérico.

Módulo folha de propósito: não importa nada de `loxia_core`, para que o scanner
(`frontend`) valide literais sem depender de `loxia_core.execution` — a direção das
dependências é policiada por `tests/test_package_layers.py` (AGENTS.md §3-§4).
"""

from __future__ import annotations

INT_MIN = -(2**63)
INT_MAX = 2**63 - 1
