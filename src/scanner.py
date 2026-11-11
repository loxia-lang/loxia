from src.error_reporter import ErrorReporter
from src.keywords import KEYWORDS
from src.token_type import TokenType
from src.tokens import Token


class Scanner:
    def __init__(self, source: str, reporter: ErrorReporter | None = None) -> None:
        self._source: str = source
        self._tokens: list[Token] = []
        self._start: int = 0
        self._current: int = 0
        self._line: int = 1
        self.reporter: ErrorReporter = reporter if reporter is not None else ErrorReporter()

    def scan_tokens(self) -> list[Token]:

        while not self._is_at_end():
            self._start = self._current
            self._scan_token()

        self._tokens.append(Token(TokenType.EOF, "", None, self._line))
        return self._tokens

    def _scan_token(self) -> None:
        c = self._advance()

        match c:
            case "(":
                self._add_token(TokenType.LEFT_PAREN)
            case ")":
                self._add_token(TokenType.RIGHT_PAREN)
            case "{":
                self._add_token(TokenType.LEFT_BRACE)
            case "}":
                self._add_token(TokenType.RIGHT_BRACE)
            case ",":
                self._add_token(TokenType.COMMA)
            case ".":
                self._add_token(TokenType.DOT)
            case "-":
                self._add_token(TokenType.MINUS)
            case "+":
                self._add_token(TokenType.PLUS)
            case ";":
                self._add_token(TokenType.SEMICOLON)
            case "*":
                self._add_token(TokenType.STAR)
            case "!":
                self._add_token(
                    TokenType.BANG_EQUAL if self._match("=") else TokenType.BANG
                )
            case "=":
                self._add_token(
                    TokenType.EQUAL_EQUAL if self._match("=") else TokenType.EQUAL
                )
            case "<":
                self._add_token(
                    TokenType.LESS_EQUAL if self._match("=") else TokenType.LESS
                )
            case ">":
                self._add_token(
                    TokenType.GREATER_EQUAL if self._match("=") else TokenType.GREATER
                )

            case "/":
                if self._match("/"):
                    while self._peek() != "\n" and not self._is_at_end():
                        self._advance()
                else:
                    self._add_token(TokenType.SLASH)
            case " " | "\r" | "\t":
                # Ignora espaços em branco
                pass
            case "\n":
                self._line += 1
            case '"':
                self._string()
            case _:
                if Scanner._is_digit(c=c):
                    self._number()
                elif Scanner._is_alpha(c=c):
                    self._identifier()
                else:
                    self.reporter.error(self._line, f"Unexpected character: {c}")

    def _is_at_end(self) -> bool:
        return self._current >= len(self._source)

    def _advance(self) -> str:
        c = self._source[self._current]
        self._current += 1
        return c

    def _add_token(self, type: TokenType, literal: object = None) -> None:
        text = self._source[self._start : self._current]
        self._tokens.append(Token(type, text, literal, self._line))

    def _match(self, expected: str) -> bool:
        if self._is_at_end():
            return False

        if self._source[self._current] != expected:
            return False

        self._current += 1
        return True

    def _peek(self) -> str:
        if self._is_at_end():
            return "\0"
        return self._source[self._current]

    def _string(self) -> None:
        while self._peek() != '"' and not self._is_at_end():
            if self._peek() == "\n":
                self._line += 1
            self._advance()

        if self._is_at_end():
            self.reporter.error(self._line, "Unterminated string.")
            return

        self._advance()

        value = self._source[self._start + 1 : self._current - 1]
        self._add_token(TokenType.STRING, value)

    def _number(self) -> None:
        while Scanner._is_digit(self._peek()):
            self._advance()

        if self._peek() == "." and Scanner._is_digit(self._peek_next()):
            self._advance()

            while Scanner._is_digit(self._peek()):
                self._advance()

        value = float(self._source[self._start : self._current])
        self._add_token(TokenType.NUMBER, value)

    def _peek_next(self) -> str:
        if self._current + 1 >= len(self._source):
            return "\0"
        return self._source[self._current + 1]

    @staticmethod
    def _is_digit(c: str) -> bool:
        return "0" <= c <= "9"

    @staticmethod
    def _is_alpha(c: str) -> bool:
        return "a" <= c <= "z" or "A" <= c <= "Z" or c == "_"

    @staticmethod
    def _is_alpha_numeric(c: str) -> bool:
        return Scanner._is_alpha(c) or Scanner._is_digit(c)

    def _identifier(self) -> None:
        while Scanner._is_alpha_numeric(self._peek()):
            self._advance()
        text = self._source[self._start : self._current]
        token_type = KEYWORDS.get(text, TokenType.IDENTIFIER)
        self._add_token(token_type)
