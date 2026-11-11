from src.error_reporter import ErrorReporter
from src.errors import ParseError
from src.expr import Assign, Binary, Expr, Grouping, Literal, Unary, Variable
from src.stmt import Block, Expression, Print, Stmt, Var
from src.token import Token
from src.token_type import TokenType


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens: list[Token] = tokens
        self._current: int = 0

    def parse(self) -> list[Stmt] | None:
        statements: list[Stmt] = []
        while not self._is_at_end():
            declaration = self._declaration()
            if declaration is not None:
                statements.append(declaration)

        return statements

    def parse_repl(self) -> list[Stmt] | None:
        """Tenta fazer o parse de uma única expressão (para REPL).

        Se não for uma expressão pura (ou se contiver erros de sintaxe),
        retorna None sem reportar erros na tela.
        """
        # Salva a posição atual para poder dar rollback caso não seja uma expressão
        saved_current = self._current

        # Silencia temporariamente o ErrorReporter durante o teste
        ErrorReporter.silent = True
        had_error_before = ErrorReporter.had_error

        try:
            expr = self._expression()
            # Se consumiu a expressão e chegou exatamente ao fim da linha:
            if not ErrorReporter.had_error and self._is_at_end():
                ErrorReporter.silent = False
                ErrorReporter.had_error = had_error_before
                # Envelopa como um nó Print para ser avaliado e exibido!
                return [Print(expr)]
        except ParseError:
            pass
        finally:
            ErrorReporter.silent = False

        # Rollback: restaura a posição dos tokens e reseta flags de erro
        self._current = saved_current
        ErrorReporter.had_error = had_error_before

        # Faz o parse padrão de statements
        return self.parse()


    def _declaration(self) -> Stmt | None:
        try:
            if self._match(TokenType.VAR):
                return self._var_declaration()

            return self._statement()
        except ParseError as e:
            self._synchronize()
            return None

    def _var_declaration(self) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect variable name.")
        initializer: Expr | None = None

        if self._match(TokenType.EQUAL):
            initializer = self._expression()

        self._consume(TokenType.SEMICOLON, "Expect ';' after variable declaration.")

        return Var(name, initializer)

    def _statement(self) -> Stmt:
        if self._match(TokenType.PRINT):
            return self._print_statement()

        if self._match(TokenType.LEFT_BRACE):
            return Block(self._block())

        return self._expression_statement()

    def _block(self) -> list[Stmt]:
        statements: list[Stmt] = []

        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            declaration = self._declaration()
            if declaration is not None:
                statements.append(declaration)

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after block.")
        return statements

    def _print_statement(self) -> Stmt:
        value = self._expression()
        self._consume(TokenType.SEMICOLON, "Expect ';' after value.")
        return Print(value)

    def _expression_statement(self) -> Stmt:
        expr = self._expression()
        self._consume(TokenType.SEMICOLON, "Expect ';' after expression.")
        return Expression(expr)

    def _expression(self) -> Expr:
        return self._assignment()

    def _assignment(self) -> Expr:
        expr = self._equality()

        if self._match(TokenType.EQUAL):
            equals = self._previous()
            value = self._assignment()

            if isinstance(expr, Variable):
                name = expr.name
                return Assign(name, value)

            self._error(equals, "Invalid assignment target.")

        return expr

    def _equality(self) -> Expr:
        expr = self._comparison()

        while self._match(TokenType.BANG_EQUAL, TokenType.EQUAL_EQUAL):
            operator: Token = self._previous()
            right: Expr = self._comparison()
            expr = Binary(expr, operator, right)

        return expr

    def _comparison(self) -> Expr:
        expr: Expr = self._term()

        while self._match(
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
            TokenType.LESS,
            TokenType.LESS_EQUAL,
        ):
            operator: Token = self._previous()
            right: Expr = self._term()
            expr = Binary(expr, operator, right)

        return expr

    def _term(self) -> Expr:
        expr: Expr = self._factor()

        while self._match(TokenType.MINUS, TokenType.PLUS):
            operator: Token = self._previous()
            right: Expr = self._factor()
            expr = Binary(expr, operator, right)

        return expr

    def _factor(self) -> Expr:
        expr: Expr = self._unary()

        while self._match(TokenType.SLASH, TokenType.STAR):
            operator: Token = self._previous()
            right: Expr = self._unary()
            expr = Binary(expr, operator, right)

        return expr

    def _unary(self) -> Expr:
        if self._match(TokenType.BANG, TokenType.MINUS):
            operator: Token = self._previous()
            right: Expr = self._unary()
            return Unary(operator, right)

        return self._primary()

    def _primary(self) -> Expr:

        if self._match(TokenType.FALSE):
            return Literal(False)

        if self._match(TokenType.TRUE):
            return Literal(True)

        if self._match(TokenType.NIL):
            return Literal(None)

        if self._match(TokenType.NUMBER, TokenType.STRING):
            return Literal(self._previous().literal)

        if self._match(TokenType.IDENTIFIER):
            return Variable(self._previous())

        if self._match(TokenType.LEFT_PAREN):
            expr: Expr = self._expression()
            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after expression.")
            return Grouping(expr)

        raise self._error(self._peek(), "Expect expression.")

    def _match(self, *types: TokenType) -> bool:
        for token_type in types:
            if self._check(token_type):
                self._advance()
                return True
        return False

    def _check(self, type: TokenType) -> bool:
        if self._is_at_end():
            return False
        return self._peek().type == type

    def _advance(self) -> Token:
        if not self._is_at_end():
            self._current += 1
        return self._previous()

    def _is_at_end(self) -> bool:
        return self._peek().type == TokenType.EOF

    def _peek(self) -> Token:
        return self._tokens[self._current]

    def _previous(self) -> Token:
        return self._tokens[self._current - 1]

    def _consume(self, type: TokenType, message: str) -> Token:
        if self._check(type):
            return self._advance()

        raise self._error(self._peek(), message)

    def _error(self, token: Token, message: str) -> ParseError:
        ErrorReporter.error(token, message)
        return ParseError()

    def _synchronize(self):
        self._advance()

        while not self._is_at_end():
            if self._previous().type == TokenType.SEMICOLON:
                return

            if self._peek().type in {
                TokenType.CLASS,
                TokenType.FUN,
                TokenType.VAR,
                TokenType.FOR,
                TokenType.IF,
                TokenType.WHILE,
                TokenType.PRINT,
                TokenType.RETURN,
            }:
                return

            self._advance()
