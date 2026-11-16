"""Formatter mínimo (ADR-0092), sem alterar semântica.

Fase 1: normaliza indentação de bloco (2 espaços), remove espaços no fim da linha e
`;` opcional no fim; preserva quebras, strings multilinha, comentários de bloco e o
conteúdo de comentários. Não reflow, não renomeia, não reordena e não insere `fn`.
"""

from __future__ import annotations

from dataclasses import dataclass

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.token_type import TokenType


@dataclass(frozen=True)
class Formatted:
    text: str
    changed: bool


def format_source(
    source: str, *, reporter: ErrorReporter | None = None
) -> Formatted | None:
    """Formata `source`; `None` quando há erro léxico/sintático."""
    reporter = reporter or ErrorReporter()
    scanner = Scanner(source, reporter)
    tokens = scanner.scan_tokens()
    if reporter.had_error:
        return None

    Parser(tokens, reporter=reporter).parse()
    if reporter.had_error:
        return None

    brace_delta: dict[int, int] = {}
    paren_delta: dict[int, int] = {}
    multiline_start: set[int] = set()
    protected: set[int] = set(scanner.block_comment_lines)

    for token in tokens:
        if token.type is TokenType.LEFT_BRACE:
            brace_delta[token.line] = brace_delta.get(token.line, 0) + 1
        elif token.type is TokenType.RIGHT_BRACE:
            brace_delta[token.line] = brace_delta.get(token.line, 0) - 1
        elif token.type in (TokenType.LEFT_PAREN, TokenType.LEFT_BRACKET):
            paren_delta[token.line] = paren_delta.get(token.line, 0) + 1
        elif token.type in (TokenType.RIGHT_PAREN, TokenType.RIGHT_BRACKET):
            paren_delta[token.line] = paren_delta.get(token.line, 0) - 1

        if "\n" in token.lexeme:
            end_line = token.line + token.lexeme.count("\n")
            multiline_start.add(token.line)
            protected.update(range(token.line + 1, end_line + 1))

    protected.update(scanner.block_comment_starts)

    lines = source.splitlines()
    output: list[str] = []
    depth = 0
    parens = 0

    for number, line in enumerate(lines, start=1):
        stripped = line.strip()

        starts_literal = (
            number in multiline_start or number in scanner.block_comment_starts
        )
        if number in protected and not starts_literal:
            output.append(line)
        elif starts_literal:
            # Só a indentação inicial pode mudar; o resto da string/comentário fica
            # literal (inclusive espaços no fim). Dentro de parênteses a continuação
            # preserva a indentação original.
            original_indent = line[: len(line) - len(line.lstrip(" \t"))]
            content = line[len(original_indent) :]
            if parens > 0:
                output.append(line)
            else:
                output.append("  " * max(0, depth) + content)
        elif not stripped:
            output.append("")
        elif parens > 0:
            output.append(line.rstrip())
        else:
            indent = depth - (1 if stripped.startswith("}") else 0)
            content = stripped
            if (
                content.endswith(";")
                and not content.startswith(("#", "///", "/*"))
            ):
                content = content[:-1].rstrip()
            output.append("  " * max(0, indent) + content)

        depth += brace_delta.get(number, 0)
        parens += paren_delta.get(number, 0)

    text = "\n".join(output)
    if text:
        text += "\n"
    return Formatted(text=text, changed=text != source)
