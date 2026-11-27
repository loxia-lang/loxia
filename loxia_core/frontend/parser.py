# SPDX-License-Identifier: MIT OR Apache-2.0
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.diagnostic import Span
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.errors import ParseError
from loxia_core.frontend.destructuring import (
    DestructurePattern,
    NamePattern,
    TuplePattern,
    first_token,
)
from loxia_core.frontend.expr import (
    As,
    Assign,
    Binary,
    Call,
    Conditional,
    ErrorExpr,
    Expr,
    Get,
    Grouping,
    Index,
    IndexSet,
    InterpolatedString,
    Is,
    Lambda,
    ListLiteral,
    Literal,
    LiteralPattern,
    Logical,
    MapLiteral,
    Match,
    MatchArm,
    Pattern,
    Range,
    Set,
    Super,
    This,
    TupleLiteral,
    Unary,
    Variable,
    VariantPattern,
    WildcardPattern,
)
from loxia_core.frontend.spans import span_of_token_exact, span_of_token_range
from loxia_core.frontend.stmt import (
    Block,
    Break,
    Class,
    Continue,
    Destructure,
    EnumDecl,
    EnumVariant,
    ErrorStmt,
    ExceptClause,
    Expression,
    Field,
    ForIn,
    Function,
    If,
    Import,
    ImportName,
    Interface,
    Param,
    Raise,
    Return,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import (
    ERROR,
    NIL,
    PRIMITIVES,
    ClassTy,
    FnTy,
    ListTy,
    MapTy,
    TupleTy,
    Ty,
    union,
)


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
        self._bracket_depth: int = 0
        self.reporter: ErrorReporter = reporter if reporter is not None else ErrorReporter()
        # Nomes de tipo vistos em anotações/assinaturas, em ordem textual. É uma
        # side table (como a trivia): o AST e o JSON v2 não mudam (ADR-0090/#130).
        self.type_spans: list[Span] = []

    def parse(self) -> list[Stmt] | None:
        statements: list[Stmt] = []
        while not self._is_at_end():
            before = self._current
            try:
                declaration = self._declaration()
            except RecursionError:
                # Deeply nested input (`[[[[...`) exhausts the Python stack before the
                # parser can build an AST. It is a syntax error, not a crash.
                self.reporter.error(self._peek(), "Too deeply nested.", code=Code.SYNTAX_UNEXPECTED)
                break
            if declaration is not None:
                statements.append(declaration)
            if self._current == before:
                # Um `_synchronize` que não avançou não pode travar o parse inteiro.
                self._advance()

        return statements

    def parse_expression(self) -> Expr:
        try:
            expr = self._expression()
        except RecursionError:
            raise self._error(self._peek(), "Too deeply nested.") from None
        if not self._is_at_end():
            raise self._error(self._peek(), "Expect end of interpolation.")

        return expr

    def parse_repl(self) -> list[Stmt] | None:
        """Tenta fazer o parse de uma única expressão (para REPL).

        Se não for uma expressão pura (ou se contiver erros de sintaxe),
        retorna None sem reportar erros na tela.
        """
        # Salva a posição atual para poder dar rollback caso não seja uma expressão
        saved_current = self._current
        saved_type_spans = len(self.type_spans)
        state = self.reporter.mark()

        try:
            expr = self._expression()
            # `;` final é opcional no REPL: `1 + 1;` imprime como `1 + 1`.
            self._match(TokenType.SEMICOLON)

            # Se consumiu a expressão e chegou exatamente ao fim da linha:
            if not self.reporter.had_error and self._is_at_end():
                self.reporter.restore(state)
                # REPL: uma expressão pura é avaliada e exibida via `print`.
                if (
                    isinstance(expr, Call)
                    and isinstance(expr.callee, Variable)
                    and expr.callee.name.lexeme == "print"
                ):
                    return [Expression(expr)]
                call = Call(
                    Variable(Token(TokenType.IDENTIFIER, "print", None, 0)),
                    Token(TokenType.LEFT_PAREN, "(", None, 0),
                    [expr],
                )
                return [Expression(call)]
        except ParseError:
            pass
        except RecursionError:
            # Fall through to the statement parser, which reports "Too deeply nested.".
            pass

        # Rollback: restaura a posição dos tokens e descarta os diagnósticos do teste
        self._current = saved_current
        del self.type_spans[saved_type_spans:]
        self.reporter.restore(state)

        # Faz o parse padrão de statements
        return self.parse()

    def _declaration(self) -> Stmt | None:
        start = self._peek()
        try:
            if self._match(TokenType.IMPORT):
                return self._import_declaration(self._previous())
            if self._match(TokenType.FROM):
                return self._from_import_declaration(self._previous())
            if self._is_type_alias_declaration():
                return self._type_alias_declaration()
            if self._match(TokenType.CLASS):
                return self._class_declaration(self._previous())

            if self._match(TokenType.INTERFACE):
                return self._interface_declaration(self._previous())

            if self._match(TokenType.ENUM):
                return self._enum_declaration(self._previous())

            if self._match(TokenType.FN):
                if self._check(TokenType.LEFT_PAREN):
                    expression = self._lambda(self._previous())
                    self._end_statement("Expect ';' after expression.")
                    return Expression(expression)

                return self._function("function", fn_token=self._previous())

            if self._match(TokenType.VAL):
                return self._var_declaration(mutable=False, keyword=self._previous())

            if self._match(TokenType.VAR):
                return self._var_declaration(mutable=True, keyword=self._previous())

            return self._statement()
        except ParseError as error:
            self._synchronize(error.token)
            end = self._previous()
            if (end.offset or 0) < (start.offset or 0):  # pragma: no cover - EOF guard
                end = start
            return ErrorStmt(start, end, error.message)

    def _is_type_alias_declaration(self) -> bool:
        if not self._check(TokenType.IDENTIFIER) or self._peek().lexeme != "type":
            return False
        if self._current + 2 >= len(self._tokens):
            return False
        return self._tokens[self._current + 1].type is TokenType.IDENTIFIER and self._tokens[
            self._current + 2
        ].type in (TokenType.EQUAL, TokenType.LEFT_BRACKET)

    def _type_alias_declaration(self) -> Stmt:
        keyword = self._advance()
        name = self._consume(TokenType.IDENTIFIER, "Expect type alias name.")
        if self._check(TokenType.LEFT_BRACKET):
            raise self._error(
                self._peek(),
                "Type aliases can't be generic yet.",
                Code.INVALID_TYPE_ANNOTATION,
            )
        self._consume(TokenType.EQUAL, "Expect '=' after type alias name.")
        target, type_span = self._type_with_span()
        end = self._previous()
        self._end_statement("Expect ';' after type alias.")
        return TypeAlias(keyword, name, target, doc=keyword.doc, end=end, type_span=type_span)

    def _module_path(self) -> tuple[Token, ...]:
        path = [self._consume(TokenType.IDENTIFIER, "Expect module name.")]
        while self._match(TokenType.DOT):
            path.append(self._consume(TokenType.IDENTIFIER, "Expect name after '.'."))
        return tuple(path)

    def _import_declaration(self, keyword: Token) -> Stmt:
        path = self._module_path()
        alias = None
        if self._match(TokenType.AS):
            alias = self._consume(TokenType.IDENTIFIER, "Expect alias name.")
        end = self._end_statement("Expect ';' after import.")
        return Import(
            path=path,
            alias=alias,
            from_import=False,
            start=keyword,
            end=end,
        )

    def _from_import_declaration(self, keyword: Token) -> Stmt:
        path = self._module_path()
        self._consume(TokenType.IMPORT, "Expect 'import' after module path.")
        names: list[ImportName] = []
        while True:
            name = self._consume(TokenType.IDENTIFIER, "Expect imported name.")
            alias = None
            if self._match(TokenType.AS):
                alias = self._consume(TokenType.IDENTIFIER, "Expect alias name.")
            names.append(ImportName(name, alias))
            if not self._match(TokenType.COMMA):
                break
        end = self._end_statement("Expect ';' after import.")
        return Import(
            path=path,
            names=tuple(names),
            from_import=True,
            start=keyword,
            end=end,
        )

    def _class_declaration(self, keyword: Token) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect class name.")
        type_params, type_param_bounds = self._type_parameters()
        self._reject_type_param_bounds(type_param_bounds, "class")

        superclass: Variable | None = None
        if self._match(TokenType.LEFT_PAREN):
            self._consume(TokenType.IDENTIFIER, "Expect superclass name.")
            superclass = Variable(self._previous())
            if self._check(TokenType.LEFT_BRACKET):
                raise self._error(
                    self._peek(),
                    "Generic superclasses aren't supported yet.",
                    Code.INVALID_TYPE_ANNOTATION,
                )
            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after superclass.")

        implements: list[Token] = []
        if self._match_contextual("implements"):
            while True:
                implements.append(self._consume(TokenType.IDENTIFIER, "Expect interface name."))
                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.LEFT_BRACE, "Expect '{' before class body.")

        fields: list[Field] = []
        methods: list[Function] = []
        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            if self._match(TokenType.VAL):
                fields.append(self._field_declaration(mutable=False, keyword=self._previous()))
            elif self._match(TokenType.VAR):
                fields.append(self._field_declaration(mutable=True, keyword=self._previous()))
            else:
                # `fn` é opcional em método: o corpo da classe já marca a declaração.
                fn_token = self._previous() if self._match(TokenType.FN) else None
                methods.append(self._function("method", fn_token=fn_token))

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after class body.")

        return Class(
            name,
            superclass,
            fields,
            methods,
            type_params,
            implements=implements,
            doc=keyword.doc,
            keyword=keyword,
            end=self._previous(),
        )

    def _interface_declaration(self, keyword: Token) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect interface name.")
        if self._check(TokenType.LEFT_BRACKET):
            raise self._error(
                self._peek(),
                "Generic interfaces aren't supported yet.",
                Code.GENERIC_UNSUPPORTED,
            )

        self._consume(TokenType.LEFT_BRACE, "Expect '{' before interface body.")
        methods: list[Function] = []
        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            if self._match(TokenType.VAL, TokenType.VAR):
                raise self._error(
                    self._previous(),
                    "Interfaces can't have fields.",
                    Code.INVALID_DECLARATION,
                )
            # `fn` é opcional, como em método (ADR-0067).
            fn_token = self._previous() if self._match(TokenType.FN) else None
            methods.append(self._function("method", allow_abstract=True, fn_token=fn_token))

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after interface body.")
        return Interface(name, methods, doc=keyword.doc, keyword=keyword, end=self._previous())

    def _enum_declaration(self, keyword: Token) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect enum name.")
        type_params, type_param_bounds = self._type_parameters()
        self._reject_type_param_bounds(type_param_bounds, "enum")
        self._consume(TokenType.LEFT_BRACE, "Expect '{' before enum variants.")

        variants: list[EnumVariant] = []
        if not self._check(TokenType.RIGHT_BRACE):
            while True:
                variant = self._consume(TokenType.IDENTIFIER, "Expect variant name.")
                payload: list[Ty] = []
                payload_spans: list[Span] = []
                if self._match(TokenType.LEFT_PAREN):
                    if not self._check(TokenType.RIGHT_PAREN):
                        payload_ty, payload_span = self._type_with_span()
                        payload.append(payload_ty)
                        payload_spans.append(payload_span)
                        while self._match(TokenType.COMMA):
                            payload_ty, payload_span = self._type_with_span()
                            payload.append(payload_ty)
                            payload_spans.append(payload_span)
                    self._consume(
                        TokenType.RIGHT_PAREN,
                        "Expect ')' after variant payload.",
                    )

                variants.append(
                    EnumVariant(variant, payload, doc=variant.doc, payload_spans=payload_spans)
                )
                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after enum variants.")
        return EnumDecl(
            name,
            type_params,
            variants,
            doc=keyword.doc,
            keyword=keyword,
            end=self._previous(),
        )

    def _field_declaration(self, mutable: bool, *, keyword: Token) -> Field:
        name = self._consume(TokenType.IDENTIFIER, "Expect field name.")

        type_annotation: Ty | None = None
        type_span: Span | None = None
        if self._match(TokenType.COLON):
            type_annotation, type_span = self._type_with_span()

        initializer: Expr | None = None
        if self._match(TokenType.EQUAL):
            initializer = self._expression()
            if not self._is_constant_default(initializer):
                self._error(
                    name,
                    "Field initializer must be a constant.",
                    Code.INVALID_DECLARATION,
                )

        end = self._end_statement("Expect ';' after field declaration.") or self._previous()
        return Field(
            name,
            initializer,
            mutable,
            type_annotation,
            doc=keyword.doc,
            keyword=keyword,
            end=end,
            type_span=type_span,
        )

    def _destructure(self, mutable: bool, *, keyword: Token) -> Stmt:
        pattern = self._destructure_pattern()

        type_annotation: Ty | None = None
        type_span: Span | None = None
        if self._match(TokenType.COLON):
            type_annotation, type_span = self._type_with_span()

        self._consume(TokenType.EQUAL, "Expect '=' after destructuring pattern.")
        initializer = self._expression()
        end = self._previous()
        self._end_statement("Expect ';' after destructuring.")

        return Destructure(
            pattern,
            initializer,
            mutable,
            type_annotation,
            keyword=keyword,
            end=end,
            type_span=type_span,
        )

    def _destructure_pattern(self) -> DestructurePattern:
        if self._match(TokenType.LEFT_PAREN):
            elements = [self._destructure_pattern()]
            while self._match(TokenType.COMMA):
                elements.append(self._destructure_pattern())

            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after destructuring pattern.")
            if len(elements) < 2:
                raise self._error(
                    first_token(elements[0]),
                    "Destructuring needs at least two elements.",
                    Code.INVALID_DECLARATION,
                )
            return TuplePattern(elements)

        name = self._consume(TokenType.IDENTIFIER, "Expect variable name.")
        return NamePattern(name)

    def _var_declaration(self, mutable: bool, *, keyword: Token) -> Stmt:
        if self._check(TokenType.LEFT_PAREN):
            return self._destructure(mutable, keyword=keyword)

        name = self._consume(TokenType.IDENTIFIER, "Expect variable name.")

        type_annotation: Ty | None = None
        type_span: Span | None = None
        if self._match(TokenType.COLON):
            type_annotation, type_span = self._type_with_span()

        initializer: Expr | None = None

        if self._match(TokenType.EQUAL):
            initializer = self._expression()
        elif not mutable:
            raise self._error(
                self._peek(),
                "Expect initializer for 'val' declaration.",
                Code.INVALID_DECLARATION,
            )

        end = self._previous()
        self._end_statement("Expect ';' after variable declaration.")

        return Var(
            name,
            initializer,
            mutable,
            type_annotation,
            doc=keyword.doc,
            keyword=keyword,
            end=end,
            type_span=type_span,
        )

    def _statement(self) -> Stmt:
        if self._match(TokenType.FOR):
            return self._for_statement(self._previous())
        if self._match(TokenType.IF):
            return self._if_statement(self._previous())

        if self._match(TokenType.RETURN):
            return self._return_statement()

        if self._match(TokenType.BREAK):
            return self._break_statement()

        if self._match(TokenType.CONTINUE):
            return self._continue_statement()

        if self._match(TokenType.WHILE):
            return self._while_statement(self._previous())

        if self._match(TokenType.TRY):
            return self._try_statement(self._previous())

        if self._match(TokenType.RAISE):
            return self._raise_statement(self._previous())

        if self._match(TokenType.LEFT_BRACE):
            start = self._previous()
            statements = self._block()
            return Block(statements, start=start, end=self._previous())

        return self._expression_statement()

    def _try_statement(self, keyword: Token) -> Stmt:
        self._consume(TokenType.LEFT_BRACE, "Expect '{' after 'try'.")
        body = self._block()

        handlers: list[ExceptClause] = []
        while self._match(TokenType.EXCEPT):
            except_keyword = self._previous()
            type_name = self._consume(TokenType.IDENTIFIER, "Expect exception type after 'except'.")
            self._consume(TokenType.AS, "Expect 'as' after exception type.")
            binding = self._consume(TokenType.IDENTIFIER, "Expect binding name after 'as'.")
            self._consume(TokenType.LEFT_BRACE, "Expect '{' after except binding.")
            except_body = self._block()
            handlers.append(
                ExceptClause(
                    type_name,
                    binding,
                    except_body,
                    keyword=except_keyword,
                    end=self._previous(),
                )
            )

        finally_body: list[Stmt] | None = None
        if self._match(TokenType.FINALLY):
            self._consume(TokenType.LEFT_BRACE, "Expect '{' after 'finally'.")
            finally_body = self._block()

        if not handlers and finally_body is None:
            raise self._error(
                keyword,
                "Try needs at least one 'except' or 'finally'.",
                Code.INVALID_DECLARATION,
            )

        return Try(keyword, body, handlers, finally_body, end=self._previous())

    def _break_statement(self) -> Stmt:
        keyword = self._previous()
        self._end_statement("Expect ';' after 'break'.")
        return Break(keyword)

    def _continue_statement(self) -> Stmt:
        keyword = self._previous()
        self._end_statement("Expect ';' after 'continue'.")
        return Continue(keyword)

    def _raise_statement(self, keyword: Token) -> Stmt:
        value: Expr | None = None
        if not self._check(TokenType.SEMICOLON) and not self._check(TokenType.RIGHT_BRACE):
            value = self._expression()

        self._end_statement("Expect ';' after raise.")
        return Raise(keyword, value)

    def _block(self) -> list[Stmt]:
        statements: list[Stmt] = []

        # Um bloco é uma fronteira de statements: brackets abertos fora dele não podem
        # fazer um `-` no início da linha virar subtração (ADR-0067).
        saved_depth = self._bracket_depth
        self._bracket_depth = 0
        try:
            while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
                declaration = self._declaration()
                if declaration is not None:
                    statements.append(declaration)

            self._consume(TokenType.RIGHT_BRACE, "Expect '}' after block.")
            return statements
        finally:
            self._bracket_depth = saved_depth

    def _for_statement(self, keyword: Token) -> Stmt:
        if self._check(TokenType.LEFT_PAREN):
            raise self._error(
                self._peek(),
                "C-style 'for' was removed; use `for x in range(n)` or a `while` loop.",
                Code.SYNTAX_UNEXPECTED,
            )

        return self._for_in_statement(keyword)

    def _for_in_statement(self, keyword: Token) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect loop variable name after 'for'.")
        self._consume(TokenType.IN, "Expect 'in' after loop variable.")
        iterable = self._expression()
        body = self._statement()

        return ForIn(name, iterable, body, keyword=keyword)

    def _while_statement(self, keyword: Token) -> Stmt:
        self._consume(TokenType.LEFT_PAREN, "Expect '(' after 'while'.")
        cond = self._expression()
        self._consume(TokenType.RIGHT_PAREN, "Expect ')' after condition.")
        body = self._statement()

        return While(cond, body, keyword=keyword)

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

    def _if_statement(self, keyword: Token) -> Stmt:
        self._consume(TokenType.LEFT_PAREN, f"Expect '(' after '{keyword.lexeme}'.")
        cond = self._expression()
        self._consume(TokenType.RIGHT_PAREN, f"Expect ')' after '{keyword.lexeme}' condition.")

        then_branch = self._statement()
        else_branch = None

        if self._match(TokenType.ELSE):
            else_branch = self._statement()
        elif self._match(TokenType.ELIF):
            else_branch = self._if_statement(self._previous())

        return If(cond, then_branch, else_branch, keyword=keyword)

    def _expression_statement(self) -> Stmt:
        start = self._peek()
        try:
            expr = self._expression()
        except ParseError as error:
            self._synchronize(error.token)
            end = self._previous()
            if (end.offset or 0) < (start.offset or 0):  # pragma: no cover - EOF guard
                end = start
            return Expression(ErrorExpr(start, end, error.message))
        if self._check(TokenType.COLON):
            raise self._error(
                self._peek(),
                "Unexpected ':'. Map literals can't start a statement; "
                "use 'val m = { ... }' or parentheses.",
                Code.INVALID_LITERAL,
            )
        self._end_statement("Expect ';' after expression.")
        return Expression(expr)

    def _end_statement(self, message: str) -> Token | None:
        """Consome o `;` final; no REPL/EOF, no fim da linha ou antes de `}` ele é opcional."""
        if self._match(TokenType.SEMICOLON):
            return self._previous()

        if self._repl and self._is_at_end():
            return None

        if self._is_at_end():
            return None

        # `}` nunca continua uma expressão: fechar o bloco/pai termina o statement
        # (permite `if (ok) { print 1 }` na mesma linha).
        if self._check(TokenType.RIGHT_BRACE):
            return None

        if self._peek().line > self._previous().line:
            return None

        raise self._error(self._peek(), message)

    def _function(
        self,
        kind: str,
        *,
        allow_abstract: bool = False,
        fn_token: Token | None = None,
    ) -> Function:
        name = self._consume(TokenType.IDENTIFIER, f"Expect {kind} name.")
        doc = name.doc or (fn_token.doc if fn_token is not None else None)
        type_params, type_param_bounds = self._type_parameters()
        self._consume(TokenType.LEFT_PAREN, f"Expect '(' after {kind} name.")
        parameters = self._parameters()
        params_end = self._previous()

        return_type: Ty | None = None
        return_type_span: Span | None = None
        if self._match(TokenType.ARROW):
            return_type, return_type_span = self._type_with_span()

        if allow_abstract and not self._check(TokenType.LEFT_BRACE):
            self._end_statement("Expect ';' after method signature.")
            return Function(
                name,
                parameters,
                [],
                return_type,
                type_params,
                type_param_bounds=type_param_bounds,
                abstract=True,
                doc=doc,
                fn_token=fn_token,
                params_end=params_end,
            )

        self._consume(TokenType.LEFT_BRACE, f"Expect '{{' before {kind} body.")

        body = self._block()
        end = self._previous()
        return Function(
            name,
            parameters,
            body,
            return_type,
            type_params,
            type_param_bounds=type_param_bounds,
            doc=doc,
            end=end,
            fn_token=fn_token,
            params_end=params_end,
            return_type_span=return_type_span,
        )

    def _type_parameters(
        self,
    ) -> tuple[list[Token], list[tuple[Token, ...]]]:
        if not self._match(TokenType.LEFT_BRACKET):
            return [], []

        parameters: list[Token] = []
        bounds: list[tuple[Token, ...]] = []
        while True:
            parameters.append(self._consume(TokenType.IDENTIFIER, "Expect type parameter name."))
            parameter_bounds: list[Token] = []
            if self._match(TokenType.COLON):
                while True:
                    parameter_bounds.append(
                        self._consume(TokenType.IDENTIFIER, "Expect constraint name.")
                    )
                    if not self._match(TokenType.PLUS):
                        break
            bounds.append(tuple(parameter_bounds))
            if not self._match(TokenType.COMMA):
                break

        self._consume(TokenType.RIGHT_BRACKET, "Expect ']' after type parameters.")
        return parameters, bounds

    def _reject_type_param_bounds(self, bounds: list[tuple[Token, ...]], kind: str) -> None:
        for parameter_bounds in bounds:
            if parameter_bounds:
                raise self._error(
                    parameter_bounds[0],
                    f"Constraints on {kind} type parameters aren't supported yet.",
                    Code.INVALID_TYPE_ANNOTATION,
                )

    def _parameters(self) -> list[Param]:
        parameters: list[Param] = []
        seen_default = False
        saw_variadic = False
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                if len(parameters) >= 255:
                    self._error(
                        self._peek(),
                        "Can't have more than 255 parameters.",
                        Code.LIMIT_EXCEEDED,
                    )
                variadic = self._match(TokenType.ELLIPSIS)
                if variadic and saw_variadic:
                    self._error(
                        self._previous(),
                        "Only one variadic parameter is allowed.",
                        Code.INVALID_DECLARATION,
                    )
                if variadic:
                    saw_variadic = True

                mutable = self._match(TokenType.VAR)
                name_token = self._consume(TokenType.IDENTIFIER, "Expect parameter name.")

                type_annotation: Ty | None = None
                type_span: Span | None = None
                if self._match(TokenType.COLON):
                    type_annotation, type_span = self._type_with_span()

                default: Expr | None = None
                if self._match(TokenType.EQUAL):
                    default = self._expression()
                    if not self._is_constant_default(default):
                        self._error(
                            name_token,
                            "Default value must be a constant.",
                            Code.INVALID_DECLARATION,
                        )
                    seen_default = True
                elif seen_default and not variadic:
                    self._error(
                        name_token,
                        "Required parameter can't follow an optional parameter.",
                        Code.INVALID_DECLARATION,
                    )

                parameters.append(
                    Param(
                        name_token,
                        mutable,
                        default,
                        type_annotation,
                        variadic,
                        type_span=type_span,
                    )
                )

                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RIGHT_PAREN):
                    break

        self._consume(TokenType.RIGHT_PAREN, "Expect ')' after parameters.")
        for index, param in enumerate(parameters):
            if param.variadic and index != len(parameters) - 1:
                self._error(
                    param.name,
                    "Variadic parameter must be last.",
                    Code.INVALID_DECLARATION,
                )
        return parameters

    def _lambda(self, keyword: Token) -> Lambda:
        self._consume(TokenType.LEFT_PAREN, "Expect '(' after 'fn' in lambda.")
        parameters = self._parameters()
        for param in parameters:
            if param.default is not None:
                self._error(
                    param.name,
                    "Lambda parameters can't have defaults.",
                    Code.INVALID_DECLARATION,
                )

        return_type: Ty | None = None
        return_type_span: Span | None = None
        if self._match(TokenType.ARROW):
            return_type, return_type_span = self._type_with_span()

        body: list[Stmt]
        end: Token
        if self._match(TokenType.FAT_ARROW):
            arrow = self._previous()
            expression = self._expression()
            body = [Return(arrow, expression)]
            end = self._previous()
        elif self._match(TokenType.LEFT_BRACE):
            body = self._block()
            end = self._previous()
        else:
            raise self._error(self._peek(), "Expect '=>' or '{' after lambda parameters.")

        return Lambda(
            keyword,
            parameters,
            body,
            return_type,
            end=end,
            return_type_span=return_type_span,
        )

    def _type_with_span(self, *, allow_union: bool = True) -> tuple[Ty, Span]:
        start = self._peek()
        ty = self._type(allow_union=allow_union)
        return ty, span_of_token_range(start, self._previous())

    def _type(self, *, allow_union: bool = True) -> Ty:
        ty = self._postfix_type()

        if not allow_union:
            return ty

        while self._match(TokenType.PIPE):
            ty = union(ty, self._postfix_type())

        return ty

    def _postfix_type(self) -> Ty:
        ty = self._primary_type()

        while self._match(TokenType.QUESTION):
            ty = union(ty, NIL)

        return ty

    def _primary_type(self) -> Ty:
        if self._match(TokenType.FN):
            return self._function_type()

        if self._match(TokenType.LEFT_PAREN):
            first = self._type()

            if self._match(TokenType.COMMA):
                items = [first]
                while True:
                    items.append(self._type())
                    if not self._match(TokenType.COMMA):
                        break

                self._consume(TokenType.RIGHT_PAREN, "Expect ')' after tuple type.")
                return TupleTy(tuple(items))

            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after type.")
            return first

        token = self._consume(TokenType.IDENTIFIER, "Expect type name.")
        self.type_spans.append(span_of_token_exact(token))
        name = token.lexeme

        if self._match(TokenType.LEFT_BRACKET):
            arguments = [self._type()]
            while self._match(TokenType.COMMA):
                arguments.append(self._type())
            self._consume(TokenType.RIGHT_BRACKET, "Expect ']' after type arguments.")

            return self._generic_type(token, name, arguments)

        if name in {"List", "Map"}:
            expected = 1 if name == "List" else 2
            self._error(
                token,
                f"{name} expects {expected} type argument(s), got 0.",
                Code.INVALID_TYPE_ANNOTATION,
            )
            return ERROR

        primitive = PRIMITIVES.get(name)
        if primitive is not None:
            return primitive

        return ClassTy(name, token=token)

    def _function_type(self) -> Ty:
        self._consume(TokenType.LEFT_PAREN, "Expect '(' after 'fn' in function type.")
        params: list[Ty] = []
        variadic = False
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                if self._match(TokenType.ELLIPSIS):
                    variadic = True
                    params.append(self._type())
                    if self._match(TokenType.COMMA):
                        self._error(
                            self._previous(),
                            "Variadic parameter must be last.",
                            Code.INVALID_TYPE_ANNOTATION,
                        )
                    break
                params.append(self._type())
                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RIGHT_PAREN, "Expect ')' after function type parameters.")
        self._consume(TokenType.ARROW, "Expect '->' after function type parameters.")
        ret = self._type()
        return FnTy(
            tuple(params),
            ret,
            len(params) - 1 if variadic else len(params),
            variadic,
        )

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
                Code.INVALID_TYPE_ANNOTATION,
            )
        elif name in {"list", "map"}:
            self._error(
                token,
                f"Unknown generic type '{name}'. Did you mean '{name.capitalize()}'?",
                Code.INVALID_TYPE_ANNOTATION,
            )
        else:
            return ClassTy(name, tuple(arguments), token=token)

        return ERROR

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
        expr = self._conditional()

        if self._check(TokenType.EQUAL) and self._peek().line == self._previous().line:
            self._advance()
            equals = self._previous()
            value = self._assignment()

            if isinstance(expr, Variable):
                name = expr.name
                return Assign(name, value)

            if isinstance(expr, Get):
                if self._has_optional_chain(expr):
                    self._error(
                        equals,
                        "Can't assign through optional chaining.",
                        Code.INVALID_ASSIGNMENT_TARGET,
                    )
                    return expr
                return Set(expr.object, expr.name, value)

            if isinstance(expr, Index):
                if self._has_optional_chain(expr):
                    self._error(
                        equals,
                        "Can't assign through optional chaining.",
                        Code.INVALID_ASSIGNMENT_TARGET,
                    )
                    return expr
                return IndexSet(expr.object, expr.index, value, expr.bracket, expr.end)

            self._error(equals, "Invalid assignment target.", Code.INVALID_ASSIGNMENT_TARGET)

        return expr

    def _has_optional_chain(self, expr: Expr) -> bool:
        if isinstance(expr, Get):
            return expr.optional or self._has_optional_chain(expr.object)
        if isinstance(expr, Index):
            return self._has_optional_chain(expr.object)
        if isinstance(expr, Call):
            return expr.optional or self._has_optional_chain(expr.callee)
        if isinstance(expr, Grouping):
            return self._has_optional_chain(expr.expression)

        return False

    def _conditional(self) -> Expr:
        expr = self._coalesce()

        if self._match_infix(TokenType.IF):
            condition = self._coalesce()
            self._consume(TokenType.ELSE, "Expect 'else' after conditional expression.")
            else_branch = self._conditional()
            return Conditional(condition, expr, else_branch)

        return expr

    def _coalesce(self) -> Expr:
        expr = self._or()

        if self._match_infix(TokenType.QUESTION_QUESTION):
            operator = self._previous()
            right = self._coalesce()
            return Logical(expr, operator, right)

        return expr

    def _or(self) -> Expr:
        expr = self._and()

        while self._match_infix(TokenType.OR):
            operator = self._previous()
            right = self._and()
            expr = Logical(expr, operator, right)

        return expr

    def _and(self) -> Expr:
        expr = self._equality()

        while self._match_infix(TokenType.AND):
            operator = self._previous()
            right = self._equality()
            expr = Logical(expr, operator, right)

        return expr

    def _equality(self) -> Expr:
        expr = self._comparison()

        while self._match_infix(TokenType.NOT_EQUAL, TokenType.EQUAL_EQUAL):
            operator: Token = self._previous()
            right: Expr = self._comparison()
            expr = Binary(expr, operator, right)

        return expr

    def _comparison(self) -> Expr:
        expr: Expr = self._bitwise_or()

        while True:
            if self._match_infix(
                TokenType.GREATER,
                TokenType.GREATER_EQUAL,
                TokenType.LESS,
                TokenType.LESS_EQUAL,
            ):
                operator: Token = self._previous()
                right: Expr = self._bitwise_or()
                expr = Binary(expr, operator, right)
            elif self._match_infix(TokenType.IS):
                operator = self._previous()
                test_type, type_span = self._type_with_span(allow_union=False)
                if self._check(TokenType.PIPE):
                    raise self._error(
                        self._peek(),
                        "Type unions in 'is' need parentheses: 'is (A | B)'.",
                        Code.INVALID_TYPE_ANNOTATION,
                    )
                expr = Is(expr, test_type, operator, type_span=type_span)
            else:
                break

        return expr

    def _bitwise_or(self) -> Expr:
        expr: Expr = self._bitwise_xor()

        while self._match_infix(TokenType.PIPE):
            operator: Token = self._previous()
            right: Expr = self._bitwise_xor()
            expr = Binary(expr, operator, right)

        return expr

    def _bitwise_xor(self) -> Expr:
        expr: Expr = self._bitwise_and()

        while self._match_infix(TokenType.CARET):
            operator: Token = self._previous()
            right: Expr = self._bitwise_and()
            expr = Binary(expr, operator, right)

        return expr

    def _bitwise_and(self) -> Expr:
        expr: Expr = self._range()

        while self._match_infix(TokenType.AMPERSAND):
            operator: Token = self._previous()
            right: Expr = self._range()
            expr = Binary(expr, operator, right)

        return expr

    def _range(self) -> Expr:
        expr: Expr = self._shift()

        while self._match_infix(TokenType.DOT_DOT, TokenType.DOT_DOT_EQUAL):
            operator: Token = self._previous()
            end: Expr = self._shift()
            expr = Range(
                expr,
                end,
                operator,
                inclusive=operator.type is TokenType.DOT_DOT_EQUAL,
            )

        return expr

    def _shift(self) -> Expr:
        expr: Expr = self._term()

        while self._match_infix(
            TokenType.LESS_LESS,
            TokenType.GREATER_GREATER,
            TokenType.GREATER_GREATER_GREATER,
        ):
            operator: Token = self._previous()
            right: Expr = self._term()
            expr = Binary(expr, operator, right)

        return expr

    def _term(self) -> Expr:
        expr: Expr = self._factor()

        while self._match_infix(TokenType.MINUS, TokenType.PLUS):
            operator: Token = self._previous()
            right: Expr = self._factor()
            expr = Binary(expr, operator, right)

        return expr

    def _factor(self) -> Expr:
        expr: Expr = self._as()

        while self._match_infix(
            TokenType.SLASH,
            TokenType.SLASH_SLASH,
            TokenType.STAR,
            TokenType.PERCENT,
        ):
            operator: Token = self._previous()
            right: Expr = self._as()
            expr = Binary(expr, operator, right)

        return expr

    def _as(self) -> Expr:
        expr: Expr = self._unary()

        while self._match_infix(TokenType.AS):
            operator: Token = self._previous()
            target, type_span = self._type_with_span()
            expr = As(expr, target, operator, type_span=type_span)

        return expr

    def _unary(self) -> Expr:
        if self._match(TokenType.NOT, TokenType.MINUS, TokenType.TILDE):
            operator: Token = self._previous()
            right: Expr = self._unary()
            return Unary(operator, right)

        return self._power()

    def _power(self) -> Expr:
        expr: Expr = self._call()

        if self._match_infix(TokenType.STAR_STAR):
            operator: Token = self._previous()
            right: Expr = self._unary()
            return Binary(expr, operator, right)

        return expr

    def _call(self) -> Expr:
        expr = self._primary()
        optional_call = False

        while True:
            if self._check(TokenType.LEFT_PAREN) and self._peek().line == self._previous().line:
                self._advance()
                expr = self._finish_call(expr, optional=optional_call)
                optional_call = False
            elif self._match(TokenType.QUESTION_DOT):
                name = self._consume(TokenType.IDENTIFIER, "Expect property name after '?.'.")
                expr = Get(expr, name, optional=True)
                optional_call = True
            elif self._match(TokenType.DOT):
                name = self._consume(TokenType.IDENTIFIER, "Expect property name after '.'.")
                expr = Get(expr, name)
                optional_call = False
            elif self._check(TokenType.LEFT_BRACKET) and self._peek().line == self._previous().line:
                bracket = self._advance()
                with self._in_brackets():
                    if self._check(TokenType.RIGHT_BRACKET):
                        raise self._error(self._peek(), "Expect index expression.")

                    index = self._expression()
                    end = self._consume(TokenType.RIGHT_BRACKET, "Expect ']' after index.")
                    expr = Index(expr, index, bracket, end)
                optional_call = False
            else:
                break

        return expr

    def _finish_call(self, callee: Expr, *, optional: bool = False) -> Expr:
        with self._in_brackets():
            arguments: list[Expr] = []
            commas: list[Token] = []
            arg_ends: list[Token] = []
            spread = False
            if not self._check(TokenType.RIGHT_PAREN):
                while True:
                    if len(arguments) >= 255:
                        self._error(
                            self._peek(),
                            "Can't have more than 255 arguments.",
                            Code.LIMIT_EXCEEDED,
                        )

                    if self._match(TokenType.ELLIPSIS):
                        spread = True
                        arguments.append(self._expression())
                        if self._match(TokenType.COMMA):
                            self._error(
                                self._previous(),
                                "Spread argument must be last.",
                                Code.INVALID_DECLARATION,
                            )
                        break

                    arguments.append(self._expression())
                    arg_ends.append(self._previous())

                    if not self._match(TokenType.COMMA):
                        break
                    commas.append(self._previous())
                    if self._check(TokenType.RIGHT_PAREN):
                        break

            paren = self._consume(TokenType.RIGHT_PAREN, "Expect ')' after arguments.")
            return Call(
                callee,
                paren,
                arguments,
                optional,
                spread,
                tuple(commas),
                tuple(arg_ends),
            )

    def _interpolated_string(self, token: Token) -> Expr:
        raw_parts = cast(list[str | list[Token]], token.literal)
        parts: list[str | Expr] = []

        for part in raw_parts:
            if isinstance(part, str):
                parts.append(part)
            else:
                sub_parser = Parser(part, reporter=self.reporter)
                parts.append(sub_parser.parse_expression())

        return InterpolatedString(parts, token)

    def _map_literal(self, brace: Token) -> Expr:
        with self._in_brackets():
            entries: list[tuple[Expr, Expr]] = []

            if not self._check(TokenType.RIGHT_BRACE):
                while True:
                    key = self._expression()
                    self._consume(
                        TokenType.COLON,
                        "Expect ':' between key and value in map literal.",
                    )
                    value = self._expression()
                    entries.append((key, value))

                    if not self._match(TokenType.COMMA):
                        break
                    if self._check(TokenType.RIGHT_BRACE):
                        break

            self._consume(TokenType.RIGHT_BRACE, "Expect '}' after map entries.")
            return MapLiteral(entries, brace, end=self._previous())

    def _primary(self) -> Expr:

        if self._match(TokenType.FN):
            return self._lambda(self._previous())

        if self._match(TokenType.FALSE):
            return Literal(False, self._previous())

        if self._match(TokenType.TRUE):
            return Literal(True, self._previous())

        if self._match(TokenType.NIL):
            return Literal(None, self._previous())

        if self._match(TokenType.INTERPOLATED_STRING):
            return self._interpolated_string(self._previous())

        if self._match(TokenType.NUMBER, TokenType.STRING):
            return Literal(self._previous().literal, self._previous())

        if self._match(TokenType.SUPER):
            keyword = self._previous()
            self._consume(TokenType.DOT, "Expect '.' after 'super'.")
            method = self._consume(TokenType.IDENTIFIER, "Expect superclass method name.")
            return Super(keyword, method)

        if self._match(TokenType.THIS):
            return This(self._previous())

        if self._match(TokenType.IDENTIFIER):
            return Variable(self._previous())

        if self._match(TokenType.LEFT_BRACKET):
            bracket = self._previous()
            with self._in_brackets():
                elements: list[Expr] = []

                if not self._check(TokenType.RIGHT_BRACKET):
                    while True:
                        elements.append(self._expression())

                        if not self._match(TokenType.COMMA):
                            break
                        if self._check(TokenType.RIGHT_BRACKET):
                            break

                self._consume(TokenType.RIGHT_BRACKET, "Expect ']' after list elements.")
                return ListLiteral(elements, bracket, end=self._previous())

        if self._match(TokenType.LEFT_BRACE):
            return self._map_literal(self._previous())

        if self._match(TokenType.MATCH):
            return self._match_expr(self._previous())

        if self._match(TokenType.LEFT_PAREN):
            paren = self._previous()
            with self._in_brackets():
                first: Expr = self._expression()

                if self._match(TokenType.COMMA):
                    elements = [first]
                    while True:
                        elements.append(self._expression())
                        if not self._match(TokenType.COMMA):
                            break
                        if len(elements) >= 2 and self._check(TokenType.RIGHT_PAREN):
                            break

                    self._consume(TokenType.RIGHT_PAREN, "Expect ')' after tuple elements.")
                    return TupleLiteral(elements, paren, end=self._previous())

                self._consume(TokenType.RIGHT_PAREN, "Expect ')' after expression.")
                return Grouping(first, paren, self._previous())

        if self._check(TokenType.SLASH_SLASH):
            raise self._error(
                self._peek(),
                "Expect expression; '//' is integer division, and comments start with '#'.",
            )

        raise self._error(self._peek(), "Expect expression.")

    def _match_expr(self, keyword: Token) -> Expr:
        scrutinee = self._expression()
        self._consume(TokenType.LEFT_BRACE, "Expect '{' after match value.")

        arms: list[MatchArm] = []
        while not self._check(TokenType.RIGHT_BRACE):
            pattern = self._pattern()
            arrow = self._consume(TokenType.FAT_ARROW, "Expect '=>' after match pattern.")
            body = self._expression()
            arms.append(MatchArm(pattern, body, arrow))
            self._match(TokenType.SEMICOLON)
            self._match(TokenType.COMMA)

        end = self._consume(TokenType.RIGHT_BRACE, "Expect '}' after match arms.")
        if not arms:
            raise self._error(keyword, "Match needs at least one arm.", Code.INVALID_MATCH)
        return Match(keyword, scrutinee, arms, end)

    def _pattern(self) -> Pattern:
        if self._match(
            TokenType.NUMBER, TokenType.STRING, TokenType.TRUE, TokenType.FALSE, TokenType.NIL
        ):
            return self._literal_pattern(self._previous())

        if self._match(TokenType.MINUS):
            minus = self._previous()
            number = self._consume(TokenType.NUMBER, "Expect number after '-' in pattern.")
            if not isinstance(number.literal, int):
                raise self._error(
                    number,
                    "Float patterns are not supported; use Int, String, Bool or nil.",
                    Code.INVALID_MATCH,
                )
            return LiteralPattern(minus, -number.literal, end=number)

        token = self._consume(TokenType.IDENTIFIER, "Expect match pattern.")
        if token.lexeme == "_":
            return WildcardPattern(token)

        self._consume(TokenType.DOT, "Expect '.' after enum name in pattern.")
        variant = self._consume(TokenType.IDENTIFIER, "Expect variant name.")
        bindings: list[Token] = []
        if self._match(TokenType.LEFT_PAREN):
            if not self._check(TokenType.RIGHT_PAREN):
                bindings.append(self._consume(TokenType.IDENTIFIER, "Expect binding name."))
                while self._match(TokenType.COMMA):
                    bindings.append(self._consume(TokenType.IDENTIFIER, "Expect binding name."))
            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after pattern bindings.")

        return VariantPattern(token, variant, bindings)

    def _literal_pattern(self, token: Token) -> LiteralPattern:
        if token.type is TokenType.TRUE:
            return LiteralPattern(token, True)
        if token.type is TokenType.FALSE:
            return LiteralPattern(token, False)
        if token.type is TokenType.NIL:
            return LiteralPattern(token, None)
        if isinstance(token.literal, float):
            raise self._error(
                token,
                "Float patterns are not supported; use Int, String, Bool or nil.",
                Code.INVALID_MATCH,
            )
        return LiteralPattern(token, token.literal)

    def _match(self, *types: TokenType) -> bool:
        for token_type in types:
            if self._check(token_type):
                self._advance()
                return True
        return False

    def _match_contextual(self, lexeme: str) -> bool:
        """Consome um identificador que só é especial neste contexto (ex.: `implements`)."""
        if self._check(TokenType.IDENTIFIER) and self._peek().lexeme == lexeme:
            self._advance()
            return True
        return False

    def _match_infix(self, *types: TokenType) -> bool:
        """Consome um operador infixo.

        Fora de brackets ele precisa estar na mesma linha do operando esquerdo (regra
        do `;` opcional, ADR-0011). Dentro de `()`, `[]` e `{}` de expressão a quebra é
        permitida: ali não existe um statement novo para começar (ADR-0067).
        """
        if self._bracket_depth > 0:
            return self._match(*types)

        for token_type in types:
            if self._check(token_type):
                if self._peek().line != self._previous().line:
                    return False
                self._advance()
                return True
        return False

    @contextmanager
    def _in_brackets(self) -> Iterator[None]:
        """Marca que a expressão corrente está dentro de `()`, `[]` ou `{}`."""
        self._bracket_depth += 1
        try:
            yield
        finally:
            self._bracket_depth -= 1

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

    def _error(
        self,
        token: Token,
        message: str,
        code: Code = Code.SYNTAX_UNEXPECTED,
    ) -> ParseError:
        self.reporter.error(token, message, code=code)
        return ParseError(token, message)

    @staticmethod
    def _starts_statement(token: Token) -> bool:
        return token.type is TokenType.IDENTIFIER or token.type in {
            TokenType.IMPORT,
            TokenType.FROM,
            TokenType.CLASS,
            TokenType.INTERFACE,
            TokenType.ENUM,
            TokenType.FN,
            TokenType.VAL,
            TokenType.VAR,
            TokenType.FOR,
            TokenType.IF,
            TokenType.WHILE,
            TokenType.RETURN,
            TokenType.BREAK,
            TokenType.CONTINUE,
            TokenType.TRY,
            TokenType.RAISE,
            TokenType.LEFT_BRACE,
            TokenType.NUMBER,
            TokenType.STRING,
            TokenType.LEFT_PAREN,
            TokenType.LEFT_BRACKET,
            TokenType.THIS,
            TokenType.SUPER,
            TokenType.NOT,
            TokenType.MINUS,
            TokenType.TILDE,
        }

    def _synchronize(self, error_token: Token | None = None) -> None:
        if error_token is not None and error_token is self._peek():
            if error_token.type is TokenType.EOF:
                return
            if error_token.line > self._previous().line and self._starts_statement(error_token):
                # O token que falhou já inicia a próxima linha e pode ser um statement
                # válido (lista/parentese aberta na linha anterior). Não o consuma.
                return
        self._advance()

        while not self._is_at_end():
            if self._previous().type == TokenType.SEMICOLON:
                return

            if self._peek().line > self._previous().line:
                return

            if self._peek().type in {
                TokenType.CLASS,
                TokenType.FN,
                TokenType.VAL,
                TokenType.VAR,
                TokenType.FOR,
                TokenType.IF,
                TokenType.WHILE,
                TokenType.RETURN,
                TokenType.BREAK,
                TokenType.CONTINUE,
            }:
                return

            self._advance()
