from __future__ import annotations

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
    assert tokens[3].literal == 1.0
    assert isinstance(tokens[3].literal, float)


def test_tracks_line_numbers() -> None:
    tokens = scan("1;\n2;\n\n3;")
    numbers = [token for token in tokens if token.type is TokenType.NUMBER]

    assert [token.line for token in numbers] == [1, 2, 4]


def test_skips_comments_and_whitespace() -> None:
    assert scan_types("// nada aqui\n  var   a;  \n") == [
        TokenType.VAR,
        TokenType.IDENTIFIER,
        TokenType.SEMICOLON,
        TokenType.EOF,
    ]


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
