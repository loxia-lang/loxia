# SPDX-License-Identifier: MIT OR Apache-2.0
"""Modelo de diagnóstico: dados imutáveis, sem I/O.

O `ErrorReporter` acumula `Diagnostic`; os renderizadores (texto, JSON) moram em
`render.py`. Essa separação é a decisão do ADR-0075 (e o que o ADR-0003 já antecipava).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loxia_core.diagnostics.codes import Code


class Phase(StrEnum):
    """Fase que produziu o diagnóstico."""

    LEXER = "lexer"
    PARSER = "parser"
    RESOLVER = "resolver"
    CHECKER = "checker"
    BACKEND = "backend"
    RUNTIME = "runtime"
    CLI = "cli"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Applicability(StrEnum):
    """Se um fix pode ser aplicado automaticamente (ADR-0093)."""

    SAFE = "safe"
    UNSAFE = "unsafe"


@dataclass(frozen=True)
class Position:
    """Posição 1-based em code points; `offset` é 0-based em bytes UTF-8.

    `column`/`offset` podem ser `None` quando a fase não conhece a posição exata
    (erro do backend, por exemplo).
    """

    line: int
    column: int | None = None
    offset: int | None = None


@dataclass(frozen=True)
class Span:
    """Intervalo half-open: `end` é o primeiro caractere **depois** do trecho."""

    file: str
    start: Position
    end: Position


@dataclass(frozen=True)
class Label:
    span: Span
    message: str | None = None


@dataclass(frozen=True)
class Frame:
    """Uma ativação Lox no stack trace.

    `name` é o nome exibível do chamado (`f`, `init`, `<lambda>`, `C` no construtor);
    `file`/`line`/`column` são o **call site** — onde o chamado foi chamado. A posição
    do erro em si já está no `span` do diagnóstico.
    """

    name: str
    file: str
    line: int
    column: int


@dataclass(frozen=True)
class Trace:
    """Frames já em ordem de exibição (mais interno primeiro).

    Com mais de `head + tail` frames, `omitted` conta o miolo e `head` marca quantos
    frames vêm antes da linha de elisão. A elisão é determinística (sem endereço/tempo).
    """

    frames: tuple[Frame, ...]
    omitted: int = 0
    head: int = 0


@dataclass(frozen=True)
class Edit:
    """Substituição half-open de um trecho por outro texto."""

    span: Span
    new_text: str


@dataclass(frozen=True)
class Fix:
    """Uma correção candidata; `safe` pode ser aplicada sem confirmação."""

    applicability: Applicability
    message: str
    edits: tuple[Edit, ...]


@dataclass(frozen=True)
class Diagnostic:
    code: Code
    phase: Phase
    severity: Severity
    message: str
    span: Span | None = None
    labels: tuple[Label, ...] = ()
    notes: tuple[str, ...] = ()
    help: str | None = None
    trace: Trace | None = None
    fixes: tuple[Fix, ...] = ()


@dataclass(frozen=True)
class DiagnosticBatch:
    """Diagnósticos prontos para renderizar, já ordenados e deduplicados."""

    diagnostics: tuple[Diagnostic, ...]
    suppressed: int = 0

    @property
    def errors(self) -> int:
        return sum(1 for item in self.diagnostics if item.severity is Severity.ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for item in self.diagnostics if item.severity is Severity.WARNING)

    def __bool__(self) -> bool:
        return bool(self.diagnostics)
