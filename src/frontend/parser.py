from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from src.diagnostics.codes import Code
from src.diagnostics.error_reporter import ErrorReporter
from src.diagnostics.errors import ParseError
from src.frontend.destructuring import (
    DestructurePattern,
    NamePattern,
    TuplePattern,
    first_token,
)
from src.frontend.expr import (
    As,
    Assign,
    Binary,
    Call,
    Conditional,
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
from src.frontend.stmt import (
    Block,
    Class,
    Destructure,
    EnumDecl,
    EnumVariant,
    ExceptClause,
    Expression,
    Field,
    ForIn,
    Function,
    If,
    Import,
    ImportName,
    Param,
    Print,
    Raise,
    Return,
    Stmt,
    Try,
    Var,
    While,
)
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token
from src.frontend.ty import (
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

    def parse(self) -> list[Stmt] | None:
        statements: list[Stmt] = []
        while not self._is_at_end():
            declaration = self._declaration()
            if declaration is not None:
                statements.append(declaration)

        return statements

    def parse_expression(self) -> Expr:
        expr = self._expression()
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
        state = self.reporter.mark()

        try:
            expr = self._expression()
            # `;` final é opcional no REPL: `1 + 1;` imprime como `1 + 1`.
            self._match(TokenType.SEMICOLON)

            # Se consumiu a expressão e chegou exatamente ao fim da linha:
            if not self.reporter.had_error and self._is_at_end():
                self.reporter.restore(state)
                # Envelopa como um nó Print para ser avaliado e exibido!
                return [Print(expr)]
        except ParseError:
            pass

        # Rollback: restaura a posição dos tokens e descarta os diagnósticos do teste
        self._current = saved_current
        self.reporter.restore(state)

        # Faz o parse padrão de statements
        return self.parse()

    def _declaration(self) -> Stmt | None:
        try:
            if self._match(TokenType.IMPORT):
                return self._import_declaration(self._previous())
            if self._match(TokenType.FROM):
                return self._from_import_declaration(self._previous())
            if self._match(TokenType.CLASS):
                return self._class_declaration()

            if self._match(TokenType.ENUM):
                return self._enum_declaration()

            if self._match(TokenType.FN):
                if self._check(TokenType.LEFT_PAREN):
                    expression = self._lambda(self._previous())
                    self._end_statement("Expect ';' after expression.")
                    return Expression(expression)

                return self._function("function")

            if self._match(TokenType.VAL):
                return self._var_declaration(mutable=False)

            if self._match(TokenType.VAR):
                return self._var_declaration(mutable=True)

            return self._statement()
        except ParseError:
            self._synchronize()
            return None

    def _module_path(self) -> tuple[Token, ...]:
        path = [self._consume(TokenType.IDENTIFIER, "Expect module name.")]
        while self._match(TokenType.DOT):
            path.append(
                self._consume(TokenType.IDENTIFIER, "Expect name after '.'.")
            )
        return tuple(path)

    def _import_declaration(self, keyword: Token) -> Stmt:
        path = self._module_path()
        alias = None
        if self._match(TokenType.AS):
            alias = self._consume(TokenType.IDENTIFIER, "Expect alias name.")
        self._end_statement("Expect ';' after import.")
        return Import(path=path, alias=alias, from_import=False)

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
        self._end_statement("Expect ';' after import.")
        return Import(path=path, names=tuple(names), from_import=True)

    def _class_declaration(self) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect class name.")
        type_params = self._type_parameters()

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

        self._consume(TokenType.LEFT_BRACE, "Expect '{' before class body.")

        fields: list[Field] = []
        methods: list[Function] = []
        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            if self._match(TokenType.VAL):
                fields.append(self._field_declaration(mutable=False))
            elif self._match(TokenType.VAR):
                fields.append(self._field_declaration(mutable=True))
            else:
                # `fn` é opcional em método: o corpo da classe já marca a declaração.
                self._match(TokenType.FN)
                methods.append(self._function("method"))

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after class body.")

        return Class(name, superclass, fields, methods, type_params)

    def _enum_declaration(self) -> Stmt:
        name = self._consume(TokenType.IDENTIFIER, "Expect enum name.")
        type_params = self._type_parameters()
        self._consume(TokenType.LEFT_BRACE, "Expect '{' before enum variants.")

        variants: list[EnumVariant] = []
        if not self._check(TokenType.RIGHT_BRACE):
            while True:
                variant = self._consume(
                    TokenType.IDENTIFIER, "Expect variant name."
                )
                payload: list[Ty] = []
                if self._match(TokenType.LEFT_PAREN):
                    if not self._check(TokenType.RIGHT_PAREN):
                        payload.append(self._type())
                        while self._match(TokenType.COMMA):
                            payload.append(self._type())
                    self._consume(
                        TokenType.RIGHT_PAREN,
                        "Expect ')' after variant payload.",
                    )

                variants.append(EnumVariant(variant, payload))
                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after enum variants.")
        return EnumDecl(name, type_params, variants)

    def _field_declaration(self, mutable: bool) -> Field:
        name = self._consume(TokenType.IDENTIFIER, "Expect field name.")

        type_annotation: Ty | None = None
        if self._match(TokenType.COLON):
            type_annotation = self._type()

        initializer: Expr | None = None
        if self._match(TokenType.EQUAL):
            initializer = self._expression()
            if not self._is_constant_default(initializer):
                self._error(
                    name,
                    "Field initializer must be a constant.",
                    Code.INVALID_DECLARATION,
                )

        self._end_statement("Expect ';' after field declaration.")

        return Field(name, initializer, mutable, type_annotation)

    def _destructure(self, mutable: bool) -> Stmt:
        pattern = self._destructure_pattern()

        type_annotation: Ty | None = None
        if self._match(TokenType.COLON):
            type_annotation = self._type()

        self._consume(TokenType.EQUAL, "Expect '=' after destructuring pattern.")
        initializer = self._expression()
        self._end_statement("Expect ';' after destructuring.")

        return Destructure(pattern, initializer, mutable, type_annotation)

    def _destructure_pattern(self) -> DestructurePattern:
        if self._match(TokenType.LEFT_PAREN):
            elements = [self._destructure_pattern()]
            while self._match(TokenType.COMMA):
                elements.append(self._destructure_pattern())

            self._consume(
                TokenType.RIGHT_PAREN, "Expect ')' after destructuring pattern."
            )
            if len(elements) < 2:
                raise self._error(
                    first_token(elements[0]),
                    "Destructuring needs at least two elements.",
                    Code.INVALID_DECLARATION,
                )
            return TuplePattern(elements)

        name = self._consume(TokenType.IDENTIFIER, "Expect variable name.")
        return NamePattern(name)

    def _var_declaration(self, mutable: bool) -> Stmt:
        if self._check(TokenType.LEFT_PAREN):
            return self._destructure(mutable)

        name = self._consume(TokenType.IDENTIFIER, "Expect variable name.")

        type_annotation: Ty | None = None
        if self._match(TokenType.COLON):
            type_annotation = self._type()

        initializer: Expr | None = None

        if self._match(TokenType.EQUAL):
            initializer = self._expression()
        elif not mutable:
            raise self._error(
                self._peek(),
                "Expect initializer for 'val' declaration.",
                Code.INVALID_DECLARATION,
            )

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

        if self._match(TokenType.TRY):
            return self._try_statement(self._previous())

        if self._match(TokenType.RAISE):
            return self._raise_statement(self._previous())

        if self._match(TokenType.LEFT_BRACE):
            return Block(self._block())

        return self._expression_statement()

    def _try_statement(self, keyword: Token) -> Stmt:
        self._consume(TokenType.LEFT_BRACE, "Expect '{' after 'try'.")
        body = self._block()

        handlers: list[ExceptClause] = []
        while self._match(TokenType.EXCEPT):
            type_name = self._consume(
                TokenType.IDENTIFIER, "Expect exception type after 'except'."
            )
            self._consume(TokenType.AS, "Expect 'as' after exception type.")
            binding = self._consume(
                TokenType.IDENTIFIER, "Expect binding name after 'as'."
            )
            self._consume(
                TokenType.LEFT_BRACE, "Expect '{' after except binding."
            )
            handlers.append(ExceptClause(type_name, binding, self._block()))

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

        return Try(keyword, body, handlers, finally_body)

    def _raise_statement(self, keyword: Token) -> Stmt:
        value: Expr | None = None
        if not self._check(TokenType.SEMICOLON) and not self._check(
            TokenType.RIGHT_BRACE
        ):
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
        if self._check(TokenType.COLON):
            raise self._error(
                self._peek(),
                "Unexpected ':'. Map literals can't start a statement; "
                "use 'val m = { ... }' or parentheses.",
                Code.INVALID_LITERAL,
            )
        self._end_statement("Expect ';' after expression.")
        return Expression(expr)

    def _end_statement(self, message: str) -> None:
        """Consome o `;` final; no REPL/EOF, no fim da linha ou antes de `}` ele é opcional."""
        if self._match(TokenType.SEMICOLON):
            return

        if self._repl and self._is_at_end():
            return

        if self._is_at_end():
            return

        # `}` nunca continua uma expressão: fechar o bloco/pai termina o statement
        # (permite `if (ok) { print 1 }` na mesma linha).
        if self._check(TokenType.RIGHT_BRACE):
            return

        if self._peek().line > self._previous().line:
            return

        raise self._error(self._peek(), message)

    def _function(self, kind: str) -> Function:
        name = self._consume(TokenType.IDENTIFIER, f"Expect {kind} name.")
        type_params = self._type_parameters()
        self._consume(TokenType.LEFT_PAREN, f"Expect '(' after {kind} name.")
        parameters = self._parameters()

        return_type: Ty | None = None
        if self._match(TokenType.ARROW):
            return_type = self._type()

        self._consume(TokenType.LEFT_BRACE, f"Expect '{{' before {kind} body.")

        body = self._block()
        return Function(name, parameters, body, return_type, type_params)

    def _type_parameters(self) -> list[Token]:
        if not self._match(TokenType.LEFT_BRACKET):
            return []

        parameters = [self._consume(TokenType.IDENTIFIER, "Expect type parameter name.")]
        while self._match(TokenType.COMMA):
            parameters.append(
                self._consume(TokenType.IDENTIFIER, "Expect type parameter name.")
            )

        self._consume(
            TokenType.RIGHT_BRACKET, "Expect ']' after type parameters."
        )
        return parameters

    def _parameters(self) -> list[Param]:
        parameters: list[Param] = []
        seen_default = False
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                if len(parameters) >= 255:
                    self._error(
                        self._peek(),
                        "Can't have more than 255 parameters.",
                        Code.LIMIT_EXCEEDED,
                    )

                mutable = self._match(TokenType.VAR)
                name_token = self._consume(
                    TokenType.IDENTIFIER, "Expect parameter name."
                )

                type_annotation: Ty | None = None
                if self._match(TokenType.COLON):
                    type_annotation = self._type()

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
                elif seen_default:
                    self._error(
                        name_token,
                        "Required parameter can't follow an optional parameter.",
                        Code.INVALID_DECLARATION,
                    )

                parameters.append(Param(name_token, mutable, default, type_annotation))

                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RIGHT_PAREN, "Expect ')' after parameters.")
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
        if self._match(TokenType.ARROW):
            return_type = self._type()

        body: list[Stmt]
        if self._match(TokenType.FAT_ARROW):
            arrow = self._previous()
            expression = self._expression()
            body = [Return(arrow, expression)]
        elif self._match(TokenType.LEFT_BRACE):
            body = self._block()
        else:
            raise self._error(
                self._peek(), "Expect '=>' or '{' after lambda parameters."
            )

        return Lambda(keyword, parameters, body, return_type)

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

                self._consume(
                    TokenType.RIGHT_PAREN, "Expect ')' after tuple type."
                )
                return TupleTy(tuple(items))

            self._consume(TokenType.RIGHT_PAREN, "Expect ')' after type.")
            return first

        token = self._consume(TokenType.IDENTIFIER, "Expect type name.")
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

        return ClassTy(name)

    def _function_type(self) -> Ty:
        self._consume(
            TokenType.LEFT_PAREN, "Expect '(' after 'fn' in function type."
        )
        params: list[Ty] = []
        if not self._check(TokenType.RIGHT_PAREN):
            params.append(self._type())
            while self._match(TokenType.COMMA):
                params.append(self._type())

        self._consume(
            TokenType.RIGHT_PAREN, "Expect ')' after function type parameters."
        )
        self._consume(
            TokenType.ARROW, "Expect '->' after function type parameters."
        )
        ret = self._type()
        return FnTy(tuple(params), ret, len(params))

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
            return ClassTy(name, tuple(arguments))

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
                return IndexSet(expr.object, expr.index, value, expr.bracket)

            self._error(
                equals, "Invalid assignment target.", Code.INVALID_ASSIGNMENT_TARGET
            )

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
            self._consume(
                TokenType.ELSE, "Expect 'else' after conditional expression."
            )
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
                test_type = self._type(allow_union=False)
                if self._check(TokenType.PIPE):
                    raise self._error(
                        self._peek(),
                        "Type unions in 'is' need parentheses: 'is (A | B)'.",
                        Code.INVALID_TYPE_ANNOTATION,
                    )
                expr = Is(expr, test_type, operator)
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

        while self._match_infix(TokenType.DOT_DOT):
            operator: Token = self._previous()
            end: Expr = self._shift()
            expr = Range(expr, end, operator)

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
            target = self._type()
            expr = As(expr, target, operator)

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
            if (
                self._check(TokenType.LEFT_PAREN)
                and self._peek().line == self._previous().line
            ):
                self._advance()
                expr = self._finish_call(expr, optional=optional_call)
                optional_call = False
            elif self._match(TokenType.QUESTION_DOT):
                name = self._consume(
                    TokenType.IDENTIFIER, "Expect property name after '?.'."
                )
                expr = Get(expr, name, optional=True)
                optional_call = True
            elif self._match(TokenType.DOT):
                name = self._consume(
                    TokenType.IDENTIFIER, "Expect property name after '.'."
                )
                expr = Get(expr, name)
                optional_call = False
            elif (
                self._check(TokenType.LEFT_BRACKET)
                and self._peek().line == self._previous().line
            ):
                bracket = self._advance()
                with self._in_brackets():
                    if self._check(TokenType.RIGHT_BRACKET):
                        raise self._error(
                            self._peek(), "Expect index expression."
                        )

                    index = self._expression()
                    self._consume(
                        TokenType.RIGHT_BRACKET, "Expect ']' after index."
                    )
                    expr = Index(expr, index, bracket)
                optional_call = False
            else:
                break

        return expr

    def _finish_call(self, callee: Expr, *, optional: bool = False) -> Expr:
        with self._in_brackets():
            arguments: list[Expr] = []
            if not self._check(TokenType.RIGHT_PAREN):
                while True:
                    if len(arguments) >= 255:
                        self._error(
                            self._peek(),
                            "Can't have more than 255 arguments.",
                            Code.LIMIT_EXCEEDED,
                        )

                    arguments.append(self._expression())

                    if not self._match(TokenType.COMMA):
                        break

            paren = self._consume(
                TokenType.RIGHT_PAREN, "Expect ')' after arguments."
            )
            return Call(callee, paren, arguments, optional)

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

            self._consume(TokenType.RIGHT_BRACE, "Expect '}' after map entries.")
            return MapLiteral(entries, brace)

    def _primary(self) -> Expr:

        if self._match(TokenType.FN):
            return self._lambda(self._previous())

        if self._match(TokenType.FALSE):
            return Literal(False)

        if self._match(TokenType.TRUE):
            return Literal(True)

        if self._match(TokenType.NIL):
            return Literal(None)

        if self._match(TokenType.INTERPOLATED_STRING):
            return self._interpolated_string(self._previous())

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

        if self._match(TokenType.LEFT_BRACKET):
            bracket = self._previous()
            with self._in_brackets():
                elements: list[Expr] = []

                if not self._check(TokenType.RIGHT_BRACKET):
                    while True:
                        elements.append(self._expression())

                        if not self._match(TokenType.COMMA):
                            break

                self._consume(
                    TokenType.RIGHT_BRACKET, "Expect ']' after list elements."
                )
                return ListLiteral(elements, bracket)

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

                    self._consume(
                        TokenType.RIGHT_PAREN, "Expect ')' after tuple elements."
                    )
                    return TupleLiteral(elements, paren)

                self._consume(
                    TokenType.RIGHT_PAREN, "Expect ')' after expression."
                )
                return Grouping(first)

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
            self._consume(TokenType.FAT_ARROW, "Expect '=>' after match pattern.")
            body = self._expression()
            arms.append(MatchArm(pattern, body))
            self._match(TokenType.SEMICOLON)
            self._match(TokenType.COMMA)

        self._consume(TokenType.RIGHT_BRACE, "Expect '}' after match arms.")
        if not arms:
            raise self._error(
                keyword, "Match needs at least one arm.", Code.INVALID_MATCH
            )
        return Match(keyword, scrutinee, arms)

    def _pattern(self) -> Pattern:
        token = self._consume(TokenType.IDENTIFIER, "Expect match pattern.")
        if token.lexeme == "_":
            return WildcardPattern(token)

        self._consume(TokenType.DOT, "Expect '.' after enum name in pattern.")
        variant = self._consume(TokenType.IDENTIFIER, "Expect variant name.")
        bindings: list[Token] = []
        if self._match(TokenType.LEFT_PAREN):
            if not self._check(TokenType.RIGHT_PAREN):
                bindings.append(
                    self._consume(TokenType.IDENTIFIER, "Expect binding name.")
                )
                while self._match(TokenType.COMMA):
                    bindings.append(
                        self._consume(TokenType.IDENTIFIER, "Expect binding name.")
                    )
            self._consume(
                TokenType.RIGHT_PAREN, "Expect ')' after pattern bindings."
            )

        return VariantPattern(token, variant, bindings)

    def _match(self, *types: TokenType) -> bool:
        for token_type in types:
            if self._check(token_type):
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
