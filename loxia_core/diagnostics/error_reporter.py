# SPDX-License-Identifier: MIT OR Apache-2.0
"""Coleta de diagnósticos de **uma** execução (ADR-0003, ADR-0075).

O reporter não imprime: ele acumula `Diagnostic`s e o `Lox` decide quando e como
renderizar. Isso torna o diagnóstico testável sem capturar stderr, permite ordenar e
deduplicar antes de sair e deixa o mesmo modelo alimentar texto e JSON.

Não há estado global: cada `Lox.run` cria a sua instância e a injeta no scanner, no parser,
no resolver, no checker e no interpretador.
"""

from __future__ import annotations

from dataclasses import dataclass

from loxia_core.diagnostics.codes import CODE_PHASE, Code
from loxia_core.diagnostics.diagnostic import (
    Diagnostic,
    DiagnosticBatch,
    Fix,
    Label,
    Phase,
    Position,
    Severity,
    Span,
)
from loxia_core.diagnostics.errors import LoxRuntimeError
from loxia_core.frontend.tokens import Token


@dataclass(frozen=True)
class ReporterState:
    """Snapshot para o parser especulativo do REPL (`mark`/`restore`)."""

    diagnostics: tuple[Diagnostic, ...]
    deferred: tuple[Diagnostic, ...]
    had_error: bool
    had_fatal_error: bool
    had_runtime_error: bool


def _end_position(start: Position, lexeme: str) -> Position:
    """Fim half-open de um token a partir do lexema (pode ter várias linhas)."""
    column = start.column if start.column is not None else 1
    offset = start.offset if start.offset is not None else 0
    byte_length = len(lexeme.encode("utf-8"))

    if "\n" not in lexeme:
        return Position(start.line, column + len(lexeme), offset + byte_length)

    last_line = lexeme.rsplit("\n", 1)[-1]
    return Position(
        start.line + lexeme.count("\n"),
        len(last_line) + 1,
        offset + byte_length,
    )


