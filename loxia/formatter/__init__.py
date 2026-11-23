# SPDX-License-Identifier: MIT OR Apache-2.0
"""Formatter da Loxia: entrada pública e motor de layout.

O motor v2 (`doc.py`/`comments.py`/`printer.py`/`engine.py`) já existe, mas ainda não é o
default: enquanto o switch não acontece, `format_source` é o v1 congelado em `legacy.py`.
"""

from __future__ import annotations

from loxia.formatter.legacy import Formatted, format_source

__all__ = ["Formatted", "format_source"]
