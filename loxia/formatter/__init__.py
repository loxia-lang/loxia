# SPDX-License-Identifier: MIT OR Apache-2.0
"""Formatter da Loxia: entrada pública.

`format_source` é o motor v2 (Doc IR + printer, ADR-0136). O v1 (linha a linha,
ADR-0092) ficou congelado no histórico e não é mais alcançável.
"""

from __future__ import annotations

from loxia.formatter.engine import DEFAULT_MAX_WIDTH, Formatted, format_source

__all__ = ["DEFAULT_MAX_WIDTH", "Formatted", "format_source"]