class ErrorReporter:
    def __init__(self, *, max_errors: int = 20, werror: bool = False) -> None:
        self.max_errors = max_errors
        self.werror = werror
        self.file: str = "<stdin>"
        self.had_error: bool = False
        self.had_fatal_error: bool = False
        self.had_runtime_error: bool = False
        # No build, erro "rebaixável" vira panic site e não deve ser reportado agora.
        self.defer_lowerable: bool = False
        self._diagnostics: list[Diagnostic] = []
        self._deferred: list[Diagnostic] = []

    # -- emissão ---------------------------------------------------------

    def error(
        self,
        target: Token | int,
        message: str,
        *,
        code: Code,
        lowerable: bool = False,
        notes: tuple[str, ...] = (),
        help: str | None = None,
        label_tokens: tuple[tuple[Token, str], ...] = (),
        fixes: tuple[Fix, ...] = (),
    ) -> None:
        """Registra um erro de compilação.

        `lowerable=True` marca o erro que o interpretador só levantaria em runtime (ex.:
        operandos de tipo errado). No build ele vira `lox_panic` e não bloqueia o código
        gerado (ADR-0031, decisão 9).

        `label_tokens` são spans secundários (ex.: "first declared here"); o reporter
        resolve cada token para o arquivo/coluna reais do módulo, como no span principal.
        """
        span = (
            self._span_of_token(target) if isinstance(target, Token) else self._span_of_line(target)
        )
        labels = tuple(Label(self._span_of_token(token), text) for token, text in label_tokens)
        self._record(
            code=code,
            phase=CODE_PHASE[code],
            message=message,
            span=span,
            lowerable=lowerable,
            notes=notes,
            help=help,
            labels=labels,
            fixes=fixes,
        )

    def error_at(
        self,
        start: Position,
        end: Position,
        message: str,
        *,
        code: Code,
        notes: tuple[str, ...] = (),
        help: str | None = None,
    ) -> None:
        """Erro de lexing: o scanner conhece a posição, mas não produz um token."""
        self._record(
            code=code,
            phase=Phase.LEXER,
            message=message,
            span=Span(self.file, start, end),
            lowerable=False,
            notes=notes,
            help=help,
        )

    def warning(
        self,
        target: Token | int,
        message: str,
        *,
        code: Code,
        notes: tuple[str, ...] = (),
        help: str | None = None,
        label_tokens: tuple[tuple[Token, str], ...] = (),
        fixes: tuple[Fix, ...] = (),
    ) -> None:
        """Registra um warning (ou erro, com `-Werror`); não falha por padrão."""
        span = (
            self._span_of_token(target) if isinstance(target, Token) else self._span_of_line(target)
        )
        labels = tuple(Label(self._span_of_token(token), text) for token, text in label_tokens)
        severity = Severity.ERROR if self.werror else Severity.WARNING
        if self.werror:
            self.had_error = True
            self.had_fatal_error = True
        self._diagnostics.append(
            Diagnostic(
                code=code,
                phase=CODE_PHASE[code],
                severity=severity,
                message=message,
                span=span,
                labels=labels,
                notes=notes,
                help=help,
                fixes=fixes,
            )
        )

    def runtime_error(self, error: LoxRuntimeError) -> None:
        """Erro de runtime; o trace é capturado pelo interpretador no ponto mais interno."""
        self.had_runtime_error = True
        self._diagnostics.append(
            Diagnostic(
                code=error.code,
                phase=Phase.RUNTIME,
                severity=Severity.ERROR,
                message=error.message,
                span=self._span_of_token(error.token),
                trace=error.trace,
            )
        )

    def backend_error(
        self,
        line: int | None,
        message: str,
        *,
        code: Code = Code.BACKEND_INTERNAL,
    ) -> None:
        """Erro de compilação do backend nativo (exit 65)."""
        self.had_error = True
        self.had_fatal_error = True
        span = None
        if line is not None:
            span = Span(self.file, Position(line), Position(line))
        self._diagnostics.append(
            Diagnostic(
                code=code,
                phase=Phase.BACKEND,
                severity=Severity.ERROR,
                message=message,
                span=span,
            )
        )

    def cli_error(self, message: str, *, code: Code = Code.CLI_TIMEOUT) -> None:
        """Erro do comando (fase CLI), como timeout; não conta como erro de compilação."""
        self._diagnostics.append(
            Diagnostic(
                code=code,
                phase=Phase.CLI,
                severity=Severity.ERROR,
                message=message,
            )
        )

    # -- consulta --------------------------------------------------------

    def batch(self) -> DiagnosticBatch:
        """Diagnósticos ordenados, sem duplicatas e limitados por `max_errors`."""
        unique: list[Diagnostic] = []
        seen: set[tuple[Code, Span | None]] = set()
        for diagnostic in self._diagnostics:
            key = (diagnostic.code, diagnostic.span)
            if key in seen:
                continue
            seen.add(key)
            unique.append(diagnostic)

        unique.sort(key=_sort_key)

        suppressed = 0
        if self.max_errors > 0 and len(unique) > self.max_errors:
            suppressed = len(unique) - self.max_errors
            unique = unique[: self.max_errors]

        return DiagnosticBatch(diagnostics=tuple(unique), suppressed=suppressed)

    @property
    def has_error(self) -> bool:
        """Houve erro de compilação ou de runtime nesta execução?"""
        return self.had_error or self.had_runtime_error

    # -- ciclo de vida ---------------------------------------------------

    def mark(self) -> ReporterState:
        return ReporterState(
            diagnostics=tuple(self._diagnostics),
            deferred=tuple(self._deferred),
            had_error=self.had_error,
            had_fatal_error=self.had_fatal_error,
            had_runtime_error=self.had_runtime_error,
        )

    def restore(self, state: ReporterState) -> None:
        self._diagnostics = list(state.diagnostics)
        self._deferred = list(state.deferred)
        self.had_error = state.had_error
        self.had_fatal_error = state.had_fatal_error
        self.had_runtime_error = state.had_runtime_error

    def reset(self) -> None:
        self.had_error = False
        self.had_fatal_error = False
        self.had_runtime_error = False
        self.defer_lowerable = False
        self._diagnostics.clear()
        self._deferred.clear()

    # -- internos --------------------------------------------------------

    def _record(
        self,
        *,
        code: Code,
        phase: Phase,
        message: str,
        span: Span | None,
        lowerable: bool,
        notes: tuple[str, ...],
        help: str | None,
        labels: tuple[Label, ...] = (),
        fixes: tuple[Fix, ...] = (),
    ) -> None:
        diagnostic = Diagnostic(
            code=code,
            phase=phase,
            severity=Severity.ERROR,
            message=message,
            span=span,
            labels=labels,
            notes=notes,
            help=help,
            fixes=fixes,
        )

        if not lowerable:
            self.had_fatal_error = True
        elif self.defer_lowerable:
            self.had_error = True
            self._deferred.append(diagnostic)
            return

        self.had_error = True
        self._diagnostics.append(diagnostic)

    def _span_of_token(self, token: Token) -> Span:
        """Span do token; usa `token.file` (origem real) e cai no arquivo da execução.

        Tokens sintéticos têm `file` vazio; nesse caso vale o arquivo atual do reporter.
        """
        start = Position(token.line, token.column, token.offset)
        return Span(token.file or self.file, start, _end_position(start, token.lexeme))

    def _span_of_line(self, line: int) -> Span:
        position = Position(line)
        return Span(self.file, position, position)


def _sort_key(diagnostic: Diagnostic) -> tuple[str, int, int, int, str, str]:
    """Ordem determinística: arquivo, offset, linha, coluna, código, mensagem."""
    span = diagnostic.span
    if span is None:
        return ("", -1, 0, 0, diagnostic.code.value, diagnostic.message)

    offset = span.start.offset if span.start.offset is not None else -1
    column = span.start.column if span.start.column is not None else 0
    return (
        span.file,
        offset,
        span.start.line,
        column,
        diagnostic.code.value,
        diagnostic.message,
    )
