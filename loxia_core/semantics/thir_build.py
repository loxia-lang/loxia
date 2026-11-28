# SPDX-License-Identifier: MIT OR Apache-2.0
"""Produtor do THIR: AST + decisões do checker → árvore tipada e resolvida.

Este é o **único** lugar que lê as tabelas por identidade de nó do checker
(`types`, `flow_types`, `delays`, instanciações genéricas). A partir daqui, nenhum
motor precisa de `dict[Expr, Ty]`: o tipo viaja no nó, o binding viaja no `Ref` e as
capturas viajam no `TFunction`.

Regras de resolução (espelham o checker e o `captures` do backend, ADR-0046):

- declaração no escopo de topo (índice 0) → binding `GLOBAL`;
- declaração em qualquer escopo interno → `LOCAL` da unidade de função dona;
- uso numa unidade que não é a dona → `CAPTURE`, com índice na ordem de primeira
  captura (que é a ordem do `env` montado pelo motor);
- binding capturado por qualquer unidade interna vira `cell`;
- uso de nome não declarado → `UNRESOLVED` (o `--check` já reportou; o lowering emite
  o panic site, como hoje).

O produtor não é o dono da semântica de tipos: ele **não infere** nada, só copia a
decisão já tomada pelo checker (I4). Quando uma entrada falta, o nó fica com `ty`
`None` e o motor decide; nunca se inventa tipo aqui.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from loxia_core.diagnostics.diagnostic import Span
from loxia_core.frontend.destructuring import (
    DestructurePattern,
    NamePattern,
    TuplePattern,
    pattern_names,
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
from loxia_core.frontend.spans import node_span, span_of_token_exact
from loxia_core.frontend.stmt import (
    Block,
    Break,
    Class,
    Continue,
    Destructure,
    EnumDecl,
    ErrorStmt,
    Expression,
    Field,
    ForIn,
    Function,
    If,
    Import,
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
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import ClassTy, FnTy, TupleTy, Ty, display
from loxia_core.thir.model import (
    Decl,
    DeclId,
    DeclKind,
    FnId,
    Ref,
    Storage,
    TAs,
    TAssign,
    TBinary,
    TBlock,
    TBreak,
    TCall,
    TCapture,
    TClass,
    TClassDecl,
    TConditional,
    TConst,
    TContinue,
    TDestructurePattern,
    TDestructureStmt,
    TEnum,
    TEnumDecl,
    TEnumVariant,
    TExpr,
    TExprStmt,
    TField,
    TFnDecl,
    TForIn,
    TFunction,
    TGet,
    THandler,
    TIf,
    TIndex,
    TIndexSet,
    TInstance,
    TInterface,
    TInterfaceDecl,
    TInterp,
    TIs,
    TLambda,
    TList,
    TLiteralPattern,
    TLogical,
    TMap,
    TMatch,
    TMatchArm,
    TModule,
    TNamePattern,
    TParam,
    TPattern,
    TRaise,
    TRange,
    TReturn,
    TSet,
    TStmt,
    TSuper,
    TThis,
    TTry,
    TTuple,
    TTuplePattern,
    TTypeAlias,
    TUnary,
    TVar,
    TVariantPattern,
    TVarStmt,
    TWhile,
    TWildcardPattern,
)

FunctionNode = Function | Lambda


class ThirBuildError(Exception):
    """Construto que não deveria chegar ao produtor (bug interno, não erro do usuário).

    Construtos de erro (`ErrorStmt`/`ErrorExpr`) só existem na árvore recuperada e
    `Import` é removido pelo loader antes do checkout; ver um deles aqui significa que
    um caminho novo de build pulou uma fase.
    """


@dataclass
class _DeclDraft:
    id: DeclId
    name: str
    ty: Ty | None
    mutable: bool
    kind: DeclKind
    span: Span | None


@dataclass
class _Binding:
    """Nome resolvido num escopo; `unit is None` significa binding de topo (global)."""

    decl: DeclId
    name: str
    unit: _Unit | None


@dataclass
class _Unit:
    """Unidade de função: dona dos locais e das capturas que o `env` carrega."""

    id: FnId
    parent: _Unit | None
    captures: dict[DeclId, TCapture] = field(default_factory=dict)

    def add_capture(self, decl: DeclId, name: str) -> None:
        if decl not in self.captures:
            self.captures[decl] = TCapture(decl=decl, name=name)

    def ordered(self) -> tuple[TCapture, ...]:
        """Capturas em ordem canônica (nome); nome repetido é ambiguidade de `env`."""
        ordered = tuple(sorted(self.captures.values(), key=lambda capture: capture.name))
        names = [capture.name for capture in ordered]
        if len(set(names)) != len(names):
            raise ThirBuildError(f"ambiguous capture in the same function: {names}")
        return ordered


class _Builder:
    def __init__(
        self,
        *,
        storage_types: dict[Expr, Ty],
        flow_types: dict[Expr, Ty] | None = None,
        generic_instances: dict[Call, Any] | None = None,
        generic_classes: Iterable[ClassTy] = (),
        generic_class_sites: dict[Call, ClassTy] | None = None,
        type_aliases: dict[str, Ty] | None = None,
        function_types: dict[Any, FnTy] | None = None,
        entry: Function | None = None,
        globals_scope: dict[str, Ty] | None = None,
        source_path: str = "<lox>",
    ) -> None:
        self._storage = storage_types
        self._flow = flow_types if flow_types is not None else storage_types
        self._generic_instances = generic_instances or {}
        self._generic_classes = generic_classes
        self._generic_class_sites = generic_class_sites or {}
        self._function_types = function_types or {}
        self._type_aliases = dict(type_aliases or {})
        self._entry_node = entry
        # Escopo global do checker: a autoridade sobre nomes pré-declarados
        # (builtins, namespaces nativos, classes de exceção) que não têm declaração
        # no fonte. Só consultado depois do escopo léxico.
        self._globals_scope = globals_scope or {}
        self._predeclared: dict[object, DeclId] = {}
        # Nomes que o módulo declara em algum ponto (inclusive depois do uso): o
        # fallback de `_use` não pode chamá-los de `BUILTIN`.
        self._toplevel_names: set[str] = set()
        self._source_path = source_path

        self._drafts: list[_DeclDraft] = []
        self._cells: set[DeclId] = set()
        self._next_decl: DeclId = 0
        self._scopes: list[dict[str, _Binding]] = [{}]
        self._module_unit = _Unit(id=0, parent=None)
        self._unit = self._module_unit
        self._memo: dict[int, Span | None] = {}
        self._instances: dict[tuple[str, tuple[Ty, ...]], TInstance] = {}
        self._method_class: str | None = None
        self._entry_id: FnId | None = None

    # --- API ---

    def build(self, statements: list[Stmt]) -> TModule:
        self._predeclare_toplevel(statements)
        body = tuple(self._stmt(statement) for statement in statements)
        # `generic_classes` é um `set`: iterar direto vazaria ordem de hash no
        # contrato (I3). A chave é canônica e total, então a inserção é determinística.
        for klass in sorted(
            self._generic_classes,
            key=lambda item: (item.name, tuple(display(arg) for arg in item.args)),
        ):
            self._add_instance(klass.name, klass.args)
        return TModule(
            source_path=self._source_path,
            statements=body,
            decls=self._frozen_decls(),
            instances=tuple(
                sorted(
                    self._instances.values(),
                    key=lambda item: (
                        item.name,
                        tuple(display(arg) for arg in item.type_args),
                    ),
                )
            ),
            type_aliases=tuple(
                (name, self._type_aliases[name]) for name in sorted(self._type_aliases)
            ),
            entry=self._entry_id,
        )

    def _predeclare_toplevel(self, statements: list[Stmt]) -> None:
        """Declara os nomes que o checker pré-declara antes de checar os corpos.

        Sem isto uma referência para frente (`fn a() { return b() }` + `fn b()`) viraria
        `UNRESOLVED`, embora o programa passe no `--check`. O checker pré-declara
        funções, classes, interfaces e enums; `val`/`var` de topo continuam sequenciais.
        """
        for statement in statements:
            name: Token | None = None
            kind = DeclKind.VAR
            if isinstance(statement, Function):
                name, kind = statement.name, DeclKind.FUNCTION
            elif isinstance(statement, Class):
                name, kind = statement.name, DeclKind.CLASS
            elif isinstance(statement, Interface):
                name, kind = statement.name, DeclKind.INTERFACE
            elif isinstance(statement, EnumDecl):
                name, kind = statement.name, DeclKind.ENUM
            elif isinstance(statement, Var):
                self._toplevel_names.add(statement.name.lexeme)
            elif isinstance(statement, Destructure):
                self._toplevel_names.update(
                    token.lexeme for token in pattern_names(statement.pattern)
                )
            elif isinstance(statement, ForIn):
                self._toplevel_names.add(statement.name.lexeme)
            if name is None:
                continue
            self._toplevel_names.add(name.lexeme)
            decl = self._new_decl(name.lexeme, None, False, kind, self._tok(name))
            self._declare(name.lexeme, decl)
            self._predeclared[statement] = decl

    # --- declarações e escopos ---

    def _frozen_decls(self) -> tuple[Decl, ...]:
        return tuple(
            Decl(
                id=draft.id,
                name=draft.name,
                ty=draft.ty,
                mutable=draft.mutable,
                kind=draft.kind,
                span=draft.span,
                cell=draft.id in self._cells,
            )
            for draft in self._drafts
        )

    def _new_decl(
        self,
        name: str,
        ty: Ty | None,
        mutable: bool,
        kind: DeclKind,
        span: Span | None,
    ) -> DeclId:
        self._next_decl += 1
        self._drafts.append(_DeclDraft(self._next_decl, name, ty, mutable, kind, span))
        return self._next_decl

    def _declare(self, name: str, decl: DeclId) -> None:
        owner = None if len(self._scopes) == 1 else self._unit
        self._scopes[-1][name] = _Binding(decl=decl, name=name, unit=owner)

    def _use(self, name: str) -> Ref:
        for scope in reversed(self._scopes):
            binding = scope.get(name)
            if binding is None:
                continue
            if binding.unit is None:
                return Ref(storage=Storage.GLOBAL, decl=binding.decl, name=name)
            if binding.unit is self._unit:
                return Ref(storage=Storage.LOCAL, decl=binding.decl, name=name)

            unit: _Unit | None = self._unit
            guard = 0
            while unit is not None and unit is not binding.unit:
                unit.add_capture(binding.decl, binding.name)
                unit = unit.parent
                guard += 1
                if guard > 10_000:
                    raise ThirBuildError(f"capture chain too deep for '{name}'")
            if unit is None:
                raise ThirBuildError(f"binding '{name}' is not an ancestor of the current function")
            self._cells.add(binding.decl)
            return Ref(storage=Storage.CAPTURE, decl=binding.decl, name=name)

        # Nome pré-declarado pelo checker sem declaração no módulo: builtin ou
        # namespace nativo. O motor resolve pelo nome (é o que o lowering faz hoje).
        if name in self._globals_scope and name not in self._toplevel_names:
            return Ref(storage=Storage.BUILTIN, decl=None, name=name)

        # Nome inexistente: o checker já reportou e o motor emite o panic site.
        return Ref(storage=Storage.UNRESOLVED, decl=None, name=name)

    # --- anotações e spans ---

    def _ann(self, expr: Expr) -> tuple[Ty | None, Ty | None]:
        return self._flow.get(expr), self._storage.get(expr)

    def _tok(self, token: Token) -> Span:
        return span_of_token_exact(token, self._source_path)

    def _span(self, node: object) -> Span | None:
        return node_span(node, self._memo)

    # --- instanciações genéricas ---

    def _add_instance(self, name: str, args: tuple[Ty, ...]) -> TInstance:
        key = (name, args)
        existing = self._instances.get(key)
        if existing is not None:
            return existing
        instance = TInstance(name=name, type_args=args)
        self._instances[key] = instance
        return instance

    def _call_instance(self, expr: Call) -> tuple[TInstance | None, TInstance | None]:
        fn_site = self._generic_instances.get(expr)
        fn_instance = None
        if fn_site is not None:
            fn_instance = self._add_instance(fn_site.name, fn_site.type_args)
        class_site = self._generic_class_sites.get(expr)
        class_instance = None
        if class_site is not None:
            class_instance = self._add_instance(class_site.name, class_site.args)
        return fn_instance, class_instance

    # --- funções ---

    def _function(
        self,
        node: FunctionNode,
        fn_id: FnId,
        name: str | None,
        params: list[Param],
        body: list[Stmt],
        *,
        is_method: bool,
        display_name: str,
    ) -> TFunction:
        # Defaults são expressões constantes (o checker recusa `default_not_constant`) e
        # o lowering as avalia no call site; converter fora da unidade mantém o escopo
        # léxico de quem declarou.
        default_exprs = tuple(
            self._expr(param.default) if param.default is not None else None for param in params
        )

        saved_unit = self._unit
        saved_method_class = self._method_class
        lexical_class = self._method_class
        unit = _Unit(id=fn_id, parent=saved_unit)
        self._unit = unit
        self._scopes.append({})
        try:
            this_decl: DeclId | None = None
            if is_method:
                this_decl = self._new_decl("this", None, False, DeclKind.THIS, self._span(node))
                self._declare("this", this_decl)
            thir_params = tuple(
                self._param(param, default)
                for param, default in zip(params, default_exprs, strict=True)
            )
            thir_body = tuple(self._stmt(statement) for statement in body)
        finally:
            self._scopes.pop()
            self._unit = saved_unit
            self._method_class = saved_method_class

        is_init = is_method and name == "init"
        return TFunction(
            id=fn_id,
            name=name,
            params=thir_params,
            body=thir_body,
            ret_ty=node.return_type,
            fn_ty=self._function_types.get(node),
            type_params=(
                tuple(token.lexeme for token in node.type_params)
                if isinstance(node, Function)
                else ()
            ),
            is_init=is_init,
            is_method=is_method,
            method_class=lexical_class,
            this_decl=this_decl,
            captures=unit.ordered(),
            display_name=display_name,
            decl_span=self._span(node),
        )

    def _param(self, param: Param, default: TExpr | None) -> TParam:
        decl = self._new_decl(
            param.name.lexeme,
            param.type_annotation,
            param.mutable,
            DeclKind.PARAM,
            self._tok(param.name),
        )
        self._declare(param.name.lexeme, decl)
        return TParam(
            decl=decl,
            name=param.name.lexeme,
            ty=param.type_annotation,
            default=default,
            variadic=param.variadic,
            mutable=param.mutable,
            span=self._tok(param.name),
        )

    def _named_decl(self, stmt: object, token: Token, kind: DeclKind) -> DeclId:
        """Reaproveita o `Decl` da pré-declaração de topo ou cria um novo."""
        existing = self._predeclared.get(stmt)
        if existing is not None:
            return existing
        decl = self._new_decl(token.lexeme, None, False, kind, self._tok(token))
        self._declare(token.lexeme, decl)
        return decl

    def _function_decl(self, stmt: Function) -> TFunction:
        decl = self._named_decl(stmt, stmt.name, DeclKind.FUNCTION)
        if stmt is self._entry_node:
            self._entry_id = decl
        return self._function(
            stmt,
            decl,
            stmt.name.lexeme,
            stmt.params,
            stmt.body,
            is_method=False,
            display_name=stmt.display_name or stmt.name.lexeme,
        )

    def _method(self, stmt: Function) -> TFunction:
        decl = self._new_decl(
            stmt.name.lexeme,
            None,
            False,
            DeclKind.FUNCTION,
            self._tok(stmt.name),
        )
        return self._function(
            stmt,
            decl,
            stmt.name.lexeme,
            stmt.params,
            stmt.body,
            is_method=True,
            display_name=stmt.display_name or stmt.name.lexeme,
        )

    # --- statements ---

    def _stmt(self, stmt: Stmt) -> TStmt:
        span = self._span(stmt)

        if isinstance(stmt, Expression):
            return TExprStmt(span=span, expression=self._expr(stmt.expression))

        if isinstance(stmt, Block):
            self._scopes.append({})
            try:
                body = tuple(self._stmt(statement) for statement in stmt.statements)
            finally:
                self._scopes.pop()
            return TBlock(span=span, body=body)

        if isinstance(stmt, Var):
            initializer = self._expr(stmt.initializer) if stmt.initializer is not None else None
            decl = self._new_decl(
                stmt.name.lexeme,
                stmt.type_annotation,
                stmt.mutable,
                DeclKind.VAR,
                self._tok(stmt.name),
            )
            self._declare(stmt.name.lexeme, decl)
            return TVarStmt(span=span, decl=decl, initializer=initializer)

        if isinstance(stmt, Destructure):
            initializer = self._expr(stmt.initializer)
            declared = stmt.type_annotation
            if declared is None:
                declared = initializer.storage_ty or initializer.ty
            pattern = self._destructure_pattern(stmt.pattern, declared, stmt.mutable)
            return TDestructureStmt(span=span, pattern=pattern, initializer=initializer)

        if isinstance(stmt, If):
            return TIf(
                span=span,
                condition=self._expr(stmt.condition),
                then_branch=self._stmt(stmt.then_branch),
                else_branch=(
                    self._stmt(stmt.else_branch) if stmt.else_branch is not None else None
                ),
            )

        if isinstance(stmt, While):
            return TWhile(
                span=span,
                condition=self._expr(stmt.condition),
                body=self._stmt(stmt.body),
            )

        if isinstance(stmt, ForIn):
            iterable = self._expr(stmt.iterable)
            self._scopes.append({})
            try:
                decl = self._new_decl(
                    stmt.name.lexeme, None, False, DeclKind.VAR, self._tok(stmt.name)
                )
                self._declare(stmt.name.lexeme, decl)
                loop_body = self._stmt(stmt.body)
            finally:
                self._scopes.pop()
            return TForIn(span=span, decl=decl, iterable=iterable, body=loop_body)

        if isinstance(stmt, Function):
            return TFnDecl(span=span, fn=self._function_decl(stmt))

        if isinstance(stmt, Return):
            return TReturn(
                span=span,
                value=self._expr(stmt.value) if stmt.value is not None else None,
            )

        if isinstance(stmt, Break):
            return TBreak(span=span)

        if isinstance(stmt, Continue):
            return TContinue(span=span)

        if isinstance(stmt, Class):
            return TClassDecl(span=span, klass=self._class(stmt))

        if isinstance(stmt, Interface):
            return TInterfaceDecl(span=span, interface=self._interface(stmt))

        if isinstance(stmt, EnumDecl):
            return TEnumDecl(span=span, enum=self._enum(stmt))

        if isinstance(stmt, Try):
            handlers: list[THandler] = []
            self._scopes.append({})
            try:
                body_stmts = tuple(self._stmt(statement) for statement in stmt.body)
            finally:
                self._scopes.pop()
            for handler in stmt.handlers:
                handler_span = self._span(handler)
                self._scopes.append({})
                try:
                    decl = self._new_decl(
                        handler.binding.lexeme,
                        None,
                        False,
                        DeclKind.HANDLER,
                        self._tok(handler.binding),
                    )
                    self._declare(handler.binding.lexeme, decl)
                    handler_body = tuple(self._stmt(s) for s in handler.body)
                finally:
                    self._scopes.pop()
                handlers.append(
                    THandler(
                        type_name=handler.type_name.lexeme,
                        decl=decl,
                        body=handler_body,
                        span=handler_span,
                    )
                )
            finally_body: tuple[TStmt, ...] | None = None
            if stmt.finally_body is not None:
                self._scopes.append({})
                try:
                    finally_body = tuple(self._stmt(s) for s in stmt.finally_body)
                finally:
                    self._scopes.pop()
            return TTry(
                span=span,
                body=body_stmts,
                handlers=tuple(handlers),
                finally_body=finally_body,
            )

        if isinstance(stmt, Raise):
            return TRaise(
                span=span,
                value=self._expr(stmt.value) if stmt.value is not None else None,
            )

        if isinstance(stmt, TypeAlias):
            return TTypeAlias(span=span, name=stmt.name.lexeme, target=stmt.target)

        if isinstance(stmt, (Import, ErrorStmt)):
            raise ThirBuildError(
                f"{type(stmt).__name__} reached the THIR producer; "
                "the loader resolves imports and the recovered tree never compiles"
            )

        raise ThirBuildError(f"unhandled statement: {type(stmt).__name__}")

    def _destructure_pattern(
        self, pattern: DestructurePattern, ty: Ty | None, mutable: bool
    ) -> TDestructurePattern:
        """Padrão de `val`/`var` com o aninhamento preservado e tipo por elemento.

        O motor precisa da forma do padrão para desestruturar posicionalmente e do tipo
        de cada nome (não do tipo da tupla inteira): copiar a anotação para todos os
        nomes daria slot com representação errada (`(Int, String)` em cada um).
        """
        span = self._span(pattern)
        if isinstance(pattern, NamePattern):
            decl = self._declare_pattern_name(pattern.name, ty, mutable)
            return TNamePattern(span=span, decl=decl)
        if isinstance(pattern, TuplePattern):
            item_types: tuple[Ty, ...] | None = None
            if isinstance(ty, TupleTy) and len(ty.items) == len(pattern.elements):
                item_types = ty.items
            elements = tuple(
                self._destructure_pattern(
                    element,
                    item_types[index] if item_types is not None else None,
                    mutable,
                )
                for index, element in enumerate(pattern.elements)
            )
            return TTuplePattern(span=span, elements=elements)
        raise ThirBuildError(f"unhandled destructuring pattern: {type(pattern).__name__}")

    def _declare_pattern_name(self, name: Token, ty: Ty | None, mutable: bool) -> DeclId:
        decl = self._new_decl(name.lexeme, ty, mutable, DeclKind.PATTERN, self._tok(name))
        self._declare(name.lexeme, decl)
        return decl

    # --- declarações compostas ---

    def _class(self, stmt: Class) -> TClass:
        decl = self._named_decl(stmt, stmt.name, DeclKind.CLASS)

        fields: list[TField] = []
        for field_ in stmt.fields:
            fields.append(self._field(field_))

        saved_method_class = self._method_class
        self._method_class = stmt.name.lexeme
        try:
            methods = tuple(self._method(method) for method in stmt.methods)
        finally:
            self._method_class = saved_method_class

        return TClass(
            decl=decl,
            name=stmt.name.lexeme,
            superclass=stmt.superclass.name.lexeme if stmt.superclass is not None else None,
            superclass_span=(
                self._tok(stmt.superclass.name) if stmt.superclass is not None else None
            ),
            interfaces=tuple(token.lexeme for token in stmt.implements),
            type_params=tuple(token.lexeme for token in stmt.type_params),
            fields=tuple(fields),
            methods=methods,
            display_name=stmt.display_name or stmt.name.lexeme,
            span=self._span(stmt),
        )

    def _field(self, field_: Field) -> TField:
        decl = self._new_decl(
            field_.name.lexeme,
            field_.type_annotation,
            field_.mutable,
            DeclKind.VAR,
            self._tok(field_.name),
        )
        initializer = self._expr(field_.initializer) if field_.initializer is not None else None
        return TField(
            decl=decl,
            name=field_.name.lexeme,
            ty=field_.type_annotation,
            mutable=field_.mutable,
            initializer=initializer,
            span=self._tok(field_.name),
        )

    def _interface(self, stmt: Interface) -> TInterface:
        decl = self._named_decl(stmt, stmt.name, DeclKind.INTERFACE)
        saved_method_class = self._method_class
        self._method_class = stmt.name.lexeme
        try:
            methods = tuple(self._method(method) for method in stmt.methods)
        finally:
            self._method_class = saved_method_class
        return TInterface(
            decl=decl,
            name=stmt.name.lexeme,
            methods=methods,
            display_name=stmt.display_name or stmt.name.lexeme,
            span=self._span(stmt),
        )

    def _enum(self, stmt: EnumDecl) -> TEnum:
        decl = self._named_decl(stmt, stmt.name, DeclKind.ENUM)
        variants = tuple(
            TEnumVariant(
                name=variant.name.lexeme,
                payload=tuple(variant.payload),
                span=self._tok(variant.name),
            )
            for variant in stmt.variants
        )
        return TEnum(
            decl=decl,
            name=stmt.name.lexeme,
            type_params=tuple(token.lexeme for token in stmt.type_params),
            variants=variants,
            display_name=stmt.display_name or stmt.name.lexeme,
            span=self._span(stmt),
        )

    # --- expressões ---

    def _expr(self, expr: Expr) -> TExpr:
        flow, storage = self._ann(expr)
        span = self._span(expr)

        if isinstance(expr, Literal):
            return TConst(ty=flow, storage_ty=storage, span=span, value=expr.value)

        if isinstance(expr, Grouping):
            # Parênteses são sintaxe: o nó não sobrevive ao THIR (ADR-0149 §2).
            return self._expr(expr.expression)

        if isinstance(expr, Variable):
            return TVar(ty=flow, storage_ty=storage, span=span, ref=self._use(expr.name.lexeme))

        if isinstance(expr, Assign):
            return TAssign(
                ty=flow,
                storage_ty=storage,
                span=span,
                ref=self._use(expr.name.lexeme),
                name_span=self._tok(expr.name),
                value=self._expr(expr.value),
            )

        if isinstance(expr, Unary):
            return TUnary(
                ty=flow,
                storage_ty=storage,
                span=span,
                op=expr.operator.type,
                op_span=self._tok(expr.operator),
                operand=self._expr(expr.right),
            )

        if isinstance(expr, Binary):
            return TBinary(
                ty=flow,
                storage_ty=storage,
                span=span,
                op=expr.operator.type,
                op_span=self._tok(expr.operator),
                left=self._expr(expr.left),
                right=self._expr(expr.right),
            )

        if isinstance(expr, Logical):
            return TLogical(
                ty=flow,
                storage_ty=storage,
                span=span,
                op=expr.operator.type,
                op_span=self._tok(expr.operator),
                left=self._expr(expr.left),
                right=self._expr(expr.right),
            )

        if isinstance(expr, Conditional):
            return TConditional(
                ty=flow,
                storage_ty=storage,
                span=span,
                condition=self._expr(expr.condition),
                then_branch=self._expr(expr.then_branch),
                else_branch=self._expr(expr.else_branch),
            )

        if isinstance(expr, InterpolatedString):
            parts: list[str | TExpr] = [
                part if isinstance(part, str) else self._expr(part) for part in expr.parts
            ]
            return TInterp(ty=flow, storage_ty=storage, span=span, parts=tuple(parts))

        if isinstance(expr, ListLiteral):
            return TList(
                ty=flow,
                storage_ty=storage,
                span=span,
                items=tuple(self._expr(item) for item in expr.elements),
            )

        if isinstance(expr, MapLiteral):
            return TMap(
                ty=flow,
                storage_ty=storage,
                span=span,
                entries=tuple((self._expr(key), self._expr(value)) for key, value in expr.entries),
            )

        if isinstance(expr, TupleLiteral):
            return TTuple(
                ty=flow,
                storage_ty=storage,
                span=span,
                items=tuple(self._expr(item) for item in expr.elements),
            )

        if isinstance(expr, Range):
            return TRange(
                ty=flow,
                storage_ty=storage,
                span=span,
                op_span=self._tok(expr.operator),
                start=self._expr(expr.start),
                end=self._expr(expr.end),
                inclusive=expr.inclusive,
            )

        if isinstance(expr, Call):
            fn_instance, class_instance = self._call_instance(expr)
            return TCall(
                ty=flow,
                storage_ty=storage,
                span=span,
                callee=self._expr(expr.callee),
                arguments=tuple(self._expr(argument) for argument in expr.arguments),
                paren_span=self._tok(expr.paren),
                optional=expr.optional,
                spread=expr.spread,
                instance=fn_instance,
                class_instance=class_instance,
            )

        if isinstance(expr, Get):
            return TGet(
                ty=flow,
                storage_ty=storage,
                span=span,
                receiver=self._expr(expr.object),
                name=expr.name.lexeme,
                name_span=self._tok(expr.name),
                optional=expr.optional,
            )

        if isinstance(expr, Set):
            return TSet(
                ty=flow,
                storage_ty=storage,
                span=span,
                receiver=self._expr(expr.object),
                name=expr.name.lexeme,
                name_span=self._tok(expr.name),
                value=self._expr(expr.value),
            )

        if isinstance(expr, Index):
            return TIndex(
                ty=flow,
                storage_ty=storage,
                span=span,
                receiver=self._expr(expr.object),
                index=self._expr(expr.index),
                bracket_span=self._tok(expr.bracket),
            )

        if isinstance(expr, IndexSet):
            return TIndexSet(
                ty=flow,
                storage_ty=storage,
                span=span,
                receiver=self._expr(expr.object),
                index=self._expr(expr.index),
                value=self._expr(expr.value),
                bracket_span=self._tok(expr.bracket),
            )

        if isinstance(expr, This):
            return TThis(ty=flow, storage_ty=storage, span=span, ref=self._use("this"))

        if isinstance(expr, Super):
            return TSuper(
                ty=flow,
                storage_ty=storage,
                span=span,
                method=expr.method.lexeme,
                method_span=self._tok(expr.method),
                receiver=self._use("this"),
            )

        if isinstance(expr, Is):
            return TIs(
                ty=flow,
                storage_ty=storage,
                span=span,
                op_span=self._tok(expr.operator),
                operand=self._expr(expr.left),
                test_type=expr.test_type,
            )

        if isinstance(expr, As):
            return TAs(
                ty=flow,
                storage_ty=storage,
                span=span,
                op_span=self._tok(expr.operator),
                operand=self._expr(expr.left),
                target_type=expr.target_type,
            )

        if isinstance(expr, Match):
            return TMatch(
                ty=flow,
                storage_ty=storage,
                span=span,
                scrutinee=self._expr(expr.scrutinee),
                arms=tuple(self._arm(arm.pattern, arm.body, arm) for arm in expr.arms),
            )

        if isinstance(expr, Lambda):
            decl = self._new_decl("<lambda>", None, False, DeclKind.LAMBDA, span)
            return TLambda(
                ty=flow,
                storage_ty=storage,
                span=span,
                fn=self._function(
                    expr,
                    decl,
                    None,
                    expr.params,
                    expr.body,
                    is_method=False,
                    display_name="<lambda>",
                ),
            )

        if isinstance(expr, ErrorExpr):
            raise ThirBuildError("ErrorExpr reached the THIR producer")

        raise ThirBuildError(f"unhandled expression: {type(expr).__name__}")

    def _arm(self, pattern: Pattern, body: Expr, arm: MatchArm) -> TMatchArm:
        self._scopes.append({})
        try:
            thir_pattern = self._pattern(pattern)
            thir_body = self._expr(body)
        finally:
            self._scopes.pop()
        return TMatchArm(span=self._span(arm), pattern=thir_pattern, body=thir_body)

    def _pattern(self, pattern: Pattern) -> TPattern:
        span = self._span(pattern)
        if isinstance(pattern, VariantPattern):
            bindings = tuple(
                self._declare_pattern_name(token, None, False) for token in pattern.bindings
            )
            return TVariantPattern(
                span=span,
                enum=pattern.enum.lexeme,
                variant=pattern.variant.lexeme,
                bindings=bindings,
            )
        if isinstance(pattern, WildcardPattern):
            return TWildcardPattern(span=span)
        if isinstance(pattern, LiteralPattern):
            return TLiteralPattern(span=span, value=pattern.value)
        raise ThirBuildError(f"unhandled pattern: {type(pattern).__name__}")


def build_thir(
    statements: list[Stmt],
    *,
    storage_types: dict[Expr, Ty],
    flow_types: dict[Expr, Ty] | None = None,
    generic_instances: dict[Call, Any] | None = None,
    generic_classes: Iterable[ClassTy] = (),
    generic_class_sites: dict[Call, ClassTy] | None = None,
    type_aliases: dict[str, Ty] | None = None,
    function_types: dict[Any, FnTy] | None = None,
    entry: Function | None = None,
    globals_scope: dict[str, Ty] | None = None,
    source_path: str = "<lox>",
) -> TModule:
    """Constrói o THIR de um programa já resolvido e checado."""
    builder = _Builder(
        storage_types=storage_types,
        flow_types=flow_types,
        generic_instances=generic_instances,
        generic_classes=generic_classes,
        generic_class_sites=generic_class_sites,
        type_aliases=type_aliases,
        function_types=function_types,
        entry=entry,
        globals_scope=globals_scope,
        source_path=source_path,
    )
    return builder.build(statements)
