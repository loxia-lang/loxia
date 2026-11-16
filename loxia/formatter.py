"""Formatter mínimo (ADR-0092), sem alterar semântica.

Fase 1: normaliza indentação de bloco (2 espaços), remove espaços no fim da linha e
`;` opcional no fim; preserva quebras, strings multilinha, comentários de bloco e o
conteúdo de comentários. Não reflow, não renomeia, não reordena e não insere `fn`.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.expr import Call, ListLiteral, MapLiteral, TupleLiteral
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Function, Stmt
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token


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

    statements = Parser(tokens, reporter=reporter).parse()
    if reporter.had_error or statements is None:
        return None

    structural = _structural_edits(source, tokens, statements)
    if structural:
        source = _apply_edits(source, structural)
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


def _walk(value: object, visit: object) -> None:
    if isinstance(value, Token):
        return
    if is_dataclass(value) and not isinstance(value, type):
        visit(value)  # type: ignore[operator]
        for item in fields(value):
            _walk(getattr(value, item.name), visit)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk(item, visit)


def _structural_edits(
    source: str, tokens: list[Token], statements: list[Stmt]
) -> list[tuple[int, str]]:
    """Edições antes da normalização de linhas: `fn` em método e trailing comma."""
    edits: list[tuple[int, str]] = []
    close_of: dict[int, Token] = {}
    stack: list[Token] = []
    for token in tokens:
        if token.type in (
            TokenType.LEFT_PAREN,
            TokenType.LEFT_BRACKET,
            TokenType.LEFT_BRACE,
        ):
            stack.append(token)
        elif token.type in (
            TokenType.RIGHT_PAREN,
            TokenType.RIGHT_BRACKET,
            TokenType.RIGHT_BRACE,
        ) and stack:
            close_of[stack.pop().offset] = token

    by_offset = {token.offset: index for index, token in enumerate(tokens)}

    def previous(close: Token) -> Token | None:
        index = by_offset.get(close.offset)
        if index is None or index == 0:
            return None
        return tokens[index - 1]

    def comma_after(end: Token | None, close: Token | None) -> None:
        if end is None or close is None or end.line == close.line:
            return
        previous_token = previous(close)
        if previous_token is None or previous_token.type is TokenType.COMMA:
            return
        offset = end.offset + len(end.lexeme.encode("utf-8"))
        edits.append((offset, ","))

    def visit(node: object) -> None:
        if isinstance(node, Function):
            if node.fn_token is None:
                edits.append((node.name.offset, "fn "))
            if node.params and node.params_end is not None:
                last = previous(node.params_end)
                comma_after(last, node.params_end)
        elif isinstance(node, Call):
            if node.arguments and node.arg_ends and not node.spread:
                comma_after(node.arg_ends[-1], node.paren)
        elif isinstance(node, (ListLiteral, MapLiteral, TupleLiteral)):
            opener = (
                node.bracket
                if isinstance(node, ListLiteral)
                else node.brace
                if isinstance(node, MapLiteral)
                else node.paren
            )
            close = close_of.get(opener.offset)
            if close is not None and (
                (isinstance(node, ListLiteral) and node.elements)
                or (isinstance(node, MapLiteral) and node.entries)
                or (isinstance(node, TupleLiteral) and node.elements)
            ):
                comma_after(previous(close), close)

    for statement in statements:
        _walk(statement, visit)
    return edits


def _apply_edits(source: str, edits: list[tuple[int, str]]) -> str:
    data = source.encode("utf-8")
    for offset, text in sorted(edits, key=lambda item: item[0], reverse=True):
        chunk = text.encode("utf-8")
        data = data[:offset] + chunk + data[offset:]
    return data.decode("utf-8")
