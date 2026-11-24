# SPDX-License-Identifier: MIT OR Apache-2.0
"""Printer AST → Doc: layout, comentários e política de linhas em branco (ADR-0136).

O printer anda pela fonte em ordem de offset. Cada token real passa por `_token`, que
consome a trivia anterior, separa comentário trailing de leading e só então emite o
lexeme; assim nenhum comentário é perdido e o texto de literais/identificadores nunca é
re-normalizado. A decisão de quebra fica nos `Group`s do Doc IR; aqui só se escolhe onde
há grupo, indentação e vírgula condicional.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from loxia.formatter.comments import Gap, comment_text, split_gap
from loxia.formatter.doc import (
    Doc,
    TrailingComment,
    align,
    blankline,
    concat,
    ensure_line,
    group,
    hardline,
    if_break,
    indent,
    line,
    render,
    softline,
    text,
)
from loxia_core.diagnostics.diagnostic import Span
from loxia_core.frontend.destructuring import NamePattern, TuplePattern
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
from loxia_core.frontend.stmt import (
    Block,
    Class,
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
from loxia_core.frontend.trivia import Trivia, TriviaKind
from loxia_core.frontend.ty import Ty, display

type DocBuilder = Callable[[], Doc]


class ItemKind(StrEnum):
    TOP = "top"
    TOP_STMT = "top_stmt"
    IMPORT = "import"
    FIELD = "field"
    METHOD = "method"
    ENUM_VARIANT = "enum_variant"
    MATCH_ARM = "match_arm"
    STMT = "stmt"


type Policy = Callable[[int, ItemKind, ItemKind | None, int, int | None, int | None], int]


@dataclass(frozen=True)
class _Entry:
    start: int
    kind: ItemKind
    build: DocBuilder
    group: int | None = None


def _file_policy(
    index: int,
    kind: ItemKind,
    previous: ItemKind | None,
    user_blank: int,
    group: int | None,
    previous_group: int | None,
) -> int:
    if index == 0:
        return 0
    if kind is ItemKind.IMPORT:
        if previous is ItemKind.IMPORT:
            return 0 if group == previous_group else 1
        return 1
    if previous is ItemKind.IMPORT:
        return 1
    if kind is ItemKind.TOP or previous is ItemKind.TOP:
        return 1
    return min(user_blank, 1)


def _class_policy(
    index: int,
    kind: ItemKind,
    previous: ItemKind | None,
    user_blank: int,
    group: int | None,
    previous_group: int | None,
) -> int:
    if index == 0:
        return 0
    if kind is ItemKind.METHOD or previous is ItemKind.METHOD:
        return 1
    return min(user_blank, 1)


def _interface_policy(
    index: int,
    kind: ItemKind,
    previous: ItemKind | None,
    user_blank: int,
    group: int | None,
    previous_group: int | None,
) -> int:
    return 0 if index == 0 else 1


def _stmt_policy(
    index: int,
    kind: ItemKind,
    previous: ItemKind | None,
    user_blank: int,
    group: int | None,
    previous_group: int | None,
) -> int:
    return 0 if index == 0 else min(user_blank, 1)


def _enum_policy(
    index: int,
    kind: ItemKind,
    previous: ItemKind | None,
    user_blank: int,
    group: int | None,
    previous_group: int | None,
) -> int:
    return 0


def _operator_precedence(token: TokenType) -> int:
    if token in (TokenType.PLUS, TokenType.MINUS):
        return 10
    if token in (TokenType.STAR, TokenType.SLASH, TokenType.SLASH_SLASH, TokenType.PERCENT):
        return 11
    if token in (TokenType.LESS, TokenType.LESS_EQUAL, TokenType.GREATER, TokenType.GREATER_EQUAL):
        return 6
    if token in (TokenType.EQUAL_EQUAL, TokenType.NOT_EQUAL):
        return 5
    if token is TokenType.PIPE:
        return 4
    if token is TokenType.CARET:
        return 3
    if token is TokenType.AMPERSAND:
        return 2
    if token in (TokenType.LESS_LESS, TokenType.GREATER_GREATER, TokenType.GREATER_GREATER_GREATER):
        return 12
    return 0


class Printer:
    def __init__(
        self,
        *,
        source: str,
        trivia: Sequence[Trivia],
        width: int = 100,
    ) -> None:
        self.source_bytes = source.encode("utf-8")
        self.trivia = list(trivia)
        self.trivia_index = 0
        self.width = width
        self.last_token_line = 0
        self.last_token_end = 0
        self._starts: dict[object, int] = {}

    # --- entrada ---------------------------------------------------------

    def format(self, statements: list[Stmt]) -> str:
        body = self._file(statements)
        rendered = render(body, self.width)
        lines = align(rendered, self.width)
        value = "\n".join(lines)
        return value + "\n" if value else ""

    def _file(self, statements: list[Stmt]) -> Doc:
        parts: list[Doc] = []
        previous: ItemKind | None = None
        previous_group: int | None = None
        for index, statement in enumerate(statements):
            start = self._start(statement)
            gap = self._take(start)
            kind = self._file_kind(statement)
            group = self._import_group(statement)
            parts.append(
                self._item_prefix(
                    index,
                    gap,
                    kind,
                    previous,
                    _file_policy,
                    first_hardline=False,
                    group=group,
                    previous_group=previous_group,
                )
            )
            parts.append(self._stmt(statement))
            previous = kind
            previous_group = group
        closing = self._finish_gap(
            len(self.source_bytes), had_items=bool(statements), first_hardline=False
        )
        if closing is not None:
            parts.append(closing)
        return concat(*parts)

    # --- cursor de trivia ------------------------------------------------

    def _take(self, offset: int) -> Gap:
        items: list[Trivia] = []
        while self.trivia_index < len(self.trivia):
            item = self.trivia[self.trivia_index]
            if item.end > offset:
                break
            items.append(item)
            self.trivia_index += 1
        return split_gap(
            items,
            previous_end=self.last_token_end,
            previous_line=self.last_token_line,
            offset=offset,
        )

    def _skip_to(self, offset: int, line: int) -> None:
        while self.trivia_index < len(self.trivia):
            if self.trivia[self.trivia_index].end > offset:
                break
            self.trivia_index += 1
        self.last_token_end = offset
        self.last_token_line = line

    def _mark(self, token: Token | None) -> None:
        if token is None or token.offset is None:
            return
        self.last_token_end = token.offset + len(token.lexeme.encode("utf-8"))
        self.last_token_line = token.line + token.lexeme.count("\n")

    def _mark_close(self, token: Token | None, offset: int) -> None:
        if token is None:
            return
        self._mark(token)

    def _deferred[T](self, node: T, build: Callable[[T], Doc]) -> DocBuilder:
        def run() -> Doc:
            return build(node)

        return run

    # --- comentários -----------------------------------------------------

    def _trailing(self, comments: Sequence[Trivia]) -> Doc:
        docs: list[Doc] = []
        for item in comments:
            hard = item.kind is not TriviaKind.BLOCK_COMMENT or "\n" in item.text
            docs.append(TrailingComment(comment_text(item), hard=hard))
        return concat(*docs)

    def _leading(
        self,
        comments: Sequence[Trivia],
        blanks_between: Sequence[int],
        *,
        preserve_blank: bool = True,
        blank_after: int = 0,
    ) -> Doc:
        parts: list[Doc] = []
        for index, item in enumerate(comments):
            if index and preserve_blank and blanks_between[index - 1] >= 1:
                parts.append(blankline())
            parts.append(ensure_line())
            parts.append(text(comment_text(item)))
            parts.append(hardline())
        if blank_after and preserve_blank:
            parts.append(blankline())
        return concat(*parts)

    def _closer_gap(self, close: Token | None) -> Doc | None:
        if close is None or close.offset is None:
            return None
        gap = self._take(close.offset)
        parts: list[Doc] = []
        if gap.trailing:
            parts.append(self._trailing(gap.trailing))
        if gap.leading:
            parts.append(hardline())
            parts.append(self._leading(gap.leading, gap.blanks_between, preserve_blank=False))
        return concat(*parts) if parts else None

    def _before_line(self, offset: int) -> Doc:
        gap = self._take(offset)
        parts: list[Doc] = []
        if gap.trailing:
            parts.append(self._trailing(gap.trailing))
        parts.append(line())
        if gap.leading:
            parts.append(self._leading(gap.leading, gap.blanks_between, preserve_blank=False))
        return concat(*parts)

    def _value_after(self, offset: int, value: Doc) -> Doc:
        gap = self._take(offset)
        if not gap.trailing and not gap.leading:
            return concat(text(" "), value)
        parts: list[Doc] = []
        if gap.trailing:
            parts.append(self._trailing(gap.trailing))
            parts.append(hardline())
        if gap.leading:
            parts.append(self._leading(gap.leading, gap.blanks_between, preserve_blank=False))
        parts.append(value)
        return indent(concat(*parts))

    # --- itens e blocos --------------------------------------------------

    def _item_prefix(
        self,
        index: int,
        gap: Gap,
        kind: ItemKind,
        previous: ItemKind | None,
        policy: Policy,
        *,
        first_hardline: bool,
        group: int | None = None,
        previous_group: int | None = None,
    ) -> Doc:
        parts: list[Doc] = []
        if gap.trailing:
            parts.append(self._trailing(gap.trailing))
        if index > 0 or first_hardline:
            parts.append(hardline())
        if index > 0:
            blanks = policy(index, kind, previous, gap.blank_before, group, previous_group)
            if blanks:
                parts.append(blankline())
        if gap.leading:
            parts.append(self._leading(gap.leading, gap.blanks_between, preserve_blank=True))
            if gap.blank_after:
                parts.append(blankline())
        return concat(*parts)

    def _finish_gap(self, offset: int, *, had_items: bool, first_hardline: bool) -> Doc | None:
        gap = self._take(offset)
        parts: list[Doc] = []
        if gap.trailing:
            parts.append(self._trailing(gap.trailing))
        if had_items or (first_hardline and gap.leading):
            parts.append(hardline())
        if gap.leading:
            if had_items and gap.blank_before:
                parts.append(blankline())
            parts.append(self._leading(gap.leading, gap.blanks_between, preserve_blank=True))
        return concat(*parts) if parts else None

    def _body(self, entries: Sequence[_Entry], end_offset: int, policy: Policy) -> Doc | None:
        parts: list[Doc] = []
        previous: ItemKind | None = None
        for index, entry in enumerate(entries):
            gap = self._take(entry.start)
            parts.append(
                self._item_prefix(
                    index,
                    gap,
                    entry.kind,
                    previous,
                    policy,
                    first_hardline=True,
                    group=entry.group,
                )
            )
            parts.append(entry.build())
            previous = entry.kind
        closing = self._finish_gap(end_offset, had_items=bool(entries), first_hardline=True)
        if closing is not None:
            parts.append(closing)
        if not entries and closing is None:
            return None
        return concat(*parts)

    def _braced(self, body: Doc | None, close: Token | None, *, leading_space: bool = True) -> Doc:
        offset = self._close_offset(close)
        prefix = text(" {") if leading_space else text("{")
        if body is None:
            self._mark_close(close, offset)
            return concat(prefix, text("}"))
        value = concat(prefix, indent(body), softline(), text("}"))
        self._mark_close(close, offset)
        return value

    def _block_config(
        self, statements: Sequence[Stmt], close: Token | None, policy: Policy
    ) -> Doc | None:
        return self._block_config_at(statements, self._close_offset(close), policy)

    def _block_config_at(
        self, statements: Sequence[Stmt], end_offset: int, policy: Policy
    ) -> Doc | None:
        entries = [
            _Entry(
                start=self._start(statement),
                kind=ItemKind.STMT,
                build=self._deferred(statement, self._stmt),
            )
            for statement in statements
        ]
        return self._body(entries, end_offset, policy)

    def _block(self, statement: Block) -> Doc | None:
        return self._block_config(statement.statements, statement.end, _stmt_policy)

    # --- delimitados (calls, listas, mapas, tuplas, params, enums) --------

    def _delimited(
        self,
        opener: Doc,
        entries: Sequence[tuple[int, DocBuilder]],
        close: Token | None,
        close_text: str,
        *,
        trailing_comma: bool,
        spaced: bool,
    ) -> Doc:
        if not entries:
            return self._empty_delimited(opener, close, close_text)
        parts: list[Doc] = [opener]
        first_start, first_build = entries[0]
        first_gap = self._take(first_start)
        if first_gap.trailing:
            parts.append(self._trailing(first_gap.trailing))
        inner: list[Doc] = [line() if spaced else softline()]
        if first_gap.leading:
            inner.append(self._leading(first_gap.leading, first_gap.blanks_between))
        inner.append(first_build())
        for start, build in entries[1:]:
            inner.append(text(","))
            gap = self._take(start)
            if gap.trailing:
                inner.append(self._trailing(gap.trailing))
            inner.append(line())
            if gap.leading:
                inner.append(self._leading(gap.leading, gap.blanks_between))
            inner.append(build())
        if trailing_comma:
            inner.append(if_break(text(","), text("")))
        closer = self._closer_gap(close)
        if closer is not None:
            inner.append(closer)
        parts.append(indent(concat(*inner)))
        parts.append(line() if spaced else softline())
        parts.append(text(close_text))
        self._mark_close(close, self._close_offset(close))
        return group(concat(*parts))

    def _empty_delimited(self, opener: Doc, close: Token | None, close_text: str) -> Doc:
        offset = self._close_offset(close)
        gap = self._take(offset) if close is not None and close.offset is not None else Gap()
        parts: list[Doc] = [opener]
        if gap.trailing:
            parts.append(self._trailing(gap.trailing))
        if gap.leading:
            parts.append(indent(concat(hardline(), self._leading(gap.leading, gap.blanks_between))))
        parts.append(softline())
        parts.append(text(close_text))
        self._mark_close(close, offset)
        return group(concat(*parts))

    # --- spans e tipos ---------------------------------------------------

    def _close_offset(self, token: Token | None) -> int:
        if token is not None and token.offset is not None:
            return token.offset
        return len(self.source_bytes)

    def _token_offset(self, token: Token | None) -> int:
        if token is None or token.offset is None:
            return 0
        return token.offset

    def _start(self, node: object) -> int:
        cached = self._starts.get(node)
        if cached is not None:
            return cached
        offset = self._token_offset(self._first_token(node))
        self._starts[node] = offset
        return offset

    def _first_token(self, node: object) -> Token | None:
        """Primeiro token do nó, na ordem em que o printer o consome.

        Substitui o `SourceIndex` completo: o printer só precisa do offset de início,
        então uma caminhada memoizada pelos campos evita indexar ends/merges de toda a
        AST. A ordem imita a que o índice produzia para não mudar bytes.
        """
        if isinstance(node, Token):
            return node
        if isinstance(node, Expression):
            return self._first_token(node.expression)
        if isinstance(node, If):
            return node.keyword or self._first_token(node.condition)
        if isinstance(node, While):
            return node.keyword or self._first_token(node.condition)
        if isinstance(node, ForIn):
            return node.keyword or node.name
        if isinstance(node, Block):
            if node.start is not None:
                return node.start
            return self._first_token(node.statements[0]) if node.statements else None
        if isinstance(node, Return):
            return node.keyword
        if isinstance(node, Raise):
            return node.keyword
        if isinstance(node, Try):
            return node.keyword
        if isinstance(node, ErrorStmt):
            return node.start
        if isinstance(node, ErrorExpr):
            return node.start
        if isinstance(node, Class):
            return node.keyword or node.name
        if isinstance(node, Interface):
            return node.keyword or node.name
        if isinstance(node, EnumDecl):
            return node.keyword or node.name
        if isinstance(node, TypeAlias):
            return node.keyword or node.name
        if isinstance(node, Import):
            return node.start or (node.path[0] if node.path else None)
        if isinstance(node, Function):
            return node.fn_token or node.name
        if isinstance(node, Field):
            return node.keyword or node.name
        if isinstance(node, Var):
            return node.keyword or node.name
        if isinstance(node, Destructure):
            return node.keyword or self._destructure_first(node.pattern)
        if isinstance(node, Param):
            return node.name
        if isinstance(node, EnumVariant):
            return node.name
        if isinstance(node, ImportName):
            return node.name
        if isinstance(node, ExceptClause):
            return node.keyword or node.type_name
        if isinstance(node, MatchArm):
            return self._first_token(node.pattern)
        if isinstance(node, VariantPattern):
            return node.enum
        if isinstance(node, WildcardPattern):
            return node.token
        if isinstance(node, Grouping):
            return node.start or self._first_token(node.expression)
        if isinstance(node, Literal):
            return node.token
        if isinstance(node, InterpolatedString):
            return node.token
        if isinstance(node, Conditional):
            return self._first_token(node.then_branch)
        if isinstance(node, Lambda):
            return node.keyword
        if isinstance(node, Match):
            return node.keyword
        if isinstance(node, ListLiteral):
            return node.bracket
        if isinstance(node, MapLiteral):
            return node.brace
        if isinstance(node, TupleLiteral):
            return node.paren
        if isinstance(node, Call):
            return self._first_token(node.callee)
        if isinstance(node, (Get, Set, Index, IndexSet)):
            return self._first_token(node.object)
        if isinstance(node, Assign):
            return node.name
        if isinstance(node, Unary):
            return node.operator
        if isinstance(node, (Binary, Logical, Is, As)):
            return self._first_token(node.left)
        if isinstance(node, Range):
            return self._first_token(node.start)
        if isinstance(node, Variable):
            return node.name
        if isinstance(node, This):
            return node.keyword
        if isinstance(node, Super):
            return node.keyword
        return None

    def _destructure_first(self, pattern: NamePattern | TuplePattern) -> Token | None:
        if isinstance(pattern, NamePattern):
            return pattern.name
        return self._destructure_first(pattern.elements[0])

    def _pattern_start(self, pattern: Pattern) -> int:
        if isinstance(pattern, VariantPattern):
            return self._token_offset(pattern.enum)
        return self._token_offset(pattern.token)

    def _type_after(self, ty: Ty, span: Span | None, *, leading_space: bool = True) -> Doc:
        """Tipo anotado a partir do span, preservando comentários que vêm antes dele."""
        if span is None or span.start.offset is None or span.end.offset is None:
            prefix = " " if leading_space else ""
            return text(prefix + display(ty))
        gap = self._take(span.start.offset)
        value = self.source_bytes[span.start.offset : span.end.offset].decode("utf-8")
        self._skip_to(span.end.offset, span.end.line)
        if gap.empty:
            return text((" " if leading_space else "") + value)
        inner: list[Doc] = []
        if gap.trailing:
            inner.append(self._trailing(gap.trailing))
            inner.append(hardline())
        if gap.leading:
            inner.append(self._leading(gap.leading, gap.blanks_between))
        inner.append(text(value))
        return indent(concat(*inner))

    def _file_kind(self, statement: Stmt) -> ItemKind:
        if isinstance(statement, Import):
            return ItemKind.IMPORT
        if isinstance(statement, (Class, Function, Interface, EnumDecl, TypeAlias)):
            return ItemKind.TOP
        return ItemKind.TOP_STMT

    def _import_group(self, statement: Stmt) -> int | None:
        if not isinstance(statement, Import) or not statement.path:
            return None
        return 1 if statement.path[0].lexeme == "std" else 0

    # --- tokens ----------------------------------------------------------

    def _token(self, token: Token, *, space_before: bool = False) -> Doc:
        if token.offset is None:
            return text(token.lexeme)
        gap = self._take(token.offset)
        parts: list[Doc] = []
        if gap.trailing:
            parts.append(self._trailing(gap.trailing))
            parts.append(hardline())
        elif not gap.leading and space_before:
            parts.append(text(" "))
        if gap.leading:
            parts.append(self._leading(gap.leading, gap.blanks_between))
        parts.append(text(token.lexeme))
        self._mark(token)
        return concat(*parts)

    # --- expressões ------------------------------------------------------

    def _expr(self, expr: Expr) -> Doc:
        if isinstance(expr, Literal):
            return self._literal(expr)
        if isinstance(expr, Variable):
            return self._token(expr.name)
        if isinstance(expr, Binary):
            return self._binary(expr)
        if isinstance(expr, Logical):
            return self._logical(expr)
        if isinstance(expr, Range):
            return concat(self._expr(expr.start), self._token(expr.operator), self._expr(expr.end))
        if isinstance(expr, Grouping):
            start = self._token(expr.start) if expr.start is not None else text("(")
            inner = self._expr(expr.expression)
            end = self._token(expr.end) if expr.end is not None else text(")")
            return concat(start, inner, end)
        if isinstance(expr, Unary):
            operator = self._token(expr.operator)
            if expr.operator.lexeme == "not":
                return concat(operator, text(" "), self._expr(expr.right))
            return concat(operator, self._expr(expr.right))
        if isinstance(expr, Is):
            return self._type_operator(
                self._expr(expr.left), expr.operator, expr.test_type, expr.type_span
            )
        if isinstance(expr, As):
            return self._type_operator(
                self._expr(expr.left), expr.operator, expr.target_type, expr.type_span
            )
        if isinstance(expr, Call):
            return self._call(expr)
        if isinstance(expr, Conditional):
            return self._conditional(expr)
        if isinstance(expr, Assign):
            return concat(
                self._token(expr.name),
                text(" ="),
                self._value_after(self._start(expr.value), self._expr(expr.value)),
            )
        if isinstance(expr, Get):
            return concat(
                self._expr(expr.object),
                text("?." if expr.optional else "."),
                self._token(expr.name),
            )
        if isinstance(expr, Set):
            return concat(
                self._expr(expr.object),
                text("."),
                self._token(expr.name),
                text(" ="),
                self._value_after(self._start(expr.value), self._expr(expr.value)),
            )
        if isinstance(expr, Super):
            return concat(self._token(expr.keyword), text("."), self._token(expr.method))
        if isinstance(expr, This):
            return self._token(expr.keyword)
        if isinstance(expr, InterpolatedString):
            return self._token(expr.token)
        if isinstance(expr, ListLiteral):
            return self._list(expr)
        if isinstance(expr, MapLiteral):
            return self._map(expr)
        if isinstance(expr, TupleLiteral):
            return self._tuple(expr)
        if isinstance(expr, Index):
            object_doc = self._expr(expr.object)
            bracket = self._token(expr.bracket)
            index_doc = self._expr(expr.index)
            end = self._token(expr.end) if expr.end is not None else text("]")
            return concat(object_doc, bracket, index_doc, end)
        if isinstance(expr, IndexSet):
            object_doc = self._expr(expr.object)
            bracket = self._token(expr.bracket)
            index_doc = self._expr(expr.index)
            end = self._token(expr.end) if expr.end is not None else text("]")
            return concat(
                object_doc,
                bracket,
                index_doc,
                end,
                text(" ="),
                self._value_after(self._start(expr.value), self._expr(expr.value)),
            )
        if isinstance(expr, Match):
            return self._match(expr)
        if isinstance(expr, Lambda):
            return self._lambda(expr)
        if isinstance(expr, ErrorExpr):
            return self._token(expr.start)
        return text("")

    def _literal(self, expr: Literal) -> Doc:
        if expr.token is not None:
            return self._token(expr.token)
        value = expr.value
        if value is None:
            return text("nil")
        if value is True:
            return text("true")
        if value is False:
            return text("false")
        return text(str(value))

    def _type_operator(self, left: Doc, operator: Token, ty: Ty, span: Span | None) -> Doc:
        op_doc = self._token(operator)
        return group(concat(left, text(" "), op_doc, self._type_after(ty, span)))

    def _binary(self, expr: Binary) -> Doc:
        if expr.operator.type is TokenType.STAR_STAR:
            return concat(
                self._expr(expr.left),
                text(" "),
                self._token(expr.operator),
                text(" "),
                self._expr(expr.right),
            )
        operands, operators = self._flatten_binary(expr)
        return self._chain(operands, operators)

    def _flatten_binary(self, expr: Binary) -> tuple[list[Expr], list[Token]]:
        precedence = _operator_precedence(expr.operator.type)
        operands: list[Expr] = [expr.right]
        operators: list[Token] = [expr.operator]
        current: Expr = expr.left
        while (
            isinstance(current, Binary)
            and _operator_precedence(current.operator.type) == precedence
        ):
            operands.append(current.right)
            operators.append(current.operator)
            current = current.left
        operands.append(current)
        operands.reverse()
        operators.reverse()
        return operands, operators

    def _logical(self, expr: Logical) -> Doc:
        operands: list[Expr] = [expr.right]
        operators: list[Token] = [expr.operator]
        current: Expr = expr.left
        while isinstance(current, Logical) and current.operator.type is expr.operator.type:
            operands.append(current.right)
            operators.append(current.operator)
            current = current.left
        operands.append(current)
        operands.reverse()
        operators.reverse()
        return self._chain(operands, operators)

    def _chain(self, operands: Sequence[Expr], operators: Sequence[Token]) -> Doc:
        # A ordem de construção importa: `_expr` consome trivia, então o primeiro
        # operando precisa ser emitido antes de qualquer lookahead do resto.
        first = self._expr(operands[0])
        rest: list[Doc] = []
        for operator, operand in zip(operators, operands[1:], strict=True):
            rest.append(text(" "))
            rest.append(self._token(operator))
            rest.append(self._before_line(self._start(operand)))
            rest.append(self._expr(operand))
        return group(concat(first, indent(concat(*rest))))

    def _call(self, expr: Call) -> Doc:
        opener = concat(self._expr(expr.callee), text("("))
        if expr.spread and expr.arguments:
            *rest, last = expr.arguments
            entries = [
                (self._start(argument), self._deferred(argument, self._expr)) for argument in rest
            ]
            entries.append((self._start(last), self._deferred(last, self._spread)))
        else:
            entries = [
                (self._start(argument), self._deferred(argument, self._expr))
                for argument in expr.arguments
            ]
        return self._delimited(
            opener,
            entries,
            expr.paren,
            ")",
            trailing_comma=not expr.spread,
            spaced=False,
        )

    def _spread(self, argument: Expr) -> Doc:
        return concat(text("..."), self._expr(argument))

    def _list(self, expr: ListLiteral) -> Doc:
        entries = [
            (self._start(element), self._deferred(element, self._expr)) for element in expr.elements
        ]
        return self._delimited(text("["), entries, expr.end, "]", trailing_comma=True, spaced=False)

    def _tuple(self, expr: TupleLiteral) -> Doc:
        entries = [
            (self._start(element), self._deferred(element, self._expr)) for element in expr.elements
        ]
        return self._delimited(text("("), entries, expr.end, ")", trailing_comma=True, spaced=False)

    def _map(self, expr: MapLiteral) -> Doc:
        entries = [
            (self._start(key), self._deferred((key, value), self._map_pair))
            for key, value in expr.entries
        ]
        return self._delimited(text("{"), entries, expr.end, "}", trailing_comma=True, spaced=True)

    def _map_pair(self, entry: tuple[Expr, Expr]) -> Doc:
        return self._map_entry(entry[0], entry[1])

    def _map_entry(self, key: Expr, value: Expr) -> Doc:
        key_doc = self._expr(key)
        gap = self._take(self._start(value))
        inner: list[Doc] = []
        if gap.trailing:
            inner.append(self._trailing(gap.trailing))
        inner.append(line())
        if gap.leading:
            inner.append(self._leading(gap.leading, gap.blanks_between))
        inner.append(self._expr(value))
        return group(concat(key_doc, text(":"), indent(concat(*inner))))

    def _conditional(self, expr: Conditional) -> Doc:
        then_doc = self._expr(expr.then_branch)
        cond_gap = self._take(self._start(expr.condition))
        condition = self._expr(expr.condition)
        else_gap = self._take(self._start(expr.else_branch))
        else_doc = self._expr(expr.else_branch)

        cond_inner: list[Doc] = []
        if cond_gap.trailing:
            cond_inner.append(self._trailing(cond_gap.trailing))
        cond_inner.append(line())
        if cond_gap.leading:
            cond_inner.append(self._leading(cond_gap.leading, cond_gap.blanks_between))
        cond_inner.append(condition)

        else_inner: list[Doc] = []
        if else_gap.trailing:
            else_inner.append(self._trailing(else_gap.trailing))
        else_inner.append(line())
        if else_gap.leading:
            else_inner.append(self._leading(else_gap.leading, else_gap.blanks_between))
        else_inner.append(text("else "))
        else_inner.append(else_doc)

        return group(
            concat(then_doc, text(" if"), indent(concat(*cond_inner)), concat(*else_inner))
        )

    def _match(self, expr: Match) -> Doc:
        entries = [
            _Entry(
                start=self._pattern_start(arm.pattern),
                kind=ItemKind.MATCH_ARM,
                build=self._deferred(arm, self._match_arm),
            )
            for arm in expr.arms
        ]
        body = self._body(entries, self._close_offset(expr.end), _enum_policy)
        return concat(
            self._token(expr.keyword),
            text(" "),
            self._expr(expr.scrutinee),
            self._braced(body, expr.end),
        )

    def _match_arm(self, arm: MatchArm) -> Doc:
        arrow = self._token(arm.arrow) if arm.arrow is not None else text("=>")
        return group(
            concat(
                self._pattern(arm.pattern),
                text(" "),
                arrow,
                self._value_after(self._start(arm.body), self._expr(arm.body)),
            )
        )

    def _pattern(self, pattern: Pattern) -> Doc:
        if isinstance(pattern, WildcardPattern):
            return self._token(pattern.token)
        parts: list[Doc] = [
            self._token(pattern.enum),
            text("."),
            self._token(pattern.variant),
        ]
        if pattern.bindings:
            parts.append(text("("))
            for index, binding in enumerate(pattern.bindings):
                if index:
                    parts.append(text(", "))
                parts.append(self._token(binding))
            parts.append(text(")"))
        return concat(*parts)

    def _lambda(self, expr: Lambda) -> Doc:
        params_doc = self._delimited(
            concat(self._token(expr.keyword), text("(")),
            [(self._start(param), self._deferred(param, self._param)) for param in expr.params],
            None,
            ")",
            trailing_comma=True,
            spaced=False,
        )
        return_doc = text("")
        if expr.return_type is not None:
            return_doc = concat(
                text(" ->"), self._type_after(expr.return_type, expr.return_type_span)
            )
        if (
            len(expr.body) == 1
            and isinstance(expr.body[0], Return)
            and _is_arrow_return(expr.body[0])
        ):
            synthetic = expr.body[0]
            assert synthetic.value is not None
            arrow = self._token(synthetic.keyword)
            value = self._value_after(self._start(synthetic.value), self._expr(synthetic.value))
            return group(concat(params_doc, return_doc, text(" "), arrow, value))
        body = self._block_config(expr.body, expr.end, _stmt_policy)
        return concat(params_doc, return_doc, self._braced(body, expr.end))

    # --- statements ------------------------------------------------------

    def _stmt(self, stmt: Stmt) -> Doc:
        if isinstance(stmt, Import):
            return self._import(stmt)
        if isinstance(stmt, Block):
            return self._braced(self._block(stmt), stmt.end, leading_space=False)
        if isinstance(stmt, Class):
            return self._class(stmt)
        if isinstance(stmt, Expression):
            return self._expr(stmt.expression)
        if isinstance(stmt, ForIn):
            return self._for_in(stmt)
        if isinstance(stmt, Function):
            return self._function(stmt)
        if isinstance(stmt, If):
            return self._if_stmt(stmt)
        if isinstance(stmt, Interface):
            return self._interface(stmt)
        if isinstance(stmt, TypeAlias):
            return concat(
                self._token(stmt.keyword),
                text(" "),
                self._token(stmt.name),
                text(" ="),
                self._type_after(stmt.target, stmt.type_span),
            )
        if isinstance(stmt, Return):
            return self._return(stmt)
        if isinstance(stmt, Var):
            return self._var(stmt)
        if isinstance(stmt, Destructure):
            return self._destructure(stmt)
        if isinstance(stmt, EnumDecl):
            return self._enum(stmt)
        if isinstance(stmt, Try):
            return self._try(stmt)
        if isinstance(stmt, Raise):
            return self._raise(stmt)
        if isinstance(stmt, While):
            return self._while(stmt)
        if isinstance(stmt, ErrorStmt):
            return self._token(stmt.start)
        return text("")

    def _import(self, stmt: Import) -> Doc:
        parts: list[Doc] = []
        if stmt.from_import:
            keyword = self._token(stmt.start) if stmt.start is not None else text("from")
            parts.append(keyword)
            parts.append(text(" "))
            parts.append(self._path(stmt.path))
            parts.append(text(" import "))
            parts.append(self._import_names(stmt.names))
        else:
            keyword = self._token(stmt.start) if stmt.start is not None else text("import")
            parts.append(keyword)
            parts.append(text(" "))
            parts.append(self._path(stmt.path))
            if stmt.alias is not None:
                parts.append(text(" as "))
                parts.append(self._token(stmt.alias))
        return concat(*parts)

    def _path(self, path: Sequence[Token]) -> Doc:
        parts: list[Doc] = []
        for index, token in enumerate(path):
            if index:
                parts.append(text("."))
            parts.append(self._token(token))
        return concat(*parts)

    def _import_names(self, names: Sequence[ImportName]) -> Doc:
        parts: list[Doc] = []
        for index, name in enumerate(names):
            if index:
                parts.append(text(", "))
            parts.append(self._token(name.name))
            if name.alias is not None:
                parts.append(text(" as "))
                parts.append(self._token(name.alias))
        return concat(*parts)

    def _class(self, stmt: Class) -> Doc:
        parts: list[Doc] = [
            self._token(stmt.keyword) if stmt.keyword is not None else text("class"),
            text(" "),
            self._token(stmt.name),
            self._type_params(stmt.type_params),
        ]
        if stmt.superclass is not None:
            parts.append(text("("))
            parts.append(self._expr(stmt.superclass))
            parts.append(text(")"))
        if stmt.implements:
            parts.append(text(" implements "))
            parts.append(join_docs(text(", "), [self._token(token) for token in stmt.implements]))
        entries = [
            _Entry(
                start=self._start(field),
                kind=ItemKind.FIELD,
                build=self._deferred(field, self._field),
            )
            for field in stmt.fields
        ]
        entries.extend(
            _Entry(
                start=self._start(method),
                kind=ItemKind.METHOD,
                build=self._deferred(method, self._function),
            )
            for method in stmt.methods
        )
        entries.sort(key=lambda entry: entry.start)
        body = self._body(entries, self._close_offset(stmt.end), _class_policy)
        parts.append(self._braced(body, stmt.end))
        return concat(*parts)

    def _interface(self, stmt: Interface) -> Doc:
        entries = [
            _Entry(
                start=self._start(method),
                kind=ItemKind.METHOD,
                build=self._deferred(method, self._function),
            )
            for method in stmt.methods
        ]
        body = self._body(entries, self._close_offset(stmt.end), _interface_policy)
        return concat(
            self._token(stmt.keyword) if stmt.keyword is not None else text("interface"),
            text(" "),
            self._token(stmt.name),
            self._braced(body, stmt.end),
        )

    def _enum(self, stmt: EnumDecl) -> Doc:
        entries = [
            (
                self._token_offset(variant.name),
                self._deferred(variant, self._variant),
            )
            for variant in stmt.variants
        ]
        body = self._delimited(
            text(" {"),
            entries,
            stmt.end,
            "}",
            trailing_comma=False,
            spaced=True,
        )
        return concat(
            self._token(stmt.keyword) if stmt.keyword is not None else text("enum"),
            text(" "),
            self._token(stmt.name),
            self._type_params(stmt.type_params),
            body,
        )

    def _variant(self, variant: EnumVariant) -> Doc:
        parts: list[Doc] = [self._token(variant.name)]
        if variant.payload:
            parts.append(text("("))
            for index, ty in enumerate(variant.payload):
                if index:
                    parts.append(text(", "))
                span = variant.payload_spans[index] if index < len(variant.payload_spans) else None
                parts.append(self._type_after(ty, span, leading_space=False))
            parts.append(text(")"))
        return concat(*parts)

    def _function(self, stmt: Function) -> Doc:
        if stmt.fn_token is not None:
            parts: list[Doc] = [self._token(stmt.fn_token), text(" ")]
        else:
            parts = [text("fn ")]
        parts.append(self._token(stmt.name))
        parts.append(self._type_params(stmt.type_params, stmt.type_param_bounds))
        parts.append(self._params(stmt.params, stmt.params_end))
        if stmt.return_type is not None:
            parts.append(text(" ->"))
            parts.append(self._type_after(stmt.return_type, stmt.return_type_span))
        if stmt.abstract:
            return concat(*parts)
        body = self._block_config(stmt.body, stmt.end, _stmt_policy)
        parts.append(self._braced(body, stmt.end))
        return concat(*parts)

    def _params(self, params: Sequence[Param], params_end: Token | None) -> Doc:
        entries = [(self._start(param), self._deferred(param, self._param)) for param in params]
        return self._delimited(
            text("("), entries, params_end, ")", trailing_comma=True, spaced=False
        )

    def _param(self, param: Param) -> Doc:
        parts: list[Doc] = []
        if param.variadic:
            parts.append(text("..."))
        if param.mutable:
            parts.append(text("var "))
        parts.append(self._token(param.name))
        if param.type_annotation is not None:
            parts.append(text(":"))
            parts.append(self._type_after(param.type_annotation, param.type_span))
        if param.default is not None:
            parts.append(text(" ="))
            parts.append(self._value_after(self._start(param.default), self._expr(param.default)))
        return concat(*parts)

    def _field(self, field: Field) -> Doc:
        parts: list[Doc] = [
            self._token(field.keyword)
            if field.keyword is not None
            else text("var" if field.mutable else "val"),
            text(" "),
            self._token(field.name),
        ]
        if field.type_annotation is not None:
            parts.append(text(":"))
            parts.append(self._type_after(field.type_annotation, field.type_span))
        if field.initializer is not None:
            parts.append(text(" ="))
            parts.append(
                self._value_after(self._start(field.initializer), self._expr(field.initializer))
            )
        return concat(*parts)

    def _var(self, stmt: Var) -> Doc:
        parts: list[Doc] = [
            self._token(stmt.keyword)
            if stmt.keyword is not None
            else text("var" if stmt.mutable else "val"),
            text(" "),
            self._token(stmt.name),
        ]
        if stmt.type_annotation is not None:
            parts.append(text(":"))
            parts.append(self._type_after(stmt.type_annotation, stmt.type_span))
        if stmt.initializer is not None:
            parts.append(text(" ="))
            parts.append(
                self._value_after(self._start(stmt.initializer), self._expr(stmt.initializer))
            )
        return concat(*parts)

    def _destructure(self, stmt: Destructure) -> Doc:
        parts: list[Doc] = [
            self._token(stmt.keyword)
            if stmt.keyword is not None
            else text("var" if stmt.mutable else "val"),
            text(" "),
            self._destructure_pattern(stmt.pattern),
        ]
        if stmt.type_annotation is not None:
            parts.append(text(":"))
            parts.append(self._type_after(stmt.type_annotation, stmt.type_span))
        parts.append(text(" ="))
        parts.append(self._value_after(self._start(stmt.initializer), self._expr(stmt.initializer)))
        return concat(*parts)

    def _destructure_pattern(self, pattern: object) -> Doc:
        if isinstance(pattern, NamePattern):
            return self._token(pattern.name)
        if isinstance(pattern, TuplePattern):
            parts: list[Doc] = [text("(")]
            for index, element in enumerate(pattern.elements):
                if index:
                    parts.append(text(", "))
                parts.append(self._destructure_pattern(element))
            parts.append(text(")"))
            return concat(*parts)
        return text("")

    def _return(self, stmt: Return) -> Doc:
        keyword = self._token(stmt.keyword)
        if stmt.value is None:
            return keyword
        return concat(
            keyword,
            self._value_after(self._start(stmt.value), self._expr(stmt.value)),
        )

    def _raise(self, stmt: Raise) -> Doc:
        keyword = self._token(stmt.keyword)
        if stmt.value is None:
            return keyword
        return concat(
            keyword,
            self._value_after(self._start(stmt.value), self._expr(stmt.value)),
        )

    def _type_params(
        self,
        params: Sequence[Token],
        bounds: Sequence[Sequence[Token]] = (),
    ) -> Doc:
        if not params:
            return concat()
        parts: list[Doc] = [text("[")]
        for index, param in enumerate(params):
            if index:
                parts.append(text(", "))
            parts.append(self._token(param))
            if index < len(bounds) and bounds[index]:
                parts.append(text(": "))
                parts.append(
                    join_docs(text(" + "), [self._token(token) for token in bounds[index]])
                )
        parts.append(text("]"))
        return concat(*parts)

    def _if_stmt(self, stmt: If, *, as_elif: bool = False) -> Doc:
        if as_elif:
            keyword: Doc = text("elif")
        elif stmt.keyword is not None:
            keyword = self._token(stmt.keyword)
        else:
            keyword = text("if")
        header = concat(keyword, text(" ("), self._expr(stmt.condition), text(")"))
        if isinstance(stmt.then_branch, Block):
            body = self._block(stmt.then_branch)
            head = concat(header, self._braced(body, stmt.then_branch.end))
            return concat(head, self._else_part(stmt.else_branch, after_block=True))
        head = group(concat(header, indent(concat(line(), self._stmt(stmt.then_branch)))))
        return concat(head, self._else_part(stmt.else_branch, after_block=False))

    def _else_part(self, branch: Stmt | None, *, after_block: bool) -> Doc:
        if branch is None:
            return concat()
        if isinstance(branch, If):
            prefix = text(" ") if after_block else hardline()
            return concat(prefix, self._if_stmt(branch, as_elif=True))
        if isinstance(branch, Block):
            body = self._block(branch)
            prefix = text(" ") if after_block else hardline()
            return concat(prefix, text("else"), self._braced(body, branch.end))
        body_doc = self._stmt(branch)
        if after_block:
            return concat(text(" else "), body_doc)
        return concat(hardline(), text("else "), body_doc)

    def _while(self, stmt: While) -> Doc:
        keyword = self._token(stmt.keyword) if stmt.keyword is not None else text("while")
        header = concat(keyword, text(" ("), self._expr(stmt.condition), text(")"))
        if isinstance(stmt.body, Block):
            return concat(header, self._braced(self._block(stmt.body), stmt.body.end))
        return group(concat(header, indent(concat(line(), self._stmt(stmt.body)))))

    def _for_in(self, stmt: ForIn) -> Doc:
        keyword = self._token(stmt.keyword) if stmt.keyword is not None else text("for")
        header = concat(
            keyword,
            text(" "),
            self._token(stmt.name),
            text(" in "),
            self._expr(stmt.iterable),
        )
        if isinstance(stmt.body, Block):
            return concat(header, self._braced(self._block(stmt.body), stmt.body.end))
        return group(concat(header, indent(concat(line(), self._stmt(stmt.body)))))

    def _try(self, stmt: Try) -> Doc:
        handlers = stmt.handlers
        if handlers:
            first = handlers[0]
            try_end = (
                first.keyword.offset
                if first.keyword is not None and first.keyword.offset is not None
                else self._token_offset(first.type_name)
            )
            try_close: Token | None = first.keyword
        elif stmt.finally_body:
            try_end = self._start(stmt.finally_body[0])
            try_close = None
        else:
            try_end = self._close_offset(stmt.end)
            try_close = stmt.end
        parts: list[Doc] = [
            self._token(stmt.keyword),
            self._braced(
                self._block_config_at(stmt.body, try_end, _stmt_policy),
                try_close,
            ),
        ]
        for handler in handlers:
            parts.append(text(" "))
            if handler.keyword is not None:
                parts.append(self._token(handler.keyword))
            else:
                parts.append(text("except"))
            parts.append(text(" "))
            parts.append(self._token(handler.type_name))
            parts.append(text(" as "))
            parts.append(self._token(handler.binding))
            parts.append(
                self._braced(
                    self._block_config(handler.body, handler.end, _stmt_policy),
                    handler.end,
                )
            )
        if stmt.finally_body is not None:
            parts.append(text(" finally"))
            parts.append(
                self._braced(
                    self._block_config(stmt.finally_body, stmt.end, _stmt_policy),
                    stmt.end,
                )
            )
        return concat(*parts)


def _is_arrow_return(stmt: Return) -> bool:
    return stmt.keyword.type is TokenType.FAT_ARROW


def join_docs(separator: Doc, parts: Sequence[Doc]) -> Doc:
    items: list[Doc] = []
    for index, part in enumerate(parts):
        if index:
            items.append(separator)
        items.append(part)
    return concat(*items)
