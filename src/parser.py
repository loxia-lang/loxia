from src.error_reporter import ErrorReporter
from src.errors import ParseError
from src.expr import (
    Assign,
    Binary,
    Call,
    Expr,
    Get,
    Grouping,
    Literal,
    Logical,
    Range,
    Set,
    Super,
    This,
    Unary,
    Variable,
)
from src.stmt import (
    Block,
    Class,
    Expression,
    Field,
    ForIn,
    Function,
    If,
    Param,
    Print,
    Return,
    Stmt,
    Var,
    While,
)
from src.token_type import TokenType
from src.tokens import Token
from src.ty import NIL, PRIMITIVES, ClassTy, ListTy, MapTy, Ty, union


class Parser:
    def __init__(
        self,
        tokens: list[Token],
        *,
        repl: bool = False,
        reporter: ErrorReporter | None = None,
    ) -> None:
        self._tokens: list[Token] = tokens
        self._current: int = 0
        self._repl: bool = repl
        self.reporter: ErrorReporter = reporter if reporter is not None else ErrorReporter()

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

        # Silencia temporariamente o reporter durante o teste
        self.reporter.silent = True
        had_error_before = self.reporter.had_error

        try:
            expr = self._expression()
            # `;` final é opcional no REPL: `1 + 1;` imprime como `1 + 1`.
            self._match(TokenType.SEMICOLON)

            # Se consumiu a expressão e chegou exatamente ao fim da linha:
            if not self.reporter.had_error and self._is_at_end():
                self.reporter.silent = False
                self.reporter.had_error = had_error_before
                # Envelopa como um nó Print para ser avaliado e exibido!
                return [Print(expr)]
        except ParseError:
            pass
        finally:
            self.reporter.silent = False

        # Rollback: restaura a posição dos tokens e reseta flags de erro
        self._current = saved_current
        self.reporter.had_error = had_error_before

        # Faz o parse padrão de statements
        return self.parse()

    def _declaration(self) -> Stmt | None:
        try:
            if self._match(TokenType.CLASS):
                return self._class_declaration()

            if self._match(TokenType.FN):
                return self._function("function")

            if self._match(TokenType.VAL):
                return self._var_declaration(mutable=False)

            if self._match(TokenType.VAR):
                return self._var_declaration(mutable=True)

            return self._statement()
        except ParseError:
            self._synchronize()
            return None

    def _class_declaration(self) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect class name.")

        superclass: Variable | None = None
        if self._match(TokenType.LEFT_PAREN):
            self._consume(TokenType.IDENTIFIER, "Expect superclass name.")
            superclass = Variable(self._previous())
            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after superclass.")

        self._consume(TokenType.LEFT_BRACE, "Expect '{' before class body.")

        fields: list[Field] = []
        methods: list[Function] = []
        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            if self._match(TokenType.VAL):
                fields.append(self._field_declaration(mutable=False))
            elif self._match(TokenType.VAR):
                fields.append(self._field_declaration(mutable=True))
            else:
                methods.append(self._function("method"))

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after class body.")

        return Class(name, superclass, fields, methods)

    def _field_declaration(self, mutable: bool) -> Field:
        name = self._consume(TokenType.IDENTIFIER, "Expect field name.")

        type_annotation: Ty | None = None
        if self._match(TokenType.COLON):
            type_annotation = self._type()

        initializer: Expr | None = None
        if self._match(TokenType.EQUAL):
            initializer = self._expression()
            if not self._is_constant_default(initializer):
                self._error(name, "Field initializer must be a constant.")

        self._end_statement("Expect ';' after field declaration.")

        return Field(name, initializer, mutable, type_annotation)

    def _var_declaration(self, mutable: bool) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect variable name.")

        type_annotation: Ty | None = None
        if self._match(TokenType.COLON):
            type_annotation = self._type()

        initializer: Expr | None = None

        if self._match(TokenType.EQUAL):
            initializer = self._expression()
        elif not mutable:
            raise self._error(self._peek(), "Expect initializer for 'val' declaration.")

        self._end_statement("Expect ';' after variable declaration.")

        return Var(name, initializer, mutable, type_annotation)

    def _statement(self) -> Stmt:
        if self._match(TokenType.FOR):
            return self._for_statement()
        if self._match(TokenType.IF):
            return self._if_statement("if")

        if self._match(TokenType.PRINT):
            return self._print_statement()

        if self._match(TokenType.RETURN):
            return self._return_statement()

        if self._match(TokenType.WHILE):
            return self._while_statement()

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

    def _for_statement(self) -> Stmt:
        if not self._check(TokenType.LEFT_PAREN):
            return self._for_in_statement()

        self._consume(TokenType.LEFT_PAREN, "Expect '(' after 'for'.")
        initializer: Stmt | None = None

        if self._match(TokenType.SEMICOLON):
            initializer = None
        elif self._match(TokenType.VAL):
            initializer = self._var_declaration(mutable=False)
        elif self._match(TokenType.VAR):
            initializer = self._var_declaration(mutable=True)
        else:
            initializer = self._expression_statement()

        cond: Expr | None = None

        if not self._check(TokenType.SEMICOLON):
            cond = self._expression()

        self._consume(TokenType.SEMICOLON, "Expect ';' after loop condition.")

        increm: Expr | None = None

        if not self._check(TokenType.RIGHT_PAREN):
            increm = self._expression()

        self._consume(TokenType.RIGHT_PAREN, "Expect ')' after for clauses.")

        body = self._statement()

        if increm is not None:
            body = Block([body, Expression(increm)])

        if cond is None:
            cond = Literal(True)

        body = While(cond, body)

        if initializer is not None:
            body = Block([initializer, body])

        return body

    def _for_in_statement(self) -> Stmt:
        name = self._consume(
            TokenType.IDENTIFIER, "Expect loop variable name after 'for'."
        )
        self._consume(TokenType.IN, "Expect 'in' after loop variable.")
        iterable = self._expression()
        body = self._statement()

        return ForIn(name, iterable, body)

    def _while_statement(self) -> Stmt:
        self._consume(TokenType.LEFT_PAREN, "Expect '(' after 'while'.")
        cond = self._expression()
        self._consume(TokenType.RIGHT_PAREN, "Expect ')' after condition.")
        body = self._statement()

        return While(cond, body)

    def _print_statement(self) -> Stmt:
        value = self._expression()
        self._end_statement("Expect ';' after value.")
        return Print(value)

    def _return_statement(self) -> Stmt:
        keyword = self._previous()
        value: Expr | None = None

        if (
            not self._check(TokenType.SEMICOLON)
            and not self._is_at_end()
            and self._peek().line == keyword.line
        ):
            value = self._expression()

        self._end_statement("Expect ';' after return value.")
        return Return(keyword, value)

    def _if_statement(self, keyword: str) -> Stmt:
        self._consume(TokenType.LEFT_PAREN, f"Expect '(' after '{keyword}'.")
        cond = self._expression()
        self._consume(
            TokenType.RIGHT_PAREN, f"Expect ')' after '{keyword}' condition."
        )

        then_branch = self._statement()
        else_branch = None

        if self._match(TokenType.ELSE):
            else_branch = self._statement()
        elif self._match(TokenType.ELIF):
            else_branch = self._if_statement("elif")

        return If(cond, then_branch, else_branch)

    def _expression_statement(self) -> Stmt:
        expr = self._expression()
        self._end_statement("Expect ';' after expression.")
        return Expression(expr)

    def _end_statement(self, message: str) -> None:
        """Consome o `;` final; no REPL/EOF ou no fim da linha ele é opcional."""
        if self._match(TokenType.SEMICOLON):
            return

        if self._repl and self._is_at_end():
            return

        if self._is_at_end():
            return

        if self._peek().line > self._previous().line:
            return

        raise self._error(self._peek(), message)

    def _function(self, kind: str) -> Function:
        name = self._consume(TokenType.IDENTIFIER, f"Expect {kind} name.")
        self._consume(TokenType.LEFT_PAREN, f"Expect '(' after {kind} name.")

        parameters: list[Param] = []
        seen_default = False
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                if len(parameters) >= 255:
                    self._error(self._peek(), "Can't have more than 255 parameters.")

                mutable = self._match(TokenType.VAR)
                name_token = self._consume(TokenType.IDENTIFIER, "Expect parameter name.")

                type_annotation: Ty | None = None
                if self._match(TokenType.COLON):
                    type_annotation = self._type()

                default: Expr | None = None
                if self._match(TokenType.EQUAL):
                    default = self._expression()
                    if not self._is_constant_default(default):
                        self._error(name_token, "Default value must be a constant.")
                    seen_default = True
                elif seen_default:
                    self._error(
                        name_token,
                        "Required parameter can't follow an optional parameter.",
                    )

                parameters.append(Param(name_token, mutable, default, type_annotation))

                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RIGHT_PAREN, "Expect ')' after parameters.")

        return_type: Ty | None = None
        if self._match(TokenType.ARROW):
            return_type = self._type()

        self._consume(TokenType.LEFT_BRACE, f"Expect '{{' before {kind} body.")

        body = self._block()
        return Function(name, parameters, body, return_type)

    def _type(self) -> Ty:
        ty = self._postfix_type()

        while self._match(TokenType.PIPE):
            ty = union(ty, self._postfix_type())

        return ty

    def _postfix_type(self) -> Ty:
        ty = self._primary_type()

        while self._match(TokenType.QUESTION):
            ty = union(ty, NIL)

        return ty

    def _primary_type(self) -> Ty:
        if self._match(TokenType.LEFT_PAREN):
            ty = self._type()
            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after type.")
            return ty

        token = self._consume(TokenType.IDENTIFIER, "Expect type name.")
        name = token.lexeme

        if self._match(TokenType.LEFT_BRACKET):
            arguments = [self._type()]
            while self._match(TokenType.COMMA):
                arguments.append(self._type())
            self._consume(TokenType.RIGHT_BRACKET, "Expect ']' after type arguments.")

            return self._generic_type(token, name, arguments)

        primitive = PRIMITIVES.get(name)
        if primitive is not None:
            return primitive

        return ClassTy(name)

    def _generic_type(self, token: Token, name: str, arguments: list[Ty]) -> Ty:
        if name == "List" and len(arguments) == 1:
            return ListTy(arguments[0])
        if name == "Map" and len(arguments) == 2:
            return MapTy(arguments[0], arguments[1])

        if name in {"List", "Map"}:
            expected = 1 if name == "List" else 2
            self._error(
                token,
                f"{name} expects {expected} type argument(s), got {len(arguments)}.",
            )

        self._error(token, f"Unknown generic type '{name}'.")
        return Ty()

    def _is_constant_default(self, expr: Expr) -> bool:
        if isinstance(expr, Literal):
            return True
        if isinstance(expr, Grouping):
            return self._is_constant_default(expr.expression)
        if isinstance(expr, Unary) and expr.operator.type is TokenType.MINUS:
            value = expr.right
            return isinstance(value, Literal) and isinstance(value.value, (int, float))

        return False

    def _expression(self) -> Expr:
        return self._assignment()

    def _assignment(self) -> Expr:
        expr = self._or()

        if self._check(TokenType.EQUAL) and self._peek().line == self._previous().line:
            self._advance()
            equals = self._previous()
            value = self._assignment()

            if isinstance(expr, Variable):
                name = expr.name
                return Assign(name, value)

            if isinstance(expr, Get):
                return Set(expr.object, expr.name, value)

            self._error(equals, "Invalid assignment target.")

        return expr

    def _or(self) -> Expr:
        expr = self._and()

        while self._match_inline(TokenType.OR):
            operator = self._previous()
            right = self._and()
            expr = Logical(expr, operator, right)

        return expr

    def _and(self) -> Expr:
        expr = self._equality()

        while self._match_inline(TokenType.AND):
            operator = self._previous()
            right = self._equality()
            expr = Logical(expr, operator, right)

        return expr

    def _equality(self) -> Expr:
        expr = self._comparison()

        while self._match_inline(TokenType.BANG_EQUAL, TokenType.EQUAL_EQUAL):
            operator: Token = self._previous()
            right: Expr = self._comparison()
            expr = Binary(expr, operator, right)

        return expr

    def _comparison(self) -> Expr:
        expr: Expr = self._range()

        while self._match_inline(
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
            TokenType.LESS,
            TokenType.LESS_EQUAL,
        ):
            operator: Token = self._previous()
            right: Expr = self._range()
            expr = Binary(expr, operator, right)

        return expr

    def _range(self) -> Expr:
        expr: Expr = self._term()

        while self._match_inline(TokenType.DOT_DOT):
            operator: Token = self._previous()
            end: Expr = self._term()
            expr = Range(expr, end, operator)

        return expr

    def _term(self) -> Expr:
        expr: Expr = self._factor()

        while self._match_inline(TokenType.MINUS, TokenType.PLUS):
            operator: Token = self._previous()
            right: Expr = self._factor()
            expr = Binary(expr, operator, right)

        return expr

    def _factor(self) -> Expr:
        expr: Expr = self._unary()

        while self._match_inline(TokenType.SLASH, TokenType.STAR, TokenType.PERCENT):
            operator: Token = self._previous()
            right: Expr = self._unary()
            expr = Binary(expr, operator, right)

        return expr

    def _unary(self) -> Expr:
        if self._match(TokenType.BANG, TokenType.MINUS):
            operator: Token = self._previous()
            right: Expr = self._unary()
            return Unary(operator, right)

        return self._call()

    def _call(self) -> Expr:
        expr = self._primary()

        while True:
            if (
                self._check(TokenType.LEFT_PAREN)
                and self._peek().line == self._previous().line
            ):
                self._advance()
                expr = self._finish_call(expr)
            elif self._match(TokenType.DOT):
                name = self._consume(
                    TokenType.IDENTIFIER, "Expect property name after '.'."
                )
                expr = Get(expr, name)
            else:
                break

        return expr

    def _finish_call(self, callee: Expr) -> Expr:
        arguments: list[Expr] = []
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                if len(arguments) >= 255:
                    self._error(self._peek(), "Can't have more than 255 arguments.")

                arguments.append(self._expression())

                if not self._match(TokenType.COMMA):
                    break

        paren = self._consume(TokenType.RIGHT_PAREN, "Expect ')' after arguments.")
        return Call(callee, paren, arguments)

    def _primary(self) -> Expr:

        if self._match(TokenType.FALSE):
            return Literal(False)

        if self._match(TokenType.TRUE):
            return Literal(True)

        if self._match(TokenType.NIL):
            return Literal(None)

        if self._match(TokenType.NUMBER, TokenType.STRING):
            return Literal(self._previous().literal)

        if self._match(TokenType.SUPER):
            keyword = self._previous()
            self._consume(TokenType.DOT, "Expect '.' after 'super'.")
            method = self._consume(
                TokenType.IDENTIFIER, "Expect superclass method name."
            )
            return Super(keyword, method)

        if self._match(TokenType.THIS):
            return This(self._previous())

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

    def _match_inline(self, *types: TokenType) -> bool:
        """Como `_match`, mas só consome operador que esteja na mesma linha."""
        for token_type in types:
            if self._check(token_type):
                if self._peek().line != self._previous().line:
                    return False
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
        self.reporter.error(token, message)
        return ParseError()

    def _synchronize(self) -> None:
        self._advance()

        while not self._is_at_end():
            if self._previous().type == TokenType.SEMICOLON:
                return

            if self._peek().type in {
                TokenType.CLASS,
                TokenType.FN,
                TokenType.VAL,
                TokenType.VAR,
                TokenType.FOR,
                TokenType.IF,
                TokenType.WHILE,
                TokenType.PRINT,
                TokenType.RETURN,
            }:
                return

            self._advance()
