# SPDX-License-Identifier: MIT OR Apache-2.0
"""Re-export de compatibilidade: a implementação mora no core (ADR-0090).

O checker precisa do índice sem depender do pacote `loxia` (CLI); por isso o
`SourceIndex` fica em `loxia_core/frontend/source_index.py`. Este módulo mantém o
caminho antigo funcionando para consumidores externos e testes.
"""

from __future__ import annotations

from loxia_core.frontend.source_index import ExprSpan, NodeSpan, SourceIndex

__all__ = ["ExprSpan", "NodeSpan", "SourceIndex"]
