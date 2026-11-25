# SPDX-License-Identifier: MIT OR Apache-2.0
"""Índice de spans de nós (ADR-0090).

O parser não guarda spans em todo nó; o índice deriva a extensão a partir dos tokens
do próprio nó e dos filhos. Parênteses de agrupamento entram no span porque `Grouping`
guarda os dois tokens. Ele indexa expressões, declarações, parâmetros, campos, variantes
e anotações de tipo; é a base formal para navegação, diagnósticos e edições.

O índice também sabe devolver o texto e a linha de um span, desde que receba o
`SourceMap` da execução (módulos incluídos). É o que o checker consome para as `notes`
de proveniência: "the value comes from `pessoa.nome` (line 7)".
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, cast

from loxia_core.diagnostics.diagnostic import Span
from loxia_core.diagnostics.source import SourceMap
from loxia_core.frontend.destructuring import pattern_names
from loxia_core.frontend.expr import (
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
    LiteralPattern,
    Logical,
    MapLiteral,
    Match,
    MatchArm,
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
    Class,
    Destructure,
    EnumDecl,
    EnumVariant,
    ErrorStmt,
    Field,
    ForIn,
    Function,
    Import,
    ImportName,
    Interface,
    Param,
    Stmt,
    TypeAlias,
    Var,
)
from loxia_core.frontend.tokens import Token

EXPR_TYPES = (
    As,
    Assign,
    Binary,
    Call,
    Conditional,
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
    Range,
    Set,
    Super,
    This,
    TupleLiteral,
    Unary,
    Variable,
)

NODE_TYPES = (
    *EXPR_TYPES,
    Class,
    Destructure,
    EnumDecl,
    EnumVariant,
    ErrorStmt,
    Field,
    Function,
    Import,
    ImportName,
    Interface,
    Param,
    TypeAlias,
    Var,
    MatchArm,
    LiteralPattern,
    VariantPattern,
    WildcardPattern,
)

# (start, end, file) em bytes UTF-8.
type Extent = tuple[int, int, str]


@dataclass(frozen=True, init=False)
class NodeSpan:
    """Extensão half-open de um nó de sintaxe, em offsets de bytes UTF-8.

    `kind` diz que autoridade produziu o span: `node` (AST), `name` (nome de
    declaração/parâmetro/campo/variante) ou `type` (nome dentro de uma anotação).
    """

    node: object
    start: int
    end: int
    file: str = ""
    kind: str = "node"

    def __init__(
        self,
        node: object = None,
        start: int = 0,
        end: int = 0,
        file: str = "",
        *,
        expression: object = None,
        kind: str = "node",
    ) -> None:
        # `expression=` mantém o construtor antigo de `ExprSpan` funcionando.
        if expression is not None:
            if node is not None:
                raise TypeError("pass either node or expression, not both")
            node = expression
        object.__setattr__(self, "node", node)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "file", file)
        object.__setattr__(self, "kind", kind)

    @property
    def expression(self) -> Expr:
        """Compatibilidade com o uso antigo, que só indexava expressões."""
        if not isinstance(self.node, EXPR_TYPES):
            raise TypeError("this span does not wrap an Expr")
        return self.node


ExprSpan = NodeSpan


class SourceIndex:
    """Mapeia offset → menor expressão que contém aquele offset."""

    def __init__(
        self,
        statements: list[Stmt],
        source: str,
        *,
        sources: SourceMap | None = None,
        extra_spans: list[Span] | None = None,
        navigation_file: str | None = None,
        lazy: bool = False,
    ) -> None:
        self.source = source
        self.sources = sources
        self._statements = statements
        self._extra_spans = list(extra_spans or ())
        # O índice carrega os módulos inlined pelo loader, mas nomes de navegação
        # só são consultados no arquivo aberto: limitar por arquivo evita pagar
        # por declarações de `std`/imports em todo check.
        self._navigation_file = navigation_file
        self._spans: list[NodeSpan] = []
        self._by_node: dict[object, NodeSpan] = {}
        self._by_extent: dict[Extent, NodeSpan] = {}
        self._built = False
        if not lazy:
            self._build()

    def _build(self) -> None:
        """Constrói o índice na primeira consulta quando `lazy=True`."""
        if self._built:
            return
        self._built = True
        # Nomes de tipo entram antes da caminhada do AST: quando coincidem com o
        # span de um nó (ex.: `x: Int`), o kind específico vence e o nó reusa o
        # mesmo span (offsets idênticos).
        for span in self._extra_spans:
            self._register(
                NodeSpan(
                    span,
                    span.start.offset or 0,
                    span.end.offset or 0,
                    span.file,
                    kind="type",
                )
            )
        for statement in self._statements:
            self._walk(statement)

    @property
    def spans(self) -> list[NodeSpan]:
        self._build()
        return self._spans

    def _register(self, span: NodeSpan) -> NodeSpan:
        """Registra um span uma única vez por intervalo; devolve o span vigente."""
        key = (span.start, span.end, span.file)
        existing = self._by_extent.get(key)
        if existing is not None:
            if span.node is not None:
                self._by_node[span.node] = existing
            return existing
        self._by_extent[key] = span
        self._spans.append(span)
        if span.node is not None:
            self._by_node[span.node] = span
        return span

    def _register_name(self, token: Token) -> None:
        if self._navigation_file is not None and token.file != self._navigation_file:
            return
        self._register(
            NodeSpan(
                token,
                token.offset or 0,
                (token.offset or 0) + len(token.lexeme.encode("utf-8")),
                token.file,
                kind="name",
            )
        )

    def _collect_names(self, value: object) -> None:
        """Registra nomes de declaração achados na própria caminhada do AST.

        Não é um segundo passe: `_walk` já visita todos os nós, então o nome entra
        no mesmo percurso (parâmetros de lambda, campos e variantes inclusos).
        """
        if isinstance(value, (Var, ForIn, EnumVariant, Interface, TypeAlias, Field, Param)):
            self._register_name(value.name)
        elif isinstance(value, Destructure):
            for token in pattern_names(value.pattern):
                self._register_name(token)
        elif isinstance(value, (Function, Class, EnumDecl)):
            self._register_name(value.name)
            for token in value.type_params:
                self._register_name(token)

    def _walk(self, value: object) -> Extent | None:
        self._collect_names(value)
        if isinstance(value, Token):
            offset = value.offset or 0
            return offset, offset + len(value.lexeme.encode("utf-8")), value.file
        if isinstance(value, Span):
            start = value.start.offset or 0
            end = value.end.offset or 0
            self._register(NodeSpan(value, start, end, value.file))
            return start, end, value.file
        if isinstance(value, NODE_TYPES):
            own = self._own_extent(value)
            if own is None:
                return None
            self._register(NodeSpan(value, own[0], own[1], own[2]))
            return own
        if is_dataclass(value) and not isinstance(value, type):
            return self._merge(
                [
                    extent
                    for item in fields(value)
                    if (extent := self._walk(getattr(value, item.name))) is not None
                ]
            )
        if isinstance(value, (list, tuple)):
            return self._merge(
                [extent for item in value if (extent := self._walk(item)) is not None]
            )
        return None

    @staticmethod
    def _merge(extents: list[Extent]) -> Extent | None:
        if not extents:
            return None
        first = min(extents, key=lambda item: item[0])
        file = first[2] or next((item[2] for item in extents if item[2]), "")
        return first[0], max(item[1] for item in extents), file

    def _own_extent(self, expression: object) -> Extent | None:
        if (
            isinstance(expression, Grouping)
            and expression.start is not None
            and expression.end is not None
        ):
            # Indexa os filhos também: o `at()` precisa devolver o menor span dentro
            # dos parênteses, não o Grouping inteiro.
            for item in fields(cast(Any, expression)):
                self._walk(getattr(expression, item.name))
            start = expression.start.offset or 0
            end = (expression.end.offset or 0) + len(expression.end.lexeme.encode("utf-8"))
            return start, end, expression.start.file or expression.end.file
        if isinstance(expression, Literal) and expression.token is not None:
            start = expression.token.offset or 0
            return (
                start,
                start + len(expression.token.lexeme.encode("utf-8")),
                expression.token.file,
            )
        extents: list[Extent] = []
        for item in fields(cast(Any, expression)):
            value = getattr(expression, item.name)
            extent = self._walk(value)
            if extent is not None:
                extents.append(extent)
        return self._merge(extents)

    def at(self, offset: int, *, file: str | None = None) -> NodeSpan | None:
        """Menor expressão que contém `offset` (half-open).

        Com `file`, restringe aos spans daquele arquivo: o índice carrega os módulos
        do loader, e o offset local não pode ser resolvido pelo texto de outro módulo.
        """
        self._build()
        found = [
            span
            for span in self.spans
            if span.start <= offset < span.end and (file is None or span.file == file)
        ]
        if not found:
            return None
        return min(found, key=lambda span: span.end - span.start)

    def span_of(self, node: object) -> NodeSpan | None:
        """Span registrado para um nó específico, se ele foi indexado."""
        self._build()
        return self._by_node.get(node)

    def text_of(self, span: NodeSpan) -> str | None:
        """Texto-fonte do span, ou `None` se a fonte daquele arquivo não está carregada."""
        source = self._source_of(span.file)
        if source is None:
            return None
        data = source.encode("utf-8")
        if span.start < 0 or span.end < span.start or span.end > len(data):
            return None
        try:
            return data[span.start : span.end].decode("utf-8")
        except UnicodeDecodeError:
            return None

    def line_of(self, span: NodeSpan) -> int | None:
        """Linha 1-based do início do span, ou `None` sem a fonte carregada."""
        source = self._source_of(span.file)
        if source is None:
            return None
        data = source.encode("utf-8")
        if span.start < 0 or span.start > len(data):
            return None
        return data[: span.start].count(b"\n") + 1

    def _source_of(self, file: str) -> str | None:
        if self.sources is not None:
            loaded = self.sources.get(file)
            if loaded is not None:
                return loaded.text
            return self.source if file == "" else None
        # Sem `SourceMap` só há uma fonte conhecida (compatibilidade com o uso antigo).
        return self.source
