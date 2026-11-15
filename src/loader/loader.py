"""Loader de módulos: arquivo = módulo, pasta = namespace (ADR-0073)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from src.diagnostics.codes import Code
from src.diagnostics.error_reporter import ErrorReporter
from src.diagnostics.source import SourceMap
from src.frontend.destructuring import NamePattern, TuplePattern
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
    Range,
    Set,
    Super,
    This,
    TupleLiteral,
    Unary,
    Variable,
    VariantPattern,
)
from src.frontend.parser import Parser
from src.frontend.scanner import Scanner
from src.frontend.stmt import (
    Block,
    Class,
    Destructure,
    EnumDecl,
    Expression,
    ForIn,
    Function,
    If,
    Import,
    Interface,
    Raise,
    Return,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token
from src.frontend.ty import (
    ClassObjectTy,
    ClassTy,
    EnumObjectTy,
    EnumTy,
    FnTy,
    InterfaceTy,
    ListTy,
    MapTy,
    TupleTy,
    Ty,
    UnionTy,
)

STD_ROOT = Path(__file__).resolve().parents[2] / "std"

# Extensão canônica dos fontes da linguagem (ADR-0078). Um só lugar: o loader é quem
# transforma `import a.b` no caminho `a/b.lx`.
SOURCE_SUFFIX = ".lx"


class ModuleError(Exception):
    """Falha de resolução de módulo; o reporter já tem o diagnóstico."""


@dataclass
class Module:
    name: str
    path: Path
    statements: list[Stmt]
    imports: list[Import]
    declarations: dict[str, Stmt]
    dependencies: list[str]


class ModuleLoader:
    def __init__(
        self,
        reporter: ErrorReporter,
        sources: SourceMap,
        root: Path,
    ) -> None:
        self.reporter = reporter
        self.sources = sources
        self.root = root
        self.modules: dict[str, Module] = {}
        self._loading: set[str] = set()
        self._order: list[str] = []

    # -- entrada ---------------------------------------------------------

    def load(self, entry: list[Stmt], entry_file: str) -> list[Stmt] | None:
        entry_imports = self._entry_imports(entry, entry_file)
        try:
            for statement in entry_imports:
                self._load_import(statement)
            import_maps = self._import_maps(entry_imports)
            public_maps = {
                name: self._declaration_map(module)
                for name, module in self.modules.items()
            }
            rewritten: list[Stmt] = []
            for name in self._order:
                module = self.modules[name]
                rewriter = _Rewriter(
                    import_maps.get(name, _ImportMaps({}, {})),
                    public_maps[name],
                    self,
                )
                for module_statement in module.statements:
                    if not isinstance(module_statement, Import):
                        rewritten.append(rewriter.stmt(module_statement))
            entry_rewriter = _Rewriter(import_maps["<entry>"], {}, self)
            for entry_statement in entry:
                if not isinstance(entry_statement, Import):
                    rewritten.append(entry_rewriter.stmt(entry_statement))
            return rewritten
        except ModuleError:
            return None

    def _entry_imports(self, entry: list[Stmt], entry_file: str) -> list[Import]:
        imports: list[Import] = []
        seen_declaration = False
        for statement in entry:
            if isinstance(statement, Import):
                if seen_declaration:
                    self._error(
                        statement.path[0],
                        "Imports must appear before other statements.",
                    )
                imports.append(statement)
            else:
                seen_declaration = True
        return imports

    # -- carregamento ----------------------------------------------------

    def _load_import(self, statement: Import) -> None:
        target = self._resolve(statement.path, statement.path[0])
        self._load_module(target, statement.path[0])

    def _resolve(self, path: tuple[Token, ...], token: Token) -> tuple[str, Path]:
        parts = [item.lexeme for item in path]
        if parts[0] == "std":
            if len(parts) < 2:
                self._error(token, "Expect a module name after 'std'.")
            name = "std." + ".".join(parts[1:])
            file = STD_ROOT.joinpath(*parts[1:]).with_suffix(SOURCE_SUFFIX)
        else:
            name = ".".join(parts)
            file = self.root.joinpath(*parts).with_suffix(SOURCE_SUFFIX)
        if not file.is_file():
            self._error(token, f"Module '{name}' not found.")
        return name, file

    def _load_module(self, target: tuple[str, Path], token: Token) -> None:
        name, path = target
        if name in self._loading:
            self._error(token, f"Import cycle involving '{name}'.")
        if name in self.modules:
            return
        self._loading.add(name)
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            self._error(token, f"Can't read module '{name}'.")
        display = (
            path.relative_to(self.root).as_posix()
            if path.is_relative_to(self.root)
            else path.name
        )
        self.sources.add(display, source)
        previous = self.reporter.file
        self.reporter.file = display
        try:
            scanner = Scanner(source, self.reporter)
            statements = Parser(scanner.scan_tokens(), reporter=self.reporter).parse()
        finally:
            self.reporter.file = previous
        if statements is None or self.reporter.had_error:
            raise ModuleError()

        imports: list[Import] = []
        declarations: dict[str, Stmt] = {}
        seen_non_import = False
        for statement in statements:
            if isinstance(statement, Import):
                if seen_non_import:
                    self._error(
                        statement.path[0],
                        "Imports must appear before declarations.",
                    )
                imports.append(statement)
                continue
            seen_non_import = True
            if not isinstance(statement, (Function, Class, EnumDecl, Interface, TypeAlias)):
                self._error(
                    _first_token(statement),
                    "Modules may contain only imports, functions, classes, "
                    "interfaces, enums and type aliases.",
                )
            assert isinstance(statement, (Function, Class, EnumDecl, Interface, TypeAlias))
            decl_name = statement.name.lexeme
            if decl_name in declarations:
                self._error(statement.name, f"Duplicate declaration '{decl_name}'.")
            declarations[decl_name] = statement
        for statement in statements:
            self._reject_nested_imports(statement)
        module = Module(name, path, statements, imports, declarations, [])
        self.modules[name] = module
        for statement in imports:
            target_import = self._resolve(statement.path, statement.path[0])
            module.dependencies.append(target_import[0])
            self._load_module(target_import, statement.path[0])
        self._loading.remove(name)
        self._order.append(name)

    def _entry_root(self) -> Path:
        return self.root

    def _reject_nested_imports(self, statement: Stmt) -> None:
        for value in vars(statement).values():
            items = value if isinstance(value, list) else [value]
            for item in items:
                if isinstance(item, Import):
                    self._error(
                        item.path[0], "Imports must appear at the top level."
                    )
                if hasattr(item, "accept"):
                    self._reject_nested_imports(item)

    # -- mapas -----------------------------------------------------------

    def _declaration_map(self, module: Module) -> dict[str, str]:
        prefix = module.name.replace(".", "$")
        return {
            name: f"{prefix}${name}"
            for name in module.declarations
        }

    def _import_maps(self, entry_imports: list[Import]) -> dict[str, _ImportMaps]:
        result: dict[str, _ImportMaps] = {"<entry>": self._build_import_map(entry_imports)}
        for name, module in self.modules.items():
            result[name] = self._build_import_map(module.imports)
        return result

    def _build_import_map(self, imports: list[Import]) -> _ImportMaps:
        names: dict[str, str] = {}
        namespaces: dict[str, Module] = {}
        for statement in imports:
            target_name, _ = self._resolve(statement.path, statement.path[0])
            module = self.modules[target_name]
            if statement.from_import:
                for item in statement.names:
                    public = item.name.lexeme
                    if public.startswith("_"):
                        self._error(
                            item.name,
                            f"Can't import private name '{public}' from "
                            f"'{target_name}'.",
                        )
                    if public not in module.declarations:
                        self._error(
                            item.name,
                            f"Module '{target_name}' has no public name '{public}'.",
                        )
                    local = (item.alias or item.name).lexeme
                    if local in names or local in namespaces:
                        self._error(item.alias or item.name, f"Duplicate import '{local}'.")
                    names[local] = (
                        f"{target_name.replace('.', '$')}${public}"
                    )
            else:
                alias = statement.alias or statement.path[-1]
                if alias.lexeme in names or alias.lexeme in namespaces:
                    self._error(alias, f"Duplicate import '{alias.lexeme}'.")
                namespaces[alias.lexeme] = module
        return _ImportMaps(names, namespaces)

    # -- erros -----------------------------------------------------------

    def _error(self, token: Token, message: str) -> None:
        self.reporter.error(token, message, code=Code.SYNTAX_UNEXPECTED)
        raise ModuleError()


@dataclass
class _ImportMaps:
    names: dict[str, str]
    namespaces: dict[str, Module]


class _Rewriter:
    def __init__(
        self,
        imports: _ImportMaps,
        declarations: dict[str, str],
        loader: ModuleLoader,
    ) -> None:
        self.imports = imports
        self.declarations = declarations
        self.loader = loader
        self.bound: list[set[str]] = []

    # -- helpers ---------------------------------------------------------

    def _is_local(self, name: str) -> bool:
        return any(name in scope for scope in reversed(self.bound))

    def _global(self, name: str, token: Token) -> str | None:
        if name in self.imports.names:
            return self.imports.names[name]
        return self.declarations.get(name)

    def _rename_token(self, token: Token, name: str) -> Token:
        return Token(token.type, name, token.literal, token.line)

    def _var(self, expr: Variable) -> Expr:
        if self._is_local(expr.name.lexeme):
            return expr
        replacement = self._global(expr.name.lexeme, expr.name)
        if replacement is not None:
            return Variable(self._rename_token(expr.name, replacement))
        return expr

    def _type_param_bounds(
        self, bounds: list[tuple[Token, ...]]
    ) -> list[tuple[Token, ...]]:
        renamed: list[tuple[Token, ...]] = []
        for group in bounds:
            items: list[Token] = []
            for token in group:
                replacement = self._global(token.lexeme, token)
                items.append(
                    self._rename_token(token, replacement)
                    if replacement is not None
                    else token
                )
            renamed.append(tuple(items))
        return renamed

    def _type(self, ty: Ty | None) -> Ty | None:
        if ty is None:
            return None
        if isinstance(ty, ClassTy):
            name = self._global(ty.name, Token(TokenType.IDENTIFIER, ty.name, None, 0)) or ty.name
            args = tuple(self._type(arg) for arg in ty.args)
            assert all(arg is not None for arg in args)
            return replace(ty, name=name, args=args)  # type: ignore[arg-type]
        if isinstance(ty, EnumTy):
            name = self._global(ty.name, Token(TokenType.IDENTIFIER, ty.name, None, 0)) or ty.name
            args = tuple(self._type(arg) for arg in ty.args)
            assert all(arg is not None for arg in args)
            return replace(ty, name=name, args=args)  # type: ignore[arg-type]
        if isinstance(ty, InterfaceTy):
            return replace(
                ty,
                name=self._global(
                    ty.name, Token(TokenType.IDENTIFIER, ty.name, None, 0)
                )
                or ty.name,
            )
        if isinstance(ty, ClassObjectTy):
            return replace(
                ty, name=self._global(ty.name, Token(TokenType.IDENTIFIER, ty.name, None, 0)) or ty.name
            )
        if isinstance(ty, EnumObjectTy):
            return replace(
                ty, name=self._global(ty.name, Token(TokenType.IDENTIFIER, ty.name, None, 0)) or ty.name
            )
        if isinstance(ty, ListTy):
            element = self._type(ty.element)
            assert element is not None
            return replace(ty, element=element)
        if isinstance(ty, MapTy):
            key = self._type(ty.key)
            value = self._type(ty.value)
            assert key is not None and value is not None
            return replace(ty, key=key, value=value)
        if isinstance(ty, TupleTy):
            items = tuple(self._type(item) for item in ty.items)
            assert all(item is not None for item in items)
            return replace(ty, items=items)  # type: ignore[arg-type]
        if isinstance(ty, UnionTy):
            members = tuple(self._type(item) for item in ty.members)
            assert all(item is not None for item in members)
            return replace(ty, members=members)  # type: ignore[arg-type]
        if isinstance(ty, FnTy):
            params = tuple(self._type(item) for item in ty.params)
            ret = self._type(ty.ret)
            assert all(item is not None for item in params) and ret is not None
            return replace(ty, params=params, ret=ret)  # type: ignore[arg-type]
        return ty

    # -- expressões ------------------------------------------------------

    def expr(self, expr: Expr) -> Expr:
        if isinstance(expr, Variable):
            return self._var(expr)
        if isinstance(expr, Get):
            if (
                isinstance(expr.object, Variable)
                and not self._is_local(expr.object.name.lexeme)
                and expr.object.name.lexeme in self.imports.namespaces
            ):
                module = self.imports.namespaces[expr.object.name.lexeme]
                member = expr.name.lexeme
                if member.startswith("_"):
                    self.loader._error(
                        expr.name,
                        f"Can't access private name '{member}' from "
                        f"'{module.name}'.",
                    )
                if member not in module.declarations:
                    self.loader._error(
                        expr.name,
                        f"Module '{module.name}' has no public name '{member}'.",
                    )
                return Variable(
                    self._rename_token(
                        expr.name, f"{module.name.replace('.', '$')}${member}"
                    )
                )
            return replace(expr, object=self.expr(expr.object))
        if isinstance(expr, Assign):
            name = expr.name
            if not self._is_local(name.lexeme):
                replacement = self._global(name.lexeme, name)
                if replacement is not None:
                    name = self._rename_token(name, replacement)
            return replace(expr, name=name, value=self.expr(expr.value))
        if isinstance(expr, Binary):
            return replace(
                expr, left=self.expr(expr.left), right=self.expr(expr.right)
            )
        if isinstance(expr, Grouping):
            return replace(expr, expression=self.expr(expr.expression))
        if isinstance(expr, Unary):
            return replace(expr, right=self.expr(expr.right))
        if isinstance(expr, Logical):
            return replace(
                expr, left=self.expr(expr.left), right=self.expr(expr.right)
            )
        if isinstance(expr, Conditional):
            return replace(
                expr,
                condition=self.expr(expr.condition),
                then_branch=self.expr(expr.then_branch),
                else_branch=self.expr(expr.else_branch),
            )
        if isinstance(expr, Call):
            return replace(
                expr,
                callee=self.expr(expr.callee),
                arguments=[self.expr(arg) for arg in expr.arguments],
            )
        if isinstance(expr, Set):
            return replace(
                expr,
                object=self.expr(expr.object),
                value=self.expr(expr.value),
            )
        if isinstance(expr, Index):
            return replace(
                expr,
                object=self.expr(expr.object),
                index=self.expr(expr.index),
            )
        if isinstance(expr, IndexSet):
            return replace(
                expr,
                object=self.expr(expr.object),
                index=self.expr(expr.index),
                value=self.expr(expr.value),
            )
        if isinstance(expr, ListLiteral):
            return replace(expr, elements=[self.expr(item) for item in expr.elements])
        if isinstance(expr, MapLiteral):
            return replace(
                expr,
                entries=[
                    (self.expr(key), self.expr(value))
                    for key, value in expr.entries
                ],
            )
        if isinstance(expr, TupleLiteral):
            return replace(expr, elements=[self.expr(item) for item in expr.elements])
        if isinstance(expr, InterpolatedString):
            return replace(
                expr,
                parts=[
                    part if isinstance(part, str) else self.expr(part)
                    for part in expr.parts
                ],
            )
        if isinstance(expr, Is):
            return replace(
                expr,
                left=self.expr(expr.left),
                test_type=self._type(expr.test_type) or expr.test_type,
            )
        if isinstance(expr, As):
            return replace(
                expr,
                left=self.expr(expr.left),
                target_type=self._type(expr.target_type) or expr.target_type,
            )
        if isinstance(expr, Range):
            return replace(
                expr, start=self.expr(expr.start), end=self.expr(expr.end)
            )
        if isinstance(expr, Lambda):
            self.bound.append({param.name.lexeme for param in expr.params})
            try:
                return replace(
                    expr,
                    params=[
                        replace(
                            param,
                            default=self.expr(param.default)
                            if param.default is not None
                            else None,
                            type_annotation=self._type(param.type_annotation),
                        )
                        for param in expr.params
                    ],
                    body=[self.stmt(item) for item in expr.body],
                )
            finally:
                self.bound.pop()
        if isinstance(expr, Match):
            arms = []
            for arm in expr.arms:
                pattern = arm.pattern
                bindings: set[str] = set()
                if isinstance(pattern, VariantPattern):
                    bindings = {token.lexeme for token in pattern.bindings}
                    enum_name = pattern.enum.lexeme
                    replacement = self._global(enum_name, pattern.enum)
                    if replacement is not None:
                        pattern = replace(
                            pattern,
                            enum=self._rename_token(pattern.enum, replacement),
                        )
                self.bound.append(bindings)
                try:
                    arms.append(replace(arm, pattern=pattern, body=self.expr(arm.body)))
                finally:
                    self.bound.pop()
            return replace(expr, scrutinee=self.expr(expr.scrutinee), arms=arms)
        if isinstance(expr, (Literal, This, Super)):
            return expr
        return expr

    # -- statements ------------------------------------------------------

    def stmt(self, statement: Stmt) -> Stmt:
        if isinstance(statement, Import):
            return statement
        if isinstance(statement, Expression):
            return replace(statement, expression=self.expr(statement.expression))
        if isinstance(statement, Var):
            value = (
                self.expr(statement.initializer)
                if statement.initializer is not None
                else None
            )
            result = replace(
                statement,
                initializer=value,
                type_annotation=self._type(statement.type_annotation),
            )
            self.bound[-1].add(statement.name.lexeme) if self.bound else None
            return result
        if isinstance(statement, Block):
            self.bound.append(set())
            try:
                return replace(
                    statement, statements=[self.stmt(item) for item in statement.statements]
                )
            finally:
                self.bound.pop()
        if isinstance(statement, If):
            return replace(
                statement,
                condition=self.expr(statement.condition),
                then_branch=self.stmt(statement.then_branch),
                else_branch=(
                    self.stmt(statement.else_branch)
                    if statement.else_branch is not None
                    else None
                ),
            )
        if isinstance(statement, While):
            return replace(
                statement,
                condition=self.expr(statement.condition),
                body=self.stmt(statement.body),
            )
        if isinstance(statement, ForIn):
            iterable = self.expr(statement.iterable)
            self.bound.append({statement.name.lexeme})
            try:
                body = self.stmt(statement.body)
            finally:
                self.bound.pop()
            return replace(statement, iterable=iterable, body=body)
        if isinstance(statement, TypeAlias):
            name = statement.name
            replacement = self._global(name.lexeme, name)
            if replacement is not None:
                name = self._rename_token(name, replacement)
            target = self._type(statement.target)
            assert target is not None
            return replace(
                statement,
                name=name,
                target=target,
            )
        if isinstance(statement, Function):
            name = statement.name
            replacement = self._global(name.lexeme, name)
            if replacement is not None:
                name = self._rename_token(name, replacement)
            self.bound.append({param.name.lexeme for param in statement.params})
            try:
                params = [
                    replace(
                        param,
                        default=self.expr(param.default)
                        if param.default is not None
                        else None,
                        type_annotation=self._type(param.type_annotation),
                    )
                    for param in statement.params
                ]
                function_body = [self.stmt(item) for item in statement.body]
            finally:
                self.bound.pop()
            return replace(
                statement,
                name=name,
                params=params,
                body=function_body,
                return_type=self._type(statement.return_type),
                type_param_bounds=self._type_param_bounds(
                    statement.type_param_bounds
                ),
                display_name=statement.display_name or statement.name.lexeme,
            )
        if isinstance(statement, Return):
            return replace(
                statement,
                value=self.expr(statement.value)
                if statement.value is not None
                else None,
            )
        if isinstance(statement, Class):
            name = statement.name
            replacement = self._global(name.lexeme, name)
            if replacement is not None:
                name = self._rename_token(name, replacement)
            superclass = (
                self.expr(statement.superclass)
                if statement.superclass is not None
                else None
            )
            fields = [
                replace(
                    field,
                    initializer=(
                        self.expr(field.initializer)
                        if field.initializer is not None
                        else None
                    ),
                    type_annotation=self._type(field.type_annotation),
                )
                for field in statement.fields
            ]
            methods = []
            for method in statement.methods:
                self.bound.append({param.name.lexeme for param in method.params})
                try:
                    methods.append(
                        replace(
                            method,
                            params=[
                                replace(
                                    param,
                                    default=(
                                        self.expr(param.default)
                                        if param.default is not None
                                        else None
                                    ),
                                    type_annotation=self._type(param.type_annotation),
                                )
                                for param in method.params
                            ],
                            body=[self.stmt(item) for item in method.body],
                            return_type=self._type(method.return_type),
                        )
                    )
                finally:
                    self.bound.pop()
            implements = []
            for token in statement.implements:
                replacement = self._global(token.lexeme, token)
                implements.append(
                    self._rename_token(token, replacement)
                    if replacement is not None
                    else token
                )

            return replace(
                statement,
                name=name,
                superclass=superclass,  # type: ignore[arg-type]
                fields=fields,
                methods=methods,
                implements=implements,
                display_name=statement.display_name or statement.name.lexeme,
            )
        if isinstance(statement, Interface):
            name = statement.name
            replacement = self._global(name.lexeme, name)
            if replacement is not None:
                name = self._rename_token(name, replacement)

            methods = []
            for method in statement.methods:
                self.bound.append({param.name.lexeme for param in method.params})
                try:
                    methods.append(
                        replace(
                            method,
                            params=[
                                replace(
                                    param,
                                    default=(
                                        self.expr(param.default)
                                        if param.default is not None
                                        else None
                                    ),
                                    type_annotation=self._type(param.type_annotation),
                                )
                                for param in method.params
                            ],
                            body=(
                                []
                                if method.abstract
                                else [self.stmt(item) for item in method.body]
                            ),
                            return_type=self._type(method.return_type),
                        )
                    )
                finally:
                    self.bound.pop()
            return replace(
                statement,
                name=name,
                methods=methods,
                display_name=statement.display_name or statement.name.lexeme,
            )
        if isinstance(statement, EnumDecl):
            name = statement.name
            replacement = self._global(name.lexeme, name)
            if replacement is not None:
                name = self._rename_token(name, replacement)
            variants = [
                replace(
                    variant,
                    payload=[
                        self._type(item)  # type: ignore[misc]
                        for item in variant.payload
                    ],
                )
                for variant in statement.variants
            ]
            return replace(
                statement,
                name=name,
                variants=variants,
                display_name=statement.display_name or statement.name.lexeme,
            )
        if isinstance(statement, Destructure):
            names = _pattern_names(statement.pattern)
            initializer = self.expr(statement.initializer)
            destructure = replace(
                statement,
                initializer=initializer,
                type_annotation=self._type(statement.type_annotation),
            )
            if self.bound:
                self.bound[-1].update(names)
            return destructure
        if isinstance(statement, Try):
            self.bound.append(set())
            try:
                try_body = [self.stmt(item) for item in statement.body]
                handlers = []
                for clause in statement.handlers:
                    type_name = clause.type_name
                    replacement = self._global(type_name.lexeme, type_name)
                    if replacement is not None:
                        type_name = self._rename_token(type_name, replacement)
                    self.bound[-1].add(clause.binding.lexeme)
                    handlers.append(
                        replace(
                            clause,
                            type_name=type_name,
                            body=[self.stmt(item) for item in clause.body],
                        )
                    )
                finally_body = (
                    [self.stmt(item) for item in statement.finally_body]
                    if statement.finally_body is not None
                    else None
                )
            finally:
                self.bound.pop()
            return replace(
                statement,
                body=try_body,
                handlers=handlers,
                finally_body=finally_body,
            )
        if isinstance(statement, Raise):
            return replace(
                statement,
                value=self.expr(statement.value)
                if statement.value is not None
                else None,
            )
        return statement


def _pattern_names(pattern: Any) -> set[str]:
    if isinstance(pattern, NamePattern):
        return {pattern.name.lexeme}
    if isinstance(pattern, TuplePattern):
        result: set[str] = set()
        for item in pattern.elements:
            result |= _pattern_names(item)
        return result
    return set()


def _first_token(statement: Stmt) -> Token:
    for field in ("name", "keyword"):
        token = getattr(statement, field, None)
        if isinstance(token, Token):
            return token
    return Token(TokenType.IDENTIFIER, "<module>", None, 0)
