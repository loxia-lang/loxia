# SPDX-License-Identifier: MIT OR Apache-2.0
"""Engine do formatter: scanner → parser → printer → render (ADR-0136)."""

from __future__ import annotations

from dataclasses import dataclass

from loxia.formatter.printer import Printer
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner

DEFAULT_MAX_WIDTH = 100


@dataclass(frozen=True)
class Formatted:
    text: str
    changed: bool


def format_source(
    source: str,
    *,
    reporter: ErrorReporter | None = None,
    max_width: int = DEFAULT_MAX_WIDTH,
) -> Formatted | None:
    """Formata `source`; `None` em erro léxico/sintático."""
    reporter = reporter or ErrorReporter()
    scanner = Scanner(source, reporter)
    tokens = scanner.scan_tokens()
    if reporter.had_error:
        return None

    statements = Parser(tokens, reporter=reporter).parse()
    if reporter.had_error or statements is None:
        return None

    printer = Printer(source=source, trivia=scanner.trivia, width=max_width)
    value = printer.format(statements)
    return Formatted(text=value, changed=value != source)
