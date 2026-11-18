# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fuzzing determinístico do scanner/parser com `hypothesis` (TODO §7/§14.0).

As propriedades não olham o stdout do programa: elas garantem que entrada arbitrária ou
uma sopa de tokens **nunca** derruba o front-end (só produz diagnóstico/AST), que as
posições ficam dentro da fonte e que duas execuções produzem os mesmos bytes. O
`derandomize=True` fixa os exemplos no CI; para uma rodada maior, use `-p no:cacheprovider`
ou um `--hypothesis-seed` explícito.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.tokens import Token

FUZZ = settings(max_examples=200, deadline=None, derandomize=True, print_blob=True)

_TOKENS = (
    "1",
    "1.5",
    '"x"',
    '"${x}"',
    "true",
    "false",
    "nil",
    "x",
    "print",
    "if",
    "else",
    "elif",
    "while",
    "for",
    "in",
    "fn",
    "val",
    "var",
    "class",
    "this",
    "super",
    "return",
    "import",
    "from",
    "as",
    "match",
    "enum",
    "interface",
    "type",
    "try",
    "except",
    "finally",
    "raise",
    "not",
    "and",
    "or",
    "is",
    "+",
    "-",
    "*",
    "/",
    "//",
    "%",
    "**",
    "==",
    "!=",
    "<",
    ">",
    "<=",
    ">=",
    "..",
    "?",
    "??",
    "?.",
    "=>",
    "=",
    "(",
    ")",
    "{",
    "}",
    "[",
    "]",
    ",",
    ".",
    ":",
    ";",
    "\n",
    "_",
)


def _front_end(source: str) -> tuple[list[Token], list[Stmt], ErrorReporter]:
    reporter = ErrorReporter()
    tokens = Scanner(source, reporter).scan_tokens()
    statements = Parser(tokens, reporter=reporter).parse()
    assert statements is not None
    return tokens, statements, reporter


def _diagnostics(reporter: ErrorReporter) -> tuple[object, ...]:
    return tuple(
        (
            diagnostic.code,
            diagnostic.message,
            diagnostic.span.start.offset if diagnostic.span is not None else -1,
        )
        for diagnostic in reporter.batch().diagnostics
    )


@FUZZ
@given(st.text(max_size=300))
def test_scanner_e_parser_nunca_lancam_com_texto_arbitrario(source: str) -> None:
    _tokens, statements, _reporter = _front_end(source)

    assert isinstance(statements, list)


@FUZZ
@given(st.lists(st.sampled_from(_TOKENS), min_size=1, max_size=60))
def test_scanner_e_parser_nunca_lancam_com_sopa_de_tokens(parts: list[str]) -> None:
    source = " ".join(parts)

    _tokens, statements, _reporter = _front_end(source)

    assert isinstance(statements, list)


@FUZZ
@given(st.text(max_size=300))
def test_front_end_e_deterministico(source: str) -> None:
    first_tokens, first_statements, first = _front_end(source)
    second_tokens, second_statements, second = _front_end(source)

    assert [
        (token.type, token.lexeme, token.literal, token.line, token.column, token.offset)
        for token in first_tokens
    ] == [
        (token.type, token.lexeme, token.literal, token.line, token.column, token.offset)
        for token in second_tokens
    ]
    assert AstPrinter().print_program(first_statements) == AstPrinter().print_program(
        second_statements
    )
    assert _diagnostics(first) == _diagnostics(second)
    assert first.had_error == second.had_error


@FUZZ
@given(st.text(max_size=300))
def test_posicoes_dos_tokens_ficam_dentro_da_fonte(source: str) -> None:
    tokens, _statements, _reporter = _front_end(source)
    limit = len(source.encode("utf-8"))

    for token in tokens:
        assert token.line >= 1
        assert token.column >= 1
        assert 0 <= token.offset <= limit
        assert token.offset + len(token.lexeme.encode("utf-8")) <= limit


@FUZZ
@given(st.lists(st.sampled_from(_TOKENS), min_size=1, max_size=40))
def test_parse_repl_nunca_lanca(parts: list[str]) -> None:
    source = " ".join(parts)
    reporter = ErrorReporter()
    tokens = Scanner(source, reporter).scan_tokens()

    statements = Parser(tokens, reporter=reporter).parse_repl()

    assert statements is None or isinstance(statements, list)
