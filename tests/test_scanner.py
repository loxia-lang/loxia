from __future__ import annotations

import pytest

from src.scanner import Scanner
from src.token_type import TokenType
from src.tokens import Token


def scan(source: str) -> list[Token]:
    return Scanner(source).scan_tokens()


def scan_with_reporter(source: str) -> Scanner:
    scanner = Scanner(source)
    scanner.scan_tokens()
    return scanner


def scan_types(source: str) -> list[TokenType]:
    return [token.type for token in scan(source)]


def test_scans_declaration_and_literal_value() -> None:
    tokens = scan("var a = 1;")

    assert [token.type for token in tokens] == [
        TokenType.VAR,
        TokenType.IDENTIFIER,
        TokenType.EQUAL,
        TokenType.NUMBER,
        TokenType.SEMICOLON,
        TokenType.EOF,
    ]
    assert tokens[1].lexeme == "a"
    assert tokens[3].literal == 1
    assert isinstance(tokens[3].literal, int)


def test_scan_number_literals_split_int_and_float() -> None:
    tokens = scan("42 3.14 1e9 1.5e-3 1_000 0xFF 0b1010 0o755")
    literals = [token.literal for token in tokens if token.type is TokenType.NUMBER]

    assert literals == [42, 3.14, 1e9, 1.5e-3, 1000, 255, 10, 493]
    assert [isinstance(value, int) for value in literals] == [
        True,
        False,
        False,
        False,
        True,
        True,
        True,
        True,
    ]


def test_scans_range_token_and_in_keyword() -> None:
    assert scan_types("0..10 in 1.0 a.b") == [
        TokenType.NUMBER,
        TokenType.DOT_DOT,
        TokenType.NUMBER,
        TokenType.IN,
        TokenType.NUMBER,
        TokenType.IDENTIFIER,
        TokenType.DOT,
        TokenType.IDENTIFIER,
        TokenType.EOF,
    ]


def test_scans_type_punctuation() -> None:
    assert scan_types(": ? [ ] -> |") == [
        TokenType.COLON,
        TokenType.QUESTION,
        TokenType.LEFT_BRACKET,
        TokenType.RIGHT_BRACKET,
        TokenType.ARROW,
        TokenType.PIPE,
        TokenType.EOF,
    ]


def test_keywords_fn_elif_and_fun_as_identifier() -> None:
    assert scan_types("fn elif fun") == [
        TokenType.FN,
        TokenType.ELIF,
        TokenType.IDENTIFIER,
        TokenType.EOF,
    ]


def test_integer_literal_overflow_reports_error() -> None:
    scanner = scan_with_reporter("9223372036854775808")

    assert scanner.reporter.had_error


def test_invalid_number_separator_reports_error() -> None:
    scanner = scan_with_reporter("1__0")

    assert scanner.reporter.had_error


def test_tracks_line_numbers() -> None:
    tokens = scan("1;\n2;\n\n3;")
    numbers = [token for token in tokens if token.type is TokenType.NUMBER]

    assert [token.line for token in numbers] == [1, 2, 4]


def test_skips_comments_and_whitespace() -> None:
    assert scan_types("# nada aqui\n  var   a;  \n/* bloco */\n") == [
        TokenType.VAR,
        TokenType.IDENTIFIER,
        TokenType.SEMICOLON,
        TokenType.EOF,
    ]


def test_nested_block_comments() -> None:
    assert scan_types("/* a /* b */ c */ var x;") == [
        TokenType.VAR,
        TokenType.IDENTIFIER,
        TokenType.SEMICOLON,
        TokenType.EOF,
    ]


def test_unterminated_block_comment_reports_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    scanner = scan_with_reporter("/* aberto")

    assert scanner.reporter.had_error
    assert "Unterminated block comment." in capsys.readouterr().err


def test_scans_arithmetic_and_bitwise_tokens() -> None:
    assert scan_types("// ** & ^ ~ << >> >>>") == [
        TokenType.SLASH_SLASH,
        TokenType.STAR_STAR,
        TokenType.AMPERSAND,
        TokenType.CARET,
        TokenType.TILDE,
        TokenType.LESS_LESS,
        TokenType.GREATER_GREATER,
        TokenType.GREATER_GREATER_GREATER,
        TokenType.EOF,
    ]


def test_scans_nil_aware_tokens() -> None:
    assert scan_types("? ?? ?.") == [
        TokenType.QUESTION,
        TokenType.QUESTION_QUESTION,
        TokenType.QUESTION_DOT,
        TokenType.EOF,
    ]


def test_string_escapes() -> None:
    token = scan(r'"a\nb\t\"\\\0"')[0]

    assert token.literal == 'a\nb\t"\\\0'


def test_unicode_escape() -> None:
    assert scan(r'"\u{1F600}"')[0].literal == "😀"


def test_unknown_escape_reports_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    scanner = scan_with_reporter(r'"\q"')

    assert scanner.reporter.had_error
    assert "Unknown escape sequence '\\q'." in capsys.readouterr().err


def test_invalid_unicode_escape_reports_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    scanner = scan_with_reporter(r'"\u{110000}"')

    assert scanner.reporter.had_error
    assert "Invalid Unicode escape." in capsys.readouterr().err


def test_scans_two_character_operators() -> None:
    assert scan_types("!= == <= >= ! = < >") == [
        TokenType.BANG_EQUAL,
        TokenType.EQUAL_EQUAL,
        TokenType.LESS_EQUAL,
        TokenType.GREATER_EQUAL,
        TokenType.BANG,
        TokenType.EQUAL,
        TokenType.LESS,
        TokenType.GREATER,
        TokenType.EOF,
    ]


def test_string_literal_keeps_lexeme_and_value() -> None:
    token = scan('"oi"')[0]

    assert token.type is TokenType.STRING
    assert token.lexeme == '"oi"'
    assert token.literal == "oi"


def test_multiline_string_increments_line() -> None:
    tokens = scan('"a\nb"\nprint 1;')
    number = next(token for token in tokens if token.type is TokenType.NUMBER)

    assert number.line == 3


def test_unterminated_string_reports_error() -> None:
    scanner = scan_with_reporter('"sem fim')

    assert scanner.reporter.had_error


def test_unexpected_character_reports_error() -> None:
    scanner = scan_with_reporter("@")

    assert scanner.reporter.had_error


def test_reports_the_line_of_the_error() -> None:
    scanner = scan_with_reporter("var a;\n@")

    assert scanner.reporter.had_error
