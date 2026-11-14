from collections.abc import Callable

from src.diagnostics.error_reporter import ErrorReporter
from src.execution.numeric import INT_MAX
from src.frontend.keywords import KEYWORDS
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token


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
            case ":":
                self._add_token(TokenType.COLON)
            case "[":
                self._add_token(TokenType.LEFT_BRACKET)
            case "]":
                self._add_token(TokenType.RIGHT_BRACKET)
            case "?":
                if self._match("?"):
                    self._add_token(TokenType.QUESTION_QUESTION)
                elif self._match("."):
                    self._add_token(TokenType.QUESTION_DOT)
                else:
                    self._add_token(TokenType.QUESTION)
            case "|":
                self._add_token(TokenType.PIPE)
            case "&":
                self._add_token(TokenType.AMPERSAND)
            case "^":
                self._add_token(TokenType.CARET)
            case "~":
                self._add_token(TokenType.TILDE)
            case "#":
                while self._peek() != "\n" and not self._is_at_end():
                    self._advance()
            case ".":
                self._add_token(
                    TokenType.DOT_DOT if self._match(".") else TokenType.DOT
                )
            case "-":
                self._add_token(
                    TokenType.ARROW if self._match(">") else TokenType.MINUS
                )
            case "+":
                self._add_token(TokenType.PLUS)
            case ";":
                self._add_token(TokenType.SEMICOLON)
            case "*":
                self._add_token(
                    TokenType.STAR_STAR if self._match("*") else TokenType.STAR
                )
            case "%":
                self._add_token(TokenType.PERCENT)
            case "!":
                if not self._match("="):
                    self.reporter.error(
                        self._line,
                        "Unexpected character: ! (use 'not' for negation).",
                    )
                    return
                self._add_token(TokenType.NOT_EQUAL)
            case "=":
                if self._match(">"):
                    self._add_token(TokenType.FAT_ARROW)
                else:
                    self._add_token(
                        TokenType.EQUAL_EQUAL
                        if self._match("=")
                        else TokenType.EQUAL
                    )
            case "<":
                if self._match("<"):
                    self._add_token(TokenType.LESS_LESS)
                else:
                    self._add_token(
                        TokenType.LESS_EQUAL if self._match("=") else TokenType.LESS
                    )
            case ">":
                if self._match(">"):
                    self._add_token(
                        TokenType.GREATER_GREATER_GREATER
                        if self._match(">")
                        else TokenType.GREATER_GREATER
                    )
                else:
                    self._add_token(
                        TokenType.GREATER_EQUAL if self._match("=") else TokenType.GREATER
                    )

            case "/":
                if self._match("*"):
                    self._block_comment()
                elif self._match("/"):
                    self._add_token(TokenType.SLASH_SLASH)
                else:
                    self._add_token(TokenType.SLASH)
            case " " | "\r" | "\t":
                # Ignora espaços em branco
                pass
            case "\n":
                self._line += 1
            case '"':
                self._string()
            case "r" if self._peek() == '"':
                self._string(raw=True)
            case _:
                if Scanner._is_digit(c=c):
                    self._number()
                elif Scanner._is_alpha(c=c):
                    self._identifier()
                else:
                    self.reporter.error(self._line, f"Unexpected character: {c}")

    def _block_comment(self) -> None:
        depth = 1

        while depth > 0 and not self._is_at_end():
            if self._peek() == "/" and self._peek_next() == "*":
                self._advance()
                self._advance()
                depth += 1
            elif self._peek() == "*" and self._peek_next() == "/":
                self._advance()
                self._advance()
                depth -= 1
            else:
                if self._peek() == "\n":
                    self._line += 1
                self._advance()

        if depth > 0:
            self.reporter.error(self._line, "Unterminated block comment.")

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

    def _string(self, raw: bool = False) -> None:
        string_start = self._start
        if raw:
            # O `r` já foi consumido; a aspa de abertura vem logo depois dele.
            self._advance()

        triple = self._source[self._current : self._current + 2] == '""'
        if triple:
            self._advance()
            self._advance()

        value: list[str] = []
        parts: list[str | list[Token]] = []
        interpolated = False
        closed = False

        while not self._is_at_end():
            if triple and self._source[self._current : self._current + 3] == '"""':
                self._advance()
                self._advance()
                self._advance()
                closed = True
                break

            char = self._peek()

            if not triple and char == '"':
                self._advance()
                closed = True
                break

            if char == "\n":
                if not triple:
                    self.reporter.error(
                        self._line,
                        "Unterminated string; multiline strings use '\"\"\"'.",
                    )
                    # Descarta o resto da linha para não gerar erros em cascata.
                    while not self._is_at_end() and self._peek() != "\n":
                        self._advance()
                    return
                self._line += 1
                value.append(self._advance())
                continue

            if not raw and char == "$" and self._peek_next() == "{":
                self._advance()
                self._advance()
                parts.append("".join(value))
                value.clear()

                expression = self._scan_expression_tokens()
                if expression is None:
                    return

                parts.append(expression)
                interpolated = True
                continue

            if raw or char != "\\":
                value.append(self._advance())
                continue

            self._advance()

            if self._is_at_end():
                break

            escape = self._advance()

            if escape == "\n":
                self._line += 1

            match escape:
                case '"':
                    value.append('"')
                case "\\":
                    value.append("\\")
                case "n":
                    value.append("\n")
                case "t":
                    value.append("\t")
                case "r":
                    value.append("\r")
                case "0":
                    value.append("\0")
                case "$":
                    value.append("$")
                case "u":
                    self._unicode_escape(value)
                case _:
                    self.reporter.error(
                        self._line, f"Unknown escape sequence '\\{escape}'."
                    )

        if not closed:
            self.reporter.error(self._line, "Unterminated string.")
            return

        self._start = string_start
        if interpolated:
            parts.append("".join(value))
            self._add_token(TokenType.INTERPOLATED_STRING, parts)
        else:
            self._add_token(TokenType.STRING, "".join(value))

    def _scan_expression_tokens(self) -> list[Token] | None:
        """Escaneia a expressão de `${...}` em um buffer próprio.

        O `}` de fechamento não entra nos tokens; chaves internas (mapa, bloco) são
        contadas para não confundir o fechamento da interpolação.
        """
        saved = self._tokens
        tokens: list[Token] = []
        self._tokens = tokens
        depth = 0
        closed = False

        try:
            while not self._is_at_end():
                if self._peek() == "}" and depth == 0:
                    self._advance()
                    closed = True
                    break

                self._start = self._current
                before = len(self._tokens)
                self._scan_token()

                for token in self._tokens[before:]:
                    if token.type is TokenType.LEFT_BRACE:
                        depth += 1
                    elif token.type is TokenType.RIGHT_BRACE:
                        depth -= 1
        finally:
            self._tokens = saved

        if not closed:
            self.reporter.error(self._line, "Unterminated interpolation.")
            return None

        tokens.append(Token(TokenType.EOF, "", None, self._line))
        return tokens

    def _unicode_escape(self, value: list[str]) -> None:
        if self._peek() != "{":
            self.reporter.error(self._line, "Expect '{' after '\\u'.")
            return

        self._advance()
        digits: list[str] = []

        while self._peek() != "}" and not self._is_at_end():
            char = self._advance()
            if char not in "0123456789abcdefABCDEF":
                self.reporter.error(self._line, "Invalid Unicode escape.")
                while self._peek() not in ("}", "\0") and not self._is_at_end():
                    if self._peek() == "\n":
                        self._line += 1
                    self._advance()
                if self._peek() == "}":
                    self._advance()
                return
            digits.append(char)

        if not digits or len(digits) > 6:
            self.reporter.error(self._line, "Invalid Unicode escape.")
            if self._peek() == "}":
                self._advance()
            return

        if self._peek() != "}":
            self.reporter.error(self._line, "Invalid Unicode escape.")
            return

        self._advance()
        codepoint = int("".join(digits), 16)

        if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            self.reporter.error(self._line, "Invalid Unicode escape.")
            return

        value.append(chr(codepoint))

    def _number(self) -> None:
        if self._source[self._start] == "0" and self._peek() in "xXbBoO":
            self._based_number()
        else:
            self._decimal_number()

    def _decimal_number(self) -> None:
        self._scan_digits(Scanner._is_digit)
        is_float = False

        if self._peek() == "." and Scanner._is_digit(self._peek_next()):
            is_float = True
            self._advance()
            self._scan_digits(Scanner._is_digit)

        exponent_digits = 2 if self._peek_at(1) in ("+", "-") else 1
        if self._peek() in ("e", "E") and Scanner._is_digit(
            self._peek_at(exponent_digits)
        ):
            is_float = True
            self._advance()
            if self._peek() in ("+", "-"):
                self._advance()
            self._scan_digits(Scanner._is_digit)

        raw = self._source[self._start : self._current]
        if not Scanner._valid_separators(raw, Scanner._is_digit):
            self.reporter.error(self._line, "Invalid number literal.")
            return

        text = raw.replace("_", "")
        if is_float:
            self._add_token(TokenType.NUMBER, float(text))
            return

        value = int(text)
        if value > INT_MAX:
            self.reporter.error(self._line, "Too large integer literal.")
            return

        self._add_token(TokenType.NUMBER, value)

    def _based_number(self) -> None:
        prefix = self._advance().lower()
        is_digit: Callable[[str], bool]
        if prefix == "x":
            base, is_digit = 16, Scanner._is_hex_digit
        elif prefix == "b":
            base, is_digit = 2, Scanner._is_binary_digit
        else:
            base, is_digit = 8, Scanner._is_octal_digit

        digits_start = self._current
        self._scan_digits(is_digit)
        raw = self._source[digits_start : self._current]

        if not raw or not Scanner._valid_separators(raw, is_digit):
            self.reporter.error(self._line, "Invalid number literal.")
            return

        value = int(raw.replace("_", ""), base)
        if value > INT_MAX:
            self.reporter.error(self._line, "Too large integer literal.")
            return

        self._add_token(TokenType.NUMBER, value)

    def _scan_digits(self, is_digit: Callable[[str], bool]) -> None:
        while is_digit(self._peek()) or self._peek() == "_":
            self._advance()

    @staticmethod
    def _valid_separators(raw: str, is_digit: Callable[[str], bool]) -> bool:
        for index, char in enumerate(raw):
            if char != "_":
                continue
            if index == 0 or index == len(raw) - 1:
                return False
            if not is_digit(raw[index - 1]) or not is_digit(raw[index + 1]):
                return False

        return True

    def _peek_at(self, offset: int) -> str:
        index = self._current + offset
        if index >= len(self._source):
            return "\0"
        return self._source[index]

    def _peek_next(self) -> str:
        return self._peek_at(1)

    @staticmethod
    def _is_digit(c: str) -> bool:
        return "0" <= c <= "9"

    @staticmethod
    def _is_binary_digit(c: str) -> bool:
        return c in ("0", "1")

    @staticmethod
    def _is_octal_digit(c: str) -> bool:
        return "0" <= c <= "7"

    @staticmethod
    def _is_hex_digit(c: str) -> bool:
        return Scanner._is_digit(c) or "a" <= c <= "f" or "A" <= c <= "F"

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
