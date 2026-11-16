"""Análise de captura para closures do backend (ADR-0046).

O lowering precisa saber, antes de emitir IR, duas coisas:

- quais bindings locais viram **célula** (porque alguma função aninhada os usa);
- quais bindings cada função/lambda precisa carregar no seu `env`.

A AST não traz isso: o resolver grava só a distância léxica de cada expressão. Este
passe reconstrói a pilha de escopos (funções, parâmetros, blocos e variáveis) e propaga a
captura pelos níveis intermediários. Ele não altera a AST nem produz IR — é uma análise,
não uma HIR (ADR-0046, decisão 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    Logical,
    MapLiteral,
    Match,
    Range,
    Set,
    TupleLiteral,
    Unary,
    Variable,
)
from loxia_core.frontend.stmt import (
    Block,
    Class,
    Destructure,
    Expression,
    ForIn,
    Function,
    If,
    Param,
    Return,
    Stmt,
    Var,
    While,
)

FunctionNode = Function | Lambda


@dataclass(frozen=True)
class Capture:
    """Um binding do escopo externo que uma função precisa carregar no `env`."""

    name: str
    decl: object


@dataclass
class _Binding:
    name: str
    decl: object
    owner: _Unit | None  # `None` = global/topo


@dataclass
class _Unit:
    node: FunctionNode | None
    parent: _Unit | None
    captures: dict[str, Capture] = field(default_factory=dict)

    def add_capture(self, binding: _Binding) -> None:
        existing = self.captures.get(binding.name)
        if existing is None:
            self.captures[binding.name] = Capture(binding.name, binding.decl)
        elif existing.decl is not binding.decl:
            raise AssertionError(
                f"capture ambíguo para '{binding.name}' na mesma função"
            )


@dataclass(frozen=True)
class CaptureAnalysis:
    """Resultado do passe: capturas por função e declarações que viram célula."""

    captures: dict[FunctionNode, tuple[Capture, ...]]
    captured_decls: frozenset[int]

    def captures_of(self, node: FunctionNode) -> tuple[Capture, ...]:
        return self.captures.get(node, ())

    def is_captured(self, decl: object) -> bool:
        return id(decl) in self.captured_decls


class _Analyzer:
    def __init__(self) -> None:
        self._main = _Unit(None, None)
        self._unit = self._main
        self._scopes: list[dict[str, _Binding]] = [{}]
        self._units: dict[FunctionNode, _Unit] = {}
        self._captured: set[int] = set()

    def analyze(self, statements: list[Stmt]) -> CaptureAnalysis:
        for statement in statements:
            self._stmt(statement)

        captures = {
            node: tuple(unit.captures[name] for name in sorted(unit.captures))
            for node, unit in self._units.items()
        }
        return CaptureAnalysis(captures, frozenset(self._captured))

    # --- escopos ---

    def _declare(self, name: str, decl: object) -> None:
        owner = None if len(self._scopes) == 1 else self._unit
        self._scopes[-1][name] = _Binding(name, decl, owner)

    def _use(self, name: str) -> None:
        for scope in reversed(self._scopes):
            binding = scope.get(name)
            if binding is None:
                continue

            if binding.owner is None or binding.owner is self._unit:
                return

            unit: _Unit | None = self._unit
            while unit is not None and unit is not binding.owner:
                unit.add_capture(binding)
                unit = unit.parent

            self._captured.add(id(binding.decl))
            return

        # Variável indefinida: o checker já reporta. O lowering vira panic site.

    # --- funções ---

    def _function(
        self, node: FunctionNode, params: list[Param], body: list[Stmt]
    ) -> None:
        unit = _Unit(node, self._unit)
        self._units[node] = unit

        saved = self._unit
        self._unit = unit
        self._scopes.append({})
        try:
            for param in params:
                self._declare(param.name.lexeme, param)
            for statement in body:
                self._stmt(statement)
        finally:
            self._scopes.pop()
            self._unit = saved

    # --- statements ---

    def _stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, Block):
            self._scopes.append({})
            try:
                for statement in stmt.statements:
                    self._stmt(statement)
            finally:
                self._scopes.pop()
            return

        if isinstance(stmt, Function):
            self._declare(stmt.name.lexeme, stmt)
            self._function(stmt, stmt.params, stmt.body)
            return

        if isinstance(stmt, Class):
            self._declare(stmt.name.lexeme, stmt)
            for field in stmt.fields:
                if field.initializer is not None:
                    self._expr(field.initializer)
            for method in stmt.methods:
                self._function(method, method.params, method.body)
            return

        if isinstance(stmt, Var):
            if stmt.initializer is not None:
                self._expr(stmt.initializer)
            self._declare(stmt.name.lexeme, stmt)
            return

        if isinstance(stmt, Destructure):
            self._expr(stmt.initializer)
            for name in pattern_names(stmt.pattern):
                self._declare(name.lexeme, name)
            return

        if isinstance(stmt, If):
            self._expr(stmt.condition)
            self._stmt(stmt.then_branch)
            if stmt.else_branch is not None:
                self._stmt(stmt.else_branch)
            return

        if isinstance(stmt, While):
            self._expr(stmt.condition)
            self._stmt(stmt.body)
            return


        if isinstance(stmt, Return):
            if stmt.value is not None:
                self._expr(stmt.value)
            return

        if isinstance(stmt, Expression):
            self._expr(stmt.expression)
            return

        if isinstance(stmt, ForIn):
            self._expr(stmt.iterable)
            self._scopes.append({})
            try:
                self._declare(stmt.name.lexeme, stmt.name)
                self._stmt(stmt.body)
            finally:
                self._scopes.pop()
            return

        # Enums, try/raise e destructuring ainda não têm lowering no L4/L5;
        # ignorar aqui é seguro porque o lowering falha antes de precisar do passe.

    # --- expressões ---

    def _expr(self, expr: Expr) -> None:
        if isinstance(expr, Variable):
            self._use(expr.name.lexeme)
            return

        if isinstance(expr, Assign):
            self._expr(expr.value)
            self._use(expr.name.lexeme)
            return

        if isinstance(expr, Lambda):
            self._function(expr, expr.params, expr.body)
            return

        if isinstance(expr, Binary):
            self._expr(expr.left)
            self._expr(expr.right)
            return

        if isinstance(expr, Grouping):
            self._expr(expr.expression)
            return

        if isinstance(expr, Unary):
            self._expr(expr.right)
            return

        if isinstance(expr, Conditional):
            self._expr(expr.condition)
            self._expr(expr.then_branch)
            self._expr(expr.else_branch)
            return

        if isinstance(expr, Logical):
            self._expr(expr.left)
            self._expr(expr.right)
            return

        if isinstance(expr, Call):
            self._expr(expr.callee)
            for argument in expr.arguments:
                self._expr(argument)
            return

        if isinstance(expr, InterpolatedString):
            for part in expr.parts:
                if not isinstance(part, str):
                    self._expr(part)
            return

        if isinstance(expr, ListLiteral):
            for element in expr.elements:
                self._expr(element)
            return

        if isinstance(expr, MapLiteral):
            for key, value in expr.entries:
                self._expr(key)
                self._expr(value)
            return

        if isinstance(expr, TupleLiteral):
            for element in expr.elements:
                self._expr(element)
            return

        if isinstance(expr, Range):
            self._expr(expr.start)
            self._expr(expr.end)
            return

        if isinstance(expr, Index):
            self._expr(expr.object)
            self._expr(expr.index)
            return

        if isinstance(expr, IndexSet):
            self._expr(expr.object)
            self._expr(expr.index)
            self._expr(expr.value)
            return

        if isinstance(expr, Get):
            self._expr(expr.object)
            return

        if isinstance(expr, Set):
            self._expr(expr.object)
            self._expr(expr.value)
            return

        if isinstance(expr, Is):
            self._expr(expr.left)
            return

        if isinstance(expr, As):
            self._expr(expr.left)
            return

        if isinstance(expr, Match):
            self._expr(expr.scrutinee)
            for arm in expr.arms:
                self._expr(arm.body)
            return

        # Literal, This, Super e padrões não introduzem captura.


def analyze_captures(statements: list[Stmt]) -> CaptureAnalysis:
    return _Analyzer().analyze(statements)
