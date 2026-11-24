# SPDX-License-Identifier: MIT OR Apache-2.0
"""Type checker estático (gradual) — roda depois do resolver, antes de executar.

Anotações são opcionais no runtime; em `--check` as funções precisam de parâmetros e
retorno anotados. Tipos são apagados: o interpretador continua dinâmico.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field, fields, is_dataclass

from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.diagnostic import (
    Applicability,
    Edit,
    Fix,
    Span,
)
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.execution.bytes_api import BYTES_METHODS, BYTES_STATICS
from loxia_core.execution.prelude import BUILTIN_NAMES
from loxia_core.execution.primitives import PRIMITIVES
from loxia_core.frontend.destructuring import (
    DestructurePattern,
    NamePattern,
    first_token,
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
    WildcardPattern,
)
from loxia_core.frontend.expr import Visitor as ExprVisitor
from loxia_core.frontend.source_index import SourceIndex
from loxia_core.frontend.spans import span_of_token
from loxia_core.frontend.stmt import (
    Block,
    Class,
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
    Raise,
    Return,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from loxia_core.frontend.stmt import Visitor as StmtVisitor
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import (
    ANY,
    BOOL,
    BYTES,
    ERROR,
    FLOAT,
    INT,
    NEVER,
    NIL,
    RANGE,
    STRING,
    ClassObjectTy,
    ClassTy,
    EnumObjectTy,
    EnumTy,
    FnTy,
    GenericFnTy,
    InterfaceTy,
    ListTy,
    MapTy,
    NativeFnTy,
    NativeModuleTy,
    TupleTy,
    Ty,
    TyVar,
    UnionTy,
    display,
    falsy,
    is_nilable,
    non_nil,
    truthy,
    union,
)

RESERVED_TYPE_PARAM_NAMES = frozenset(
    {
        "Any",
        "Bool",
        "Float",
        "Int",
        "List",
        "Map",
        "Bytes",
        "BytesError",
        "Never",
        "Nil",
        "Num",
        "Ord",
        "Range",
        "String",
    }
)

BUILTIN_CONSTRAINTS = frozenset({"Ord", "Num"})
ORD_TYPES: tuple[Ty, ...] = (INT, FLOAT, STRING)
NUM_TYPES: tuple[Ty, ...] = (INT, FLOAT)


@dataclass
class FieldBinding:
    ty: Ty
    mutable: bool
    token: Token


@dataclass
class ClassInfo:
    name: str
    superclass: str | None
    fields: dict[str, FieldBinding] = field(default_factory=dict)
    methods: dict[str, FnTy] = field(default_factory=dict)
    method_tokens: dict[str, Token] = field(default_factory=dict)
    init: FnTy | None = None
    type_params: tuple[TyVar, ...] = ()
    type_param_names: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()


@dataclass
class InterfaceInfo:
    name: str
    methods: dict[str, FnTy] = field(default_factory=dict)
    method_tokens: dict[str, Token] = field(default_factory=dict)
    defaults: dict[str, bool] = field(default_factory=dict)
    declared: bool = False


@dataclass
class EnumVariantInfo:
    name: str
    payload: tuple[Ty, ...]
    token: Token | None = None


@dataclass
class EnumInfo:
    name: str
    type_params: tuple[TyVar, ...] = ()
    type_param_names: tuple[str, ...] = ()
    variants: dict[str, EnumVariantInfo] = field(default_factory=dict)


RefinementKey = tuple[int, str, tuple[tuple[str, object], ...]]
"""Chave de refinamento: nome da raiz + caminho (campo ou índice literal)."""


@dataclass(frozen=True)
class FunctionSignature:
    type_params: tuple[TyVar, ...]
    type_param_names: tuple[str, ...]
    fn: FnTy


@dataclass(frozen=True)
class GenericFnInstance:
    """Uma chamada genérica já inferida: nome e argumentos de tipo concretos."""

    name: str
    type_args: tuple[Ty, ...]


class Checker(ExprVisitor[Ty], StmtVisitor[None]):
    def __init__(
        self,
        reporter: ErrorReporter,
        *,
        captured_mutables: set[Token] | None = None,
        captured_globals: set[str] | None = None,
        source_index: SourceIndex | None = None,
    ) -> None:
        self._reporter = reporter
        self._source_index = source_index
        self._scopes: list[dict[str, Ty]] = [{}]
        self._decl_tokens: list[dict[str, Token]] = [{}]
        self._captured_mutables: set[Token] = set(captured_mutables or ())
        self._captured_globals: set[str] = set(captured_globals or ())
        self._narrowings: dict[RefinementKey, Ty] = {}
        self._classes: dict[str, ClassInfo] = {}
        self._enums: dict[str, EnumInfo] = {}
        self._interfaces: dict[str, InterfaceInfo] = {}
        self._current_class: ClassInfo | None = None
        self._current_interface: InterfaceInfo | None = None
        self._current_return: Ty | None = None
        self._in_initializer = False
        self._signatures: dict[Function, FunctionSignature] = {}
        self._predeclared_by_name: dict[str, FunctionSignature] = {}
        self._type_param_scopes: list[dict[str, TyVar]] = []
        self._next_type_var_id = 0
        self._generic_context: list[tuple[str, tuple[TyVar, ...]]] = []
        self._alias_targets: dict[str, Ty] = {}
        self._alias_tokens: dict[str, Token] = {}
        self._alias_resolved: dict[str, Ty] = {}
        self._alias_resolving: set[str] = set()
        self._native_modules: dict[str, dict[str, Ty]] = {}
        self._except_depth = 0
        # Tipos inferidos por nó, consumidos pelo backend (ADR-0031, decisão 7).
        # `types` é o tipo de fluxo (com narrowing); `storage_types` é o tipo de
        # representação (declarado, sem narrowing) — ADR-0045.
        self.types: dict[Expr, Ty] = {}
        self.storage_types: dict[Expr, Ty] = {}
        self.generic_fn_instances: dict[Call, GenericFnInstance] = {}
        self.generic_classes: set[ClassTy] = set()
        self.generic_class_sites: dict[Call, ClassTy] = {}
        self._function_depth = 0
        self._return_collector: list[Ty] | None = None
        self._define_builtins()

    def _contains_type_var(self, ty: Ty) -> bool:
        if isinstance(ty, TyVar):
            return True
        if isinstance(ty, ClassTy):
            return any(self._contains_type_var(arg) for arg in ty.args)
        if isinstance(ty, FnTy):
            return any(
                self._contains_type_var(param) for param in ty.params
            ) or self._contains_type_var(ty.ret)
        return False

    def concrete_class_types(self) -> set[ClassTy]:
        """Todas as instanciações de classe concretas vistas pelo checker."""
        result = {ty for ty in self.generic_classes if not self._contains_type_var(ty)}
        for ty in self.storage_types.values():
            if isinstance(ty, ClassTy) and ty.args and not self._contains_type_var(ty):
                result.add(ty)
        return result

    def check(self, statements: list[Stmt]) -> None:
        self._predeclare_classes(statements)
        self._predeclare_interfaces(statements)
        self._predeclare_enums(statements)
        self._predeclare_aliases(statements)
        self._predeclare_functions(statements)
        for statement in statements:
            self._check_stmt(statement)

        self._check_overrides()

    # --- infraestrutura ---

    def _define_builtins(self) -> None:
        self._scopes[0]["chars"] = NativeFnTy("chars")
        self._scopes[0]["len"] = NativeFnTy("len")
        self._scopes[0]["print"] = NativeFnTy("print")
        self._scopes[0]["range"] = FnTy((INT, INT, INT), RANGE, 3)
        self._scopes[0]["repr"] = NativeFnTy("repr")
        self._scopes[0]["str"] = NativeFnTy("str")
        result_t = self._fresh_type_var("T")
        result_e = self._fresh_type_var("E")
        self._enums["Result"] = EnumInfo(
            "Result",
            (result_t, result_e),
            ("T", "E"),
            {
                "Ok": EnumVariantInfo("Ok", (result_t,)),
                "Err": EnumVariantInfo("Err", (result_e,)),
            },
        )
        self._scopes[0]["Result"] = EnumObjectTy("Result")

        message_token = Token(TokenType.IDENTIFIER, "message", None, 0)
        site_token = Token(TokenType.IDENTIFIER, "site", None, 0)
        self._classes["Exception"] = ClassInfo(
            "Exception",
            None,
            fields={
                "message": FieldBinding(STRING, False, message_token),
                "site": FieldBinding(STRING, False, site_token),
            },
            init=FnTy((STRING,), ClassTy("Exception"), 1),
        )
        self._classes["RuntimeError"] = ClassInfo(
            "RuntimeError",
            "Exception",
            init=FnTy((STRING,), ClassTy("RuntimeError"), 1),
        )
        self._scopes[0]["Exception"] = ClassObjectTy("Exception")
        self._scopes[0]["RuntimeError"] = ClassObjectTy("RuntimeError")

        self._enums["BytesError"] = EnumInfo(
            "BytesError",
            (),
            (),
            {
                "InvalidHex": EnumVariantInfo("InvalidHex", (STRING,)),
                "InvalidBase64": EnumVariantInfo("InvalidBase64", (STRING,)),
                "InvalidUtf8": EnumVariantInfo("InvalidUtf8", (STRING,)),
            },
        )
        self._scopes[0]["BytesError"] = EnumObjectTy("BytesError")

        self._native_modules = {
            "Bytes": dict(BYTES_STATICS),
            "Int": {
                "parse": FnTy((STRING,), union(INT, NIL), 1),
            },
            "Float": {
                "parse": FnTy((STRING,), union(FLOAT, NIL), 1),
            },
            "math": {
                "abs": NativeFnTy("math.abs"),
                "min": NativeFnTy("math.min"),
                "max": NativeFnTy("math.max"),
                "clamp": NativeFnTy("math.clamp"),
                "floor": FnTy((FLOAT,), INT, 1),
                "ceil": FnTy((FLOAT,), INT, 1),
                "round": FnTy((FLOAT,), INT, 1),
                "trunc": FnTy((FLOAT,), INT, 1),
                "sqrt": FnTy((FLOAT,), FLOAT, 1),
            },
        }
        for primitive in PRIMITIVES:
            signature = FnTy(
                primitive.params,
                primitive.result,
                len(primitive.params),
            )
            if "." in primitive.lox:
                module, member = primitive.lox.split(".", 1)
                self._native_modules.setdefault(module, {})[member] = signature
            else:
                self._scopes[0][primitive.lox] = signature
        for name in self._native_modules:
            self._scopes[0][name] = NativeModuleTy(name)

    def _function_value_type(self, name: str, signature: FunctionSignature) -> Ty:
        if signature.type_params:
            return GenericFnTy(name, signature.type_params, signature.fn)
        return signature.fn

    def _fresh_type_var(self, name: str, bounds: tuple[str, ...] = ()) -> TyVar:
        self._next_type_var_id += 1
        return TyVar(name, self._next_type_var_id, bounds)

    def _declare_type_params(
        self,
        tokens: list[Token],
        bounds: list[tuple[Token, ...]] | None = None,
    ) -> tuple[tuple[TyVar, ...], tuple[str, ...]]:
        names: list[str] = []
        variables: list[TyVar] = []
        for index, token in enumerate(tokens):
            if token.lexeme in RESERVED_TYPE_PARAM_NAMES:
                self._error(
                    token,
                    f"Type parameter can't be named '{token.lexeme}'.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
                continue
            if token.lexeme in names:
                self._error(
                    token,
                    f"Type parameter '{token.lexeme}' is already declared.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
                continue

            declared: list[str] = []
            if bounds is not None and index < len(bounds):
                for bound in bounds[index]:
                    name = bound.lexeme
                    if name in declared:
                        self._error(
                            bound,
                            f"Constraint '{name}' is already declared.",
                            code=Code.INVALID_CHECKER_DECLARATION,
                        )
                        continue
                    if name not in BUILTIN_CONSTRAINTS and name not in self._interfaces:
                        if name in self._alias_targets:
                            resolved_bound = self._resolve_alias(name, bound)
                            if isinstance(resolved_bound, InterfaceTy):
                                name = resolved_bound.name
                            else:
                                self._error(
                                    bound,
                                    f"Type alias '{name}' isn't an interface.",
                                    code=Code.INVALID_TYPE_ANNOTATION,
                                )
                                continue
                        else:
                            self._error(
                                bound,
                                f"Unknown constraint '{name}'.",
                                code=Code.UNKNOWN_TYPE,
                            )
                            continue
                    declared.append(name)

            names.append(token.lexeme)
            variables.append(self._fresh_type_var(token.lexeme, tuple(declared)))

        return tuple(variables), tuple(names)

    def _push_type_params(self, names: tuple[str, ...], variables: tuple[TyVar, ...]) -> None:
        self._type_param_scopes.append(dict(zip(names, variables, strict=True)))

    def _pop_type_params(self) -> None:
        self._type_param_scopes.pop()

    def _lookup_type_param(self, name: str) -> TyVar | None:
        for scope in reversed(self._type_param_scopes):
            found = scope.get(name)
            if found is not None:
                return found

        return None

    def _predeclare_classes(self, statements: list[Stmt]) -> None:
        for statement in statements:
            if not isinstance(statement, Class):
                continue

            superclass = (
                statement.superclass.name.lexeme if statement.superclass is not None else None
            )
            params, names = self._declare_type_params(statement.type_params)
            self._classes.setdefault(
                statement.name.lexeme,
                ClassInfo(
                    statement.name.lexeme,
                    superclass,
                    type_params=params,
                    type_param_names=names,
                ),
            )
            self._scopes[0].setdefault(statement.name.lexeme, ClassObjectTy(statement.name.lexeme))

    def _predeclare_interfaces(self, statements: list[Stmt]) -> None:
        for statement in statements:
            if not isinstance(statement, Interface):
                continue
            self._interfaces.setdefault(statement.name.lexeme, InterfaceInfo(statement.name.lexeme))

    def _predeclare_enums(self, statements: list[Stmt]) -> None:
        for statement in statements:
            if not isinstance(statement, EnumDecl):
                continue
            if statement.name.lexeme in BUILTIN_NAMES:
                continue

            params, names = self._declare_type_params(statement.type_params)
            self._enums.setdefault(
                statement.name.lexeme,
                EnumInfo(statement.name.lexeme, params, names),
            )
            self._scopes[0].setdefault(statement.name.lexeme, EnumObjectTy(statement.name.lexeme))

    def _predeclare_aliases(self, statements: list[Stmt]) -> None:
        for statement in statements:
            if not isinstance(statement, TypeAlias):
                continue
            name = statement.name.lexeme
            if (
                name in self._classes
                or name in self._interfaces
                or name in self._enums
                or name in BUILTIN_NAMES
                or name in RESERVED_TYPE_PARAM_NAMES
            ):
                self._error(
                    statement.name,
                    f"Name '{name}' is already declared.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
                continue
            if name in self._alias_targets:
                self._error(
                    statement.name,
                    f"Type alias '{name}' is already declared.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
                continue
            self._alias_targets[name] = statement.target
            self._alias_tokens[name] = statement.name

        for name, token in self._alias_tokens.items():
            self._resolve_alias(name, token)

    def _resolve_alias(self, name: str, token: Token) -> Ty:
        cached = self._alias_resolved.get(name)
        if cached is not None:
            return cached
        target = self._alias_targets.get(name)
        if target is None:
            return ERROR
        if name in self._alias_resolving:
            self._error(
                token,
                f"Type alias '{name}' is recursive.",
                code=Code.INVALID_TYPE_ANNOTATION,
            )
            return ERROR
        self._alias_resolving.add(name)
        try:
            resolved = self._resolve_type(target, token)
        finally:
            self._alias_resolving.discard(name)
        self._alias_resolved[name] = resolved
        return resolved

    def type_aliases(self) -> dict[str, Ty]:
        return dict(self._alias_resolved)

    def visit_type_alias_stmt(self, stmt: TypeAlias) -> None:
        if self._function_depth > 0 or len(self._scopes) > 1:
            self._error(
                stmt.keyword,
                "Type aliases must be declared at the top level.",
                code=Code.INVALID_CHECKER_DECLARATION,
            )

    def _predeclare_functions(self, statements: list[Stmt]) -> None:
        """Calcula assinaturas de topo antes dos corpos.

        A assinatura é o contrato: um corpo de função pode chamar outra função mesmo que
        ela apareça depois. A ordem das declarações continua valendo para o código de topo
        (o runtime executa os statements na ordem em que estão escritos).
        """
        for statement in statements:
            if not isinstance(statement, Function):
                continue

            signature = self._signature(statement, is_init=False)
            self._signatures[statement] = signature
            self._predeclared_by_name[statement.name.lexeme] = signature

    def _begin_scope(self) -> None:
        self._scopes.append({})
        self._decl_tokens.append({})

    def _end_scope(self) -> None:
        index = len(self._scopes) - 1
        for key in [key for key in self._narrowings if key[0] == index]:
            del self._narrowings[key]
        self._scopes.pop()
        self._decl_tokens.pop()

    def _define(self, name: Token, ty: Ty) -> None:
        if len(self._scopes) == 1 and name.lexeme in BUILTIN_NAMES:
            self._error(
                name,
                f"Can't redefine builtin '{name.lexeme}'.",
                code=Code.RESERVED_NAME,
            )

        self._scopes[-1][name.lexeme] = ty
        self._decl_tokens[-1][name.lexeme] = name
        index = len(self._scopes) - 1
        for key in [key for key in self._narrowings if key[0] == index and key[1] == name.lexeme]:
            del self._narrowings[key]

    def _find_decl(self, name: str) -> tuple[int, Ty] | None:
        for index in range(len(self._scopes) - 1, -1, -1):
            ty = self._scopes[index].get(name)
            if ty is not None:
                return index, ty

        return None

    def _suggest(self, name: str) -> str | None:
        """Nome visível mais próximo, determinístico (candidatos ordenados).

        Nomes mangled de módulo (`std$strings$trim`) ficam de fora: sugerir o símbolo
        interno seria pior do que não sugerir.
        """
        candidates: set[str] = set()
        for scope in self._scopes:
            candidates.update(key for key in scope if "$" not in key)
        candidates.update(key for key in self._predeclared_by_name if "$" not in key)
        matches = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=0.7)
        return matches[0] if matches else None

    def _undefined_help(self, name: str) -> str | None:
        suggestion = self._suggest(name)
        return f"did you mean '{suggestion}'?" if suggestion else None

    def _undefined_fixes(self, token: Token) -> tuple[Fix, ...]:
        suggestion = self._suggest(token.lexeme)
        if suggestion is None:
            return ()
        return (
            Fix(
                Applicability.UNSAFE,
                f"Replace with '{suggestion}'.",
                (
                    Edit(
                        span_of_token(token, self._reporter.file),
                        suggestion,
                    ),
                ),
            ),
        )

    def _lookup(self, name: Token) -> Ty:
        found = self._find_decl(name.lexeme)
        if found is None:
            predeclared = self._predeclared_by_name.get(name.lexeme)
            if predeclared is not None and self._function_depth > 0:
                return self._function_value_type(name.lexeme, predeclared)

            self._error(
                name,
                f"Undefined variable '{name.lexeme}'.",
                code=Code.UNDEFINED_NAME,
                lowerable=True,
                help=self._undefined_help(name.lexeme),
                fixes=self._undefined_fixes(name),
            )
            return ERROR

        index, declared = found
        narrowed = self._narrowings.get((index, name.lexeme, ()))
        return narrowed if narrowed is not None else declared

    def _lookup_declared(self, name: Token) -> Ty:
        found = self._find_decl(name.lexeme)
        if found is None:
            self._error(
                name,
                f"Undefined variable '{name.lexeme}'.",
                code=Code.UNDEFINED_NAME,
                lowerable=True,
                help=self._undefined_help(name.lexeme),
                fixes=self._undefined_fixes(name),
            )
            return ERROR

        return found[1]

    def _invalidate(self, name: str, index: int) -> None:
        """Atribuir à raiz invalida o caminho inteiro (`p`, `p.nome`, `p[0]`)."""
        for key in list(self._narrowings):
            if key[0] == index and key[1] == name:
                del self._narrowings[key]

    def _call_may_run_user_code(self, expr: Call) -> bool:
        """Chamadas nativas puras não executam closures do usuário.

        `print`, `len`, `str`, `repr`, `chars`, `range` e métodos de `List`/`Map` são
        nativos; o resto (função, método de classe, construtor, valor de função) pode
        executar código do usuário e invalidar `var` capturado.
        """
        callee = self.types.get(expr.callee)
        if isinstance(callee, NativeFnTy):
            return False
        if isinstance(expr.callee, Get):
            receiver = self.types.get(expr.callee.object)
            if isinstance(receiver, (ListTy, MapTy)):
                return False
        return True

    def _invalidate_captured(self) -> None:
        """Chamadas podem executar closures que mutam `var` capturado (P2).

        Refinos de campo/índice já caem em `_invalidate_members`; aqui só os de
        variável. Globo é identificado pelo nome (o resolver não resolve globais).
        """
        if not self._captured_mutables and not self._captured_globals:
            return
        for key in list(self._narrowings):
            if key[2]:
                continue
            index = key[0]
            if index == 0 and key[1] in self._captured_globals:
                del self._narrowings[key]
                continue
            token = self._decl_tokens[index].get(key[1])
            if token in self._captured_mutables:
                del self._narrowings[key]

    def _invalidate_path(self, key: RefinementKey) -> None:
        """Mutar um caminho invalida ele e os caminhos mais fundos com o mesmo prefixo."""
        size = len(key[2])
        for candidate in list(self._narrowings):
            if candidate[0] == key[0] and candidate[1] == key[1] and candidate[2][:size] == key[2]:
                del self._narrowings[candidate]

    def _invalidate_members(self) -> None:
        """Chamada/atribuição de campo/índice derruba todo refino de campo/índice.

        Sem aliasing não dá para saber o que a chamada mutou; refinos de variáveis
        continuam (ADR-0045)."""
        for key in [key for key in self._narrowings if key[2]]:
            del self._narrowings[key]

    def _apply_refinements(self, refinements: dict[RefinementKey, Ty]) -> None:
        self._narrowings.update(refinements)

    def _error(
        self,
        token: Token,
        message: str,
        *,
        code: Code,
        lowerable: bool = False,
        notes: tuple[str, ...] = (),
        help: str | None = None,
        label_tokens: tuple[tuple[Token, str], ...] = (),
        fixes: tuple[Fix, ...] = (),
    ) -> None:
        """Reporta erro de tipo.

        `lowerable=True` para os erros que o interpretador também levantaria em runtime
        (operandos de tipo errado): o backend os rebaixa a panic site (ADR-0031).
        """
        self._reporter.error(
            token,
            message,
            code=code,
            lowerable=lowerable,
            notes=notes,
            help=help,
            label_tokens=label_tokens,
            fixes=fixes,
        )

    def _mismatch_message(self, expected: Ty, actual: Ty) -> str:
        if (
            isinstance(expected, ClassTy)
            and isinstance(actual, ClassObjectTy)
            and expected.name == actual.name
        ):
            return f"Expected an instance of {expected.name}, found the class {actual.name}."
        if isinstance(expected, FnTy) and isinstance(actual, ClassObjectTy):
            return f"Expected a function {display(expected)}, found the class {actual.name}."
        if expected is FLOAT and actual is INT:
            return "Expected Float, found Int. Write `2.0` or use `2 as Float`."

        return f"Expected {display(expected)}, found {display(actual)}."

    def _provenance_notes(self, expression: Expr, token: Token) -> tuple[str, ...]:
        """Nota de proveniência do valor, se a expressão tem nome/caminho.

        O diagnóstico costuma apontar o *destino* (nome da variável, parêntese da
        chamada); a nota aponta de onde o valor veio (ADR-0099). Literais e
        expressões compostas ficam de fora: para eles a nota só repetiria o caret.
        """
        if self._source_index is None:
            return ()
        if not self._is_named_value(expression):
            return ()
        span = self._source_index.span_of(expression)
        if span is None:
            return ()
        if (token.offset or 0) == span.start:
            return ()
        text = self._source_index.text_of(span)
        line = self._source_index.line_of(span)
        if text is None or line is None:
            return ()
        snippet = " ".join(text.split())
        if not snippet:
            return ()
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        return (f"the value comes from `{snippet}` (line {line})",)

    def _is_named_value(self, expression: Expr) -> bool:
        if isinstance(expression, Grouping):
            return self._is_named_value(expression.expression)
        return isinstance(expression, (Variable, Get, Index, Call))

    def _argument_notes(self, call: Call | None, index: int, token: Token) -> tuple[str, ...]:
        if call is None or not 1 <= index <= len(call.arguments):
            return ()
        return self._provenance_notes(call.arguments[index - 1], token)

    def _argument_error(
        self,
        token: Token,
        index: int,
        expected: Ty,
        actual: Ty,
        *,
        call: Call | None = None,
    ) -> None:
        """Um único ponto para argumento de tipo errado (código e proveniência)."""
        self._error(
            token,
            f"Argument {index}: {self._mismatch_message(expected, actual)}",
            code=Code.TYPE_MISMATCH,
            notes=self._argument_notes(call, index, token),
        )

    def _check_stmt(self, stmt: Stmt) -> None:
        stmt.accept(self)

    def _infer(self, expr: Expr) -> Ty:
        ty = expr.accept(self)
        self.types[expr] = ty
        self.storage_types[expr] = self._storage_type(expr, ty)
        return ty

    def _storage_type(self, expr: Expr, flow: Ty) -> Ty:
        """Tipo declarado/representação, sem narrowing (ADR-0045)."""
        if isinstance(expr, Variable):
            found = self._find_decl(expr.name.lexeme)
            return found[1] if found is not None else flow
        if isinstance(expr, Get) and not expr.optional:
            obj = self._storage_object_type(expr.object)
            if isinstance(obj, ClassTy):
                field = self._find_field(obj.name, expr.name.lexeme)
                if field is not None:
                    return self._substitute(field.ty, self._class_bindings(obj))
        if isinstance(expr, Index):
            obj = self._storage_object_type(expr.object)
            if isinstance(obj, ListTy):
                return obj.element
            if isinstance(obj, MapTy):
                return obj.value
        return flow

    def _storage_object_type(self, expr: Expr) -> Ty | None:
        """Tipo declarado da expressão-base, mesmo quando o nó foi estreitado.

        `visit_get_expr`/`visit_index_expr` no caminho estreitado não inferem o
        objeto; para a representação usamos a declaração da raiz."""
        known = self.types.get(expr) or self.storage_types.get(expr)
        if known is not None:
            return non_nil(known)
        if isinstance(expr, Variable):
            found = self._find_decl(expr.name.lexeme)
            if found is not None:
                return non_nil(found[1])
        if isinstance(expr, This) and self._current_class is not None:
            return ClassTy(self._current_class.name, self._current_class.type_params)
        return None

    def _check(self, expr: Expr, expected: Ty, token: Token) -> Ty:
        if isinstance(expr, Call):
            actual = self._infer_call(expr, expected, token)
            self._invalidate_members()
            if self._call_may_run_user_code(expr):
                self._invalidate_captured()
            if actual is ERROR:
                return ERROR
            # `_check` não passa por `_infer`; o lowering lê o tipo de chamadas
            # esperadas (ex.: `return math.sqrt(x)`) daqui.
            self.types[expr] = actual
            self.storage_types[expr] = self._storage_type(expr, actual)
            if not self._assignable(expected, actual):
                self._error(
                    token,
                    self._mismatch_message(expected, actual),
                    code=Code.TYPE_MISMATCH,
                    notes=self._provenance_notes(expr, token),
                )
            return actual

        if isinstance(expr, ListLiteral):
            element = self._expected_element(expected)
            if element is not None:
                for item in expr.elements:
                    self._check(item, element, expr.bracket)

                return ListTy(element)

        if isinstance(expr, MapLiteral):
            entry_types = self._expected_map(expected)
            if entry_types is not None:
                key_ty, value_ty = entry_types
                for key, value in expr.entries:
                    self._check(key, key_ty, expr.brace)
                    self._check(value, value_ty, expr.brace)

                return MapTy(key_ty, value_ty)

        if isinstance(expr, TupleLiteral):
            items = self._expected_tuple(expected)
            if items is not None:
                if len(items) != len(expr.elements):
                    self._error(
                        token,
                        f"Expected a tuple of {len(items)} elements, found {len(expr.elements)}.",
                        code=Code.TYPE_MISMATCH,
                    )
                    return ERROR

                for tuple_element, item_ty in zip(expr.elements, items, strict=True):
                    self._check(tuple_element, item_ty, expr.paren)

                # O lowering lê o tipo concreto da tupla (e do aninhamento) para
                # desestruturar; `_check` não passa por `_infer`, então publica aqui.
                result = TupleTy(items)
                self.types[expr] = result
                self.storage_types[expr] = self._storage_type(expr, result)
                return result

        if isinstance(expr, Lambda):
            actual = self._lambda_type(expr, self._expected_fn(expected))
            # O lowering precisa do tipo concreto da lambda contextual (ADR-0046);
            # `_check` não passa por `_infer`, então publica aqui.
            self.types[expr] = actual
            self.storage_types[expr] = actual
            if not self._assignable(expected, actual):
                self._error(
                    token,
                    self._mismatch_message(expected, actual),
                    code=Code.TYPE_MISMATCH,
                    notes=self._provenance_notes(expr, token),
                )
                return ERROR

            return actual

        actual = self._infer(expr)
        if isinstance(actual, GenericFnTy):
            self._error(
                token,
                f"Generic function '{actual.name}' can't be used as a value yet; "
                "call it so its type arguments can be inferred.",
                code=Code.GENERIC_INFERENCE,
            )
            return ERROR
        if not self._assignable(expected, actual):
            self._error(
                token,
                self._mismatch_message(expected, actual),
                code=Code.TYPE_MISMATCH,
                notes=self._provenance_notes(expr, token),
            )

        return actual

    def _expected_element(self, expected: Ty) -> Ty | None:
        if expected is ANY:
            return ANY
        if isinstance(expected, ListTy):
            return expected.element

        if isinstance(expected, UnionTy):
            lists = [member for member in expected.members if isinstance(member, ListTy)]
            if len(lists) == 1:
                return lists[0].element

        return None

    def _expected_tuple(self, expected: Ty) -> tuple[Ty, ...] | None:
        if isinstance(expected, TupleTy):
            return expected.items

        return None

    def _expected_map(self, expected: Ty) -> tuple[Ty, Ty] | None:
        if expected is ANY:
            return (ANY, ANY)
        if isinstance(expected, MapTy):
            return (expected.key, expected.value)

        if isinstance(expected, UnionTy):
            maps = [member for member in expected.members if isinstance(member, MapTy)]
            if len(maps) == 1:
                return (maps[0].key, maps[0].value)

        return None

    def _expected_fn(self, expected: Ty) -> FnTy | None:
        if isinstance(expected, FnTy):
            return expected
        if isinstance(expected, UnionTy):
            functions = [member for member in expected.members if isinstance(member, FnTy)]
            if len(functions) == 1:
                return functions[0]

        return None

    def _assignable(self, expected: Ty, actual: Ty) -> bool:
        # `Any` é top type: qualquer `T` é atribuível a `Any`. O contrário exige
        # conversão explícita (`as`), porque os tipos são apagados no runtime —
        # deixar `Any -> T` passar aqui fazia o backend reinterpretar o payload
        # (ponteiro vazado/segfault) e quebrava I1/I2/I3.
        if expected is ANY or expected is ERROR or actual is ERROR:
            return True
        if actual is NEVER:
            return True
        if expected == actual:
            return True
        # Rebinding de classe é dinâmico por ADR-0044: `Base = OtherBase as Any`
        # continua válido; o backend representa classe como ponteiro.
        if isinstance(expected, ClassObjectTy) and actual is ANY:
            return True
        # Destructuring com anotação de tupla é o formulário explícito previsto
        # em ADR-0069 para um valor vindo de `Any`; o backend desemboxa a tupla.
        if isinstance(expected, TupleTy) and actual is ANY:
            return True
        if isinstance(actual, UnionTy):
            return all(self._assignable(expected, member) for member in actual.members)
        if isinstance(expected, UnionTy):
            return any(self._assignable(member, actual) for member in expected.members)
        if isinstance(expected, InterfaceTy) and isinstance(actual, TyVar):
            return expected.name in actual.bounds
        if isinstance(expected, TyVar) or isinstance(actual, TyVar):
            return False
        # Sem promoção `Int -> Float` em contexto de armazenamento (ADR-0058):
        # `val x: Float = 2`, `x = 2`, `f(2)` e `return 2` exigem `2.0`/`as Float`.
        # A promoção continua valendo só como regra de aritmética (ADR-0006).
        if isinstance(expected, ListTy) and isinstance(actual, ListTy):
            if expected.element is ERROR or actual.element is ERROR:
                return True
            return expected.element == actual.element
        if isinstance(expected, MapTy) and isinstance(actual, MapTy):
            if expected.key is ERROR or actual.key is ERROR:
                return True
            if expected.value is ERROR or actual.value is ERROR:
                return True
            return expected.key == actual.key and expected.value == actual.value
        if isinstance(expected, TupleTy) and isinstance(actual, TupleTy):
            return len(expected.items) == len(actual.items) and all(
                self._assignable(expected_item, actual_item)
                for expected_item, actual_item in zip(expected.items, actual.items, strict=True)
            )
        if isinstance(expected, FnTy):
            if isinstance(actual, FnTy):
                return self._assignable_fn(expected, actual)
            if isinstance(actual, ClassObjectTy):
                info = self._classes.get(actual.name)
                if info is None:
                    return False
                signature = self._initializer(info) or FnTy((), ClassTy(actual.name), 0)
                return self._assignable_fn(expected, signature)
            if isinstance(actual, NativeFnTy):
                native_signature = self._native_signature(actual.name)
                return native_signature is not None and self._assignable_fn(
                    expected, native_signature
                )
        if isinstance(expected, ClassTy) and isinstance(actual, ClassTy):
            if expected.args or actual.args:
                return expected.name == actual.name and expected.args == actual.args
            return self._is_subclass(actual.name, expected.name)
        if isinstance(expected, InterfaceTy):
            if isinstance(actual, InterfaceTy):
                return expected.name == actual.name
            if isinstance(actual, ClassTy):
                return self._implements_interface(actual.name, expected.name)
            return False
        if isinstance(expected, EnumTy) and isinstance(actual, EnumTy):
            return expected.name == actual.name and expected.args == actual.args

        return False

    def _assignable_fn(self, expected: FnTy, actual: FnTy) -> bool:
        """Função é contravariante nos parâmetros e covariante no retorno."""
        if expected.variadic != actual.variadic:
            return False
        count = len(expected.params)
        if actual.variadic:
            if len(actual.params) != len(expected.params):
                return False
        elif not actual.min_params <= count <= len(actual.params):
            return False

        for expected_param, actual_param in zip(expected.params, actual.params, strict=False):
            if not self._assignable(actual_param, expected_param):
                return False

        return self._assignable(expected.ret, actual.ret)

    def _is_subclass(self, actual: str, expected: str) -> bool:
        name: str | None = actual
        while name is not None:
            if name == expected:
                return True
            info = self._classes.get(name)
            name = info.superclass if info is not None else None

        return False

    def _implements_interface(self, class_name: str, interface: str) -> bool:
        """Nominal e transitivo pela superclasse (ADR-0080)."""
        name: str | None = class_name
        while name is not None:
            info = self._classes.get(name)
            if info is None:
                return False
            if interface in info.interfaces:
                return True
            name = info.superclass

        return False

    def _resolve_type(self, ty: Ty, token: Token) -> Ty:
        if isinstance(ty, ClassTy):
            parameter = self._lookup_type_param(ty.name)
            if parameter is not None:
                if ty.args:
                    self._error(
                        token,
                        f"Type parameter '{ty.name}' can't take type arguments.",
                        code=Code.TYPE_ARGUMENTS,
                    )
                    return ERROR
                return parameter

            if ty.name in self._alias_targets:
                if ty.args:
                    self._error(
                        token,
                        f"Type alias '{ty.name}' isn't generic.",
                        code=Code.TYPE_ARGUMENTS,
                    )
                    return ERROR
                return self._resolve_alias(ty.name, token)

            enum_info = self._enums.get(ty.name)
            if enum_info is not None:
                if enum_info.type_params:
                    if not ty.args:
                        self._error(
                            token,
                            f"Enum '{ty.name}' needs "
                            f"{len(enum_info.type_params)} type argument(s).",
                            code=Code.TYPE_ARGUMENTS,
                        )
                        return ERROR
                    if len(ty.args) != len(enum_info.type_params):
                        self._error(
                            token,
                            f"{ty.name} expects "
                            f"{len(enum_info.type_params)} type argument(s), "
                            f"got {len(ty.args)}.",
                            code=Code.TYPE_ARGUMENTS,
                        )
                        return ERROR
                    args = tuple(self._resolve_type(arg, token) for arg in ty.args)
                    if any(arg is ERROR for arg in args):
                        return ERROR
                    return EnumTy(ty.name, args)
                if ty.args:
                    self._error(
                        token,
                        f"Enum '{ty.name}' isn't generic.",
                        code=Code.TYPE_ARGUMENTS,
                    )
                    return ERROR
                return EnumTy(ty.name)

            interface_info = self._interfaces.get(ty.name)
            if interface_info is not None:
                if ty.args:
                    self._error(
                        token,
                        f"Interface '{ty.name}' isn't generic.",
                        code=Code.TYPE_ARGUMENTS,
                    )
                    return ERROR
                return InterfaceTy(ty.name)

            info = self._classes.get(ty.name)
            if info is None:
                self._error(token, f"Unknown type '{ty.name}'.", code=Code.UNKNOWN_TYPE)
                return ERROR

            if info.type_params:
                if not ty.args:
                    self._error(
                        token,
                        f"Class '{ty.name}' needs {len(info.type_params)} type "
                        "argument(s); annotate it as "
                        f"{ty.name}[...].",
                        code=Code.TYPE_ARGUMENTS,
                    )
                    return ERROR
                if len(ty.args) != len(info.type_params):
                    self._error(
                        token,
                        f"{ty.name} expects {len(info.type_params)} type "
                        f"argument(s), got {len(ty.args)}.",
                        code=Code.TYPE_ARGUMENTS,
                    )
                    return ERROR

                args = tuple(self._resolve_type(arg, token) for arg in ty.args)
                if any(arg is ERROR for arg in args):
                    return ERROR
                return ClassTy(ty.name, args)

            if ty.args:
                self._error(
                    token,
                    f"Class '{ty.name}' isn't generic.",
                    code=Code.TYPE_ARGUMENTS,
                )
                return ERROR

            return ty
        if isinstance(ty, ListTy):
            return ListTy(self._resolve_type(ty.element, token))
        if isinstance(ty, MapTy):
            key = self._resolve_type(ty.key, token)
            value = self._resolve_type(ty.value, token)
            if not self._valid_map_key(key):
                self._error(
                    token,
                    "Map keys must be String, Int or Bool.",
                    code=Code.INVALID_MAP,
                )
                key = ERROR
            return MapTy(key, value)
        if isinstance(ty, TupleTy):
            return TupleTy(tuple(self._resolve_type(item, token) for item in ty.items))
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self._resolve_type(param, token) for param in ty.params),
                self._resolve_type(ty.ret, token),
                ty.min_params,
                ty.variadic,
            )
        if isinstance(ty, UnionTy):
            return union(*(self._resolve_type(member, token) for member in ty.members))

        return ty

    def _valid_map_key(self, ty: Ty) -> bool:
        if ty is ANY or ty is ERROR or ty is STRING or ty is INT or ty is BOOL:
            return True
        if isinstance(ty, UnionTy):
            return all(self._valid_map_key(member) for member in ty.members)

        return False

    def _find_field(self, class_name: str, field_name: str) -> FieldBinding | None:
        name: str | None = class_name
        while name is not None:
            info = self._classes.get(name)
            if info is None:
                return None
            if field_name in info.fields:
                return info.fields[field_name]
            name = info.superclass

        return None

    def _find_method(self, class_name: str, method_name: str) -> FnTy | None:
        name: str | None = class_name
        while name is not None:
            info = self._classes.get(name)
            if info is None:
                return None
            if method_name in info.methods:
                return info.methods[method_name]
            if method_name == "init" and info.init is not None:
                return info.init
            name = info.superclass

        # Defaults das interfaces: derivada → base, na ordem de `implements`.
        name = class_name
        while name is not None:
            info = self._classes.get(name)
            if info is None:
                return None
            for interface in info.interfaces:
                interface_info = self._interfaces.get(interface)
                if interface_info is not None:
                    method = interface_info.methods.get(method_name)
                    if method is not None:
                        return method
            name = info.superclass

        return None

    def _initializer(self, info: ClassInfo) -> FnTy | None:
        """`init` da classe ou o primeiro `init` herdado (o runtime herda)."""
        if info.init is not None:
            return info.init
        if info.superclass is None:
            return None
        return self._find_method(info.superclass, "init")

    def _numeric(self, ty: Ty, token: Token) -> Ty:
        if ty is ANY:
            return ANY
        if ty is INT or ty is FLOAT:
            return ty
        if isinstance(ty, TyVar):
            if "Num" in ty.bounds:
                return ty
            if ty.bounds:
                self._error(
                    token,
                    f"Type parameter '{ty.name}' needs a 'Num' constraint.",
                    code=Code.INVALID_OPERANDS,
                )
                return ERROR
            self._error(
                token,
                "Operands must be numbers.",
                code=Code.INVALID_OPERANDS,
                lowerable=True,
            )
            return ERROR

        self._error(
            token,
            "Operands must be numbers.",
            code=Code.INVALID_OPERANDS,
            lowerable=True,
        )
        return ERROR

    def _promote(self, left: Ty, right: Ty, token: Token) -> Ty:
        if left is ANY or right is ANY:
            return ANY
        if left is ERROR or right is ERROR:
            return ERROR
        if isinstance(left, TyVar) or isinstance(right, TyVar):
            if (
                isinstance(left, TyVar)
                and isinstance(right, TyVar)
                and left == right
                and "Num" in left.bounds
            ):
                return left
            self._error(
                token,
                "Operands must be the same type parameter constrained by 'Num'.",
                code=Code.INVALID_OPERANDS,
            )
            return ERROR
        if left is FLOAT or right is FLOAT:
            return FLOAT

        return INT

    # --- statements ---

    def visit_block_stmt(self, stmt: Block) -> None:
        self._begin_scope()
        for statement in stmt.statements:
            self._check_stmt(statement)
        self._end_scope()

    def visit_import_stmt(self, stmt: Import) -> None:
        return

    def visit_enum_stmt(self, stmt: EnumDecl) -> None:
        name = stmt.name.lexeme
        if name in BUILTIN_NAMES:
            self._error(
                stmt.name,
                f"Can't redefine builtin '{name}'.",
                code=Code.RESERVED_NAME,
            )
        if name in BUILTIN_CONSTRAINTS:
            self._error(
                stmt.name,
                f"Can't redefine builtin constraint '{name}'.",
                code=Code.RESERVED_NAME,
            )

        info = self._enums.get(name)
        if info is None:
            params, param_names = self._declare_type_params(stmt.type_params)
            info = EnumInfo(name, params, param_names)
            self._enums[name] = info

        if len(self._scopes) > 1 or self._function_depth > 0:
            self._error(
                stmt.name,
                "Enums must be declared at top level.",
                code=Code.INVALID_CHECKER_DECLARATION,
            )

        info.variants.clear()
        self._define(stmt.name, EnumObjectTy(name))
        self._push_type_params(info.type_param_names, info.type_params)
        try:
            seen: set[str] = set()
            for variant in stmt.variants:
                variant_name = variant.name.lexeme
                if variant_name in seen:
                    self._error(
                        variant.name,
                        f"Variant '{variant_name}' is already declared.",
                        code=Code.INVALID_CHECKER_DECLARATION,
                    )
                    continue
                seen.add(variant_name)

                payload = tuple(self._resolve_type(item, variant.name) for item in variant.payload)
                info.variants[variant_name] = EnumVariantInfo(variant_name, payload, variant.name)
        finally:
            self._pop_type_params()

    def visit_interface_stmt(self, stmt: Interface) -> None:
        name = stmt.name.lexeme
        if name in BUILTIN_NAMES:
            self._error(
                stmt.name,
                f"Can't redefine builtin '{name}'.",
                code=Code.RESERVED_NAME,
            )
        if name in BUILTIN_CONSTRAINTS:
            self._error(
                stmt.name,
                f"Can't redefine builtin constraint '{name}'.",
                code=Code.RESERVED_NAME,
            )

        if name in self._classes or name in self._enums:
            self._error(
                stmt.name,
                f"Name '{name}' is already declared as a class or enum.",
                code=Code.INVALID_CHECKER_DECLARATION,
            )

        if len(self._scopes) > 1 or self._function_depth > 0:
            self._error(
                stmt.name,
                "Interfaces must be declared at top level.",
                code=Code.INVALID_CHECKER_DECLARATION,
            )

        info = self._interfaces.get(name)
        if info is None:
            info = InterfaceInfo(name)
            self._interfaces[name] = info

        info.declared = True
        info.methods.clear()
        info.method_tokens.clear()
        info.defaults.clear()

        for method in stmt.methods:
            method_name = method.name.lexeme
            if method_name == "init":
                self._error(
                    method.name,
                    "Interfaces can't declare 'init'.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
                continue
            if method_name in info.methods:
                self._error(
                    method.name,
                    f"Method '{method_name}' is already declared in interface '{name}'.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
                continue

            signature = self._signature(method, is_init=False, allow_type_params=False).fn
            info.methods[method_name] = signature
            info.method_tokens[method_name] = method.name
            info.defaults[method_name] = not method.abstract

        enclosing = self._current_interface
        self._current_interface = info
        try:
            for method in stmt.methods:
                if method.abstract:
                    continue
                body_signature: FnTy | None = info.methods.get(method.name.lexeme)
                if body_signature is None:
                    continue
                self._check_function_body(
                    method,
                    body_signature,
                    None,
                    is_init=False,
                    interface_info=info,
                )
        finally:
            self._current_interface = enclosing

    def visit_class_stmt(self, stmt: Class) -> None:
        name = stmt.name.lexeme
        if name in BUILTIN_NAMES:
            self._error(
                stmt.name,
                f"Can't redefine builtin '{name}'.",
                code=Code.RESERVED_NAME,
            )
        if name in BUILTIN_CONSTRAINTS:
            self._error(
                stmt.name,
                f"Can't redefine builtin constraint '{name}'.",
                code=Code.RESERVED_NAME,
            )

        superclass_token = stmt.superclass.name if stmt.superclass is not None else None
        superclass = superclass_token.lexeme if superclass_token is not None else None

        if superclass_token is not None and superclass not in self._classes:
            self._error(
                superclass_token,
                f"Unknown superclass '{superclass}'.",
                code=Code.UNKNOWN_TYPE,
            )

        info = self._classes.get(name)
        if info is None:
            params, param_names = self._declare_type_params(stmt.type_params)
            info = ClassInfo(
                name,
                superclass,
                type_params=params,
                type_param_names=param_names,
            )
            self._classes[name] = info
            self._define(stmt.name, ClassObjectTy(name))

        info.superclass = superclass
        if superclass is not None:
            super_info = self._classes.get(superclass)
            if super_info is not None and super_info.type_params:
                assert superclass_token is not None
                self._error(
                    superclass_token,
                    "Generic superclasses aren't supported yet; inherit from a non-generic class.",
                    code=Code.GENERIC_UNSUPPORTED,
                )

        interfaces: list[str] = []
        for token in stmt.implements:
            interface = self._interfaces.get(token.lexeme)
            if interface is None:
                self._error(
                    token,
                    f"Unknown interface '{token.lexeme}'.",
                    code=Code.UNKNOWN_TYPE,
                )
                continue
            if not interface.declared:
                self._error(
                    token,
                    f"Interface '{token.lexeme}' must be declared before class '{name}'.",
                    code=Code.UNKNOWN_TYPE,
                )
                continue
            if token.lexeme in interfaces:
                self._error(
                    token,
                    f"Interface '{token.lexeme}' is already implemented.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
                continue
            interfaces.append(token.lexeme)
        info.interfaces = tuple(interfaces)

        own_interface_methods: set[str] = set()
        for interface_name in interfaces:
            interface = self._interfaces.get(interface_name)
            if interface is not None:
                own_interface_methods.update(interface.methods)

        enclosing = self._current_class
        self._current_class = info
        self._push_type_params(info.type_param_names, info.type_params)
        try:
            for field_decl in stmt.fields:
                field_name = field_decl.name.lexeme
                # Duplicata (mesma classe/herdada) é reportada pelo resolver.
                if superclass is not None and self._find_method(superclass, field_name) is not None:
                    self._error(
                        field_decl.name,
                        f"Field '{field_name}' conflicts with a method.",
                        code=Code.INVALID_OVERRIDE,
                    )
                elif field_name in own_interface_methods:
                    self._error(
                        field_decl.name,
                        f"Field '{field_name}' conflicts with an interface method.",
                        code=Code.INVALID_OVERRIDE,
                    )

                if field_decl.type_annotation is not None:
                    field_ty = self._storage_annotation(
                        self._resolve_type(field_decl.type_annotation, field_decl.name),
                        field_decl.name,
                        "Fields",
                    )
                elif field_decl.initializer is not None:
                    field_ty = self._infer(field_decl.initializer)
                    if field_decl.mutable and field_ty is NIL:
                        self._error(
                            field_decl.name,
                            f"Field '{field_decl.name.lexeme}' initialized with nil "
                            "needs a type annotation.",
                            code=Code.MISSING_ANNOTATION,
                        )
                        field_ty = ANY
                else:
                    self._error(
                        field_decl.name,
                        f"Field '{field_decl.name.lexeme}' needs a type annotation.",
                        code=Code.MISSING_ANNOTATION,
                    )
                    field_ty = ANY

                if field_decl.initializer is not None:
                    self._check(field_decl.initializer, field_ty, field_decl.name)

                info.fields[field_decl.name.lexeme] = FieldBinding(
                    field_ty, field_decl.mutable, field_decl.name
                )

            for method in stmt.methods:
                is_init = method.name.lexeme == "init"
                if (
                    superclass is not None
                    and self._find_field(superclass, method.name.lexeme) is not None
                ):
                    self._error(
                        method.name,
                        f"Method '{method.name.lexeme}' conflicts with a field.",
                        code=Code.INVALID_OVERRIDE,
                    )
                signature = self._signature(method, is_init=is_init, allow_type_params=False).fn
                if is_init:
                    info.init = signature
                else:
                    info.methods[method.name.lexeme] = signature
                    info.method_tokens[method.name.lexeme] = method.name

            for method in stmt.methods:
                is_init = method.name.lexeme == "init"
                body_signature = info.init if is_init else info.methods.get(method.name.lexeme)
                assert body_signature is not None
                self._check_function_body(method, body_signature, info, is_init=is_init)

            self._check_field_initialization(stmt, info)
            self._check_interface_conformance(stmt, info)
        finally:
            self._pop_type_params()
            self._current_class = enclosing

    def _interface_names(self, info: ClassInfo) -> list[str]:
        names: list[str] = []
        current: ClassInfo | None = info
        while current is not None:
            for interface in current.interfaces:
                if interface not in names:
                    names.append(interface)
            current = (
                self._classes.get(current.superclass) if current.superclass is not None else None
            )

        return names

    def _find_class_method(self, class_name: str | None, method_name: str) -> FnTy | None:
        """Só métodos declarados por classes (não defaults de interface)."""
        name = class_name
        while name is not None:
            info = self._classes.get(name)
            if info is None:
                return None
            if method_name in info.methods:
                return info.methods[method_name]
            if method_name == "init" and info.init is not None:
                return info.init
            name = info.superclass

        return None

    def _check_interface_conformance(self, stmt: Class, info: ClassInfo) -> None:
        if not info.interfaces:
            return

        providers: dict[str, list[str]] = {}
        for interface_name in self._interface_names(info):
            interface = self._interfaces.get(interface_name)
            if interface is None:
                continue
            for method_name in interface.methods:
                providers.setdefault(method_name, []).append(interface_name)

        for method_name, interface_names in providers.items():
            own = info.methods.get(method_name)
            inherited = (
                self._find_class_method(info.superclass, method_name) if own is None else None
            )

            if own is None and inherited is None and len(interface_names) > 1:
                self._error(
                    stmt.name,
                    f"Class '{info.name}' must override '{method_name}': "
                    f"interfaces {', '.join(repr(name) for name in interface_names)} "
                    "declare it.",
                    code=Code.INVALID_OVERRIDE,
                )
                continue

            for interface_name in info.interfaces:
                interface = self._interfaces.get(interface_name)
                if interface is None:
                    continue
                required = interface.methods.get(method_name)
                if required is None:
                    continue

                implementation = own if own is not None else inherited
                if implementation is not None:
                    # Interface exige assinatura exata na v1: a ABI do itab é a da
                    # interface, então covariância/contravariância de representação
                    # diferente não é segura no backend (ADR-0080).
                    if required != implementation:
                        token = info.method_tokens[method_name] if own is not None else stmt.name
                        self._error(
                            token,
                            f"Method '{method_name}' is incompatible with "
                            f"interface '{interface_name}': expected "
                            f"{display(required)}, found {display(implementation)}.",
                            code=Code.INVALID_OVERRIDE,
                        )
                    continue

                if interface.defaults.get(method_name):
                    continue

                self._error(
                    stmt.name,
                    f"Class '{info.name}' must implement method '{method_name}' "
                    f"of interface '{interface_name}'.",
                    code=Code.INVALID_OVERRIDE,
                )

    def _check_overrides(self) -> None:
        for info in self._classes.values():
            if info.superclass is None:
                continue

            for name, signature in info.methods.items():
                superclass_signature = self._find_method(info.superclass, name)
                if superclass_signature is None:
                    continue
                if not self._assignable(superclass_signature, signature):
                    token = info.method_tokens[name]
                    replacement = f"{name}_impl"
                    fix = Fix(
                        Applicability.UNSAFE,
                        f"Rename the method to '{replacement}'.",
                        (
                            Edit(
                                span_of_token(token, self._reporter.file),
                                replacement,
                            ),
                        ),
                    )
                    self._error(
                        token,
                        f"Method '{name}' is incompatible with the superclass "
                        f"method: expected {display(superclass_signature)}, "
                        f"found {display(signature)}.",
                        code=Code.INVALID_OVERRIDE,
                        fixes=(fix,),
                    )

    def _default_value(self, ty: Ty | None) -> str | None:
        if ty is None:
            return None
        if is_nilable(ty):
            return "nil"
        if ty is INT:
            return "0"
        if ty is FLOAT:
            return "0.0"
        if ty is BOOL:
            return "false"
        if ty is STRING:
            return '""'
        if isinstance(ty, ListTy):
            return "[]"
        if isinstance(ty, MapTy):
            return "{}"
        return None

    def _literal_type(self, expr: Expr) -> Ty | None:
        """Tipo exato de um default constante (literal/`-literal`), sem inferência."""
        if isinstance(expr, Grouping):
            return self._literal_type(expr.expression)
        if isinstance(expr, Literal):
            value = expr.value
            if isinstance(value, bool):
                return BOOL
            if isinstance(value, int):
                return INT
            if isinstance(value, float):
                return FLOAT
            if isinstance(value, str):
                return STRING
            return None
        if isinstance(expr, Unary) and expr.operator.type is TokenType.MINUS:
            inner = self._literal_type(expr.right)
            if inner is INT or inner is FLOAT:
                return inner
        return None

    def _return_literal_type(self, stmt: Function) -> Ty | None:
        """Tipo exato dos `return` do corpo, só quando todos são literais iguais.

        Funções aninhadas, classes e lambdas não contam: os `return` delas pertencem a
        outra assinatura. Sem `return`, o corpo cai em `nil`.
        """
        types: list[Ty] = []
        unsupported = False

        def walk(value: object) -> None:
            nonlocal unsupported
            if isinstance(value, Token):
                return
            if isinstance(value, (Function, Class, Lambda)):
                return
            if isinstance(value, Return):
                if value.value is None:
                    types.append(NIL)
                else:
                    ty = self._literal_type(value.value)
                    if ty is None:
                        unsupported = True
                    else:
                        types.append(ty)
                return
            if is_dataclass(value) and not isinstance(value, type):
                for item in fields(value):
                    walk(getattr(value, item.name))
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)

        for inner in stmt.body:
            walk(inner)
        if unsupported or not types:
            return None if unsupported else NIL
        if any(ty != types[0] for ty in types):
            return None
        if types[0] is not NIL and not self._body_always_returns(stmt.body):
            return None
        return types[0]

    def _annotation_fix(
        self,
        token: Token | None,
        ty: Ty | None,
        *,
        prefix: str,
        public: bool,
    ) -> tuple[Fix, ...]:
        """Fix de anotação só quando o tipo é exato; nunca com `Any`/type var."""
        if token is None or ty is None or ty in (ANY, ERROR):
            return ()
        if isinstance(ty, TyVar) or self._has_any_type_var(ty):
            return ()
        span = span_of_token(token, self._reporter.file)
        point = Span(span.file, span.end, span.end)
        rendered = display(ty)
        message = (
            f"Add return type '{rendered}'."
            if prefix.strip().startswith("->")
            else f"Annotate as '{rendered}'."
        )
        return (
            Fix(
                Applicability.UNSAFE if public else Applicability.SAFE,
                message,
                (Edit(point, prefix + rendered),),
            ),
        )

    def _initialization_fixes(self, field: Field) -> tuple[Fix, ...]:
        if field.end is None:
            return ()
        default = self._default_value(field.type_annotation)
        if default is None:
            return ()
        span = span_of_token(field.end, self._reporter.file)
        point = span.start if field.end.lexeme == ";" else span.end
        at = Span(span.file, point, point)
        return (
            Fix(
                Applicability.UNSAFE,
                f"Initialize with '{default}'.",
                (Edit(at, f" = {default}"),),
            ),
        )

    def _check_field_initialization(self, stmt: Class, info: ClassInfo) -> None:
        required = {field.name.lexeme: field for field in stmt.fields if field.initializer is None}
        if not required:
            return

        initializer = next(
            (method for method in stmt.methods if method.name.lexeme == "init"),
            None,
        )
        if initializer is None:
            for field in stmt.fields:
                if field.name.lexeme in required:
                    self._error(
                        field.name,
                        f"Field '{field.name.lexeme}' must be initialized.",
                        code=Code.MISSING_INITIALIZATION,
                        fixes=self._initialization_fixes(field),
                    )
            return

        assigned = {field.name.lexeme for field in stmt.fields if field.initializer is not None}
        returns: list[set[str]] = []
        normal = self._init_flow(initializer.body, set(assigned), returns)

        states = list(returns)
        if normal is not None:
            states.append(normal)

        missing: set[str] = set()
        for state in states:
            missing.update(name for name in required if name not in state)

        for field in stmt.fields:
            if field.name.lexeme in missing:
                self._error(
                    field.name,
                    f"Field '{field.name.lexeme}' must be initialized.",
                    code=Code.MISSING_INITIALIZATION,
                    fixes=self._initialization_fixes(field),
                )

    def _init_flow(
        self, statements: list[Stmt], assigned: set[str], returns: list[set[str]]
    ) -> set[str] | None:
        current: set[str] | None = set(assigned)
        for statement in statements:
            if current is None:
                break
            current = self._init_stmt(statement, current, returns)

        return current

    def _init_stmt(
        self, stmt: Stmt, assigned: set[str], returns: list[set[str]]
    ) -> set[str] | None:
        if isinstance(stmt, Expression):
            self._mark_field_assignments(stmt.expression, assigned)
            return assigned
        if isinstance(stmt, Block):
            return self._init_flow(stmt.statements, set(assigned), returns)
        if isinstance(stmt, If):
            self._mark_field_assignments(stmt.condition, assigned)
            then_state = self._init_flow([stmt.then_branch], set(assigned), returns)
            if stmt.else_branch is None:
                else_state: set[str] | None = set(assigned)
            else:
                else_state = self._init_flow([stmt.else_branch], set(assigned), returns)

            if then_state is None:
                return else_state
            if else_state is None:
                return then_state
            return then_state & else_state
        if isinstance(stmt, While):
            self._mark_field_assignments(stmt.condition, assigned)
            self._init_flow([stmt.body], set(assigned), returns)
            return assigned
        if isinstance(stmt, ForIn):
            self._mark_field_assignments(stmt.iterable, assigned)
            self._init_flow([stmt.body], set(assigned), returns)
            return assigned
        if isinstance(stmt, Return):
            if stmt.value is not None:
                self._mark_field_assignments(stmt.value, assigned)
            returns.append(set(assigned))
            return None
        if isinstance(stmt, Var):
            if stmt.initializer is not None:
                self._mark_field_assignments(stmt.initializer, assigned)
            return assigned
        return assigned

    def _mark_field_assignments(self, expr: Expr | None, assigned: set[str]) -> None:
        if expr is None:
            return
        if isinstance(expr, Grouping):
            self._mark_field_assignments(expr.expression, assigned)
            return
        if isinstance(expr, Set) and isinstance(expr.object, This):
            assigned.add(expr.name.lexeme)
            self._mark_field_assignments(expr.value, assigned)

    def visit_expression_stmt(self, stmt: Expression) -> None:
        self._infer(stmt.expression)

    def visit_for_in_stmt(self, stmt: ForIn) -> None:
        iterable = self._infer(stmt.iterable)
        element = self.element_type(iterable, stmt.name)

        if isinstance(iterable, (ClassTy, InterfaceTy)) or iterable is ANY:
            self._invalidate_members()
            self._invalidate_captured()
        base = dict(self._narrowings)
        self._begin_scope()
        self._define(stmt.name, element)
        self._check_stmt(stmt.body)
        body_state = dict(self._narrowings)
        self._end_scope()
        # O corpo pode executar zero vezes; só sobrevive o que vale nos dois caminhos.
        self._narrowings = self._join_states(base, body_state)

    def element_type(self, iterable: Ty, token: Token) -> Ty:
        """Tipo do elemento de um iterável; checker e LSP (inlay hints) compartilham."""
        if iterable is ANY:
            return ANY
        if iterable is RANGE:
            return INT
        if iterable is STRING:
            return STRING
        if iterable is BYTES:
            return INT
        if isinstance(iterable, ListTy):
            return iterable.element
        if isinstance(iterable, MapTy):
            return iterable.key
        if isinstance(iterable, TupleTy):
            return union(*iterable.items)
        if isinstance(iterable, (ClassTy, InterfaceTy)):
            return self._iterator_element(iterable, token)

        self._error(
            token,
            "Can only iterate over a range, a list, a map or a string.",
            code=Code.INVALID_ITERATION,
        )
        return ERROR

    def _method_on_type(self, ty: Ty, name: str) -> FnTy | None:
        if isinstance(ty, ClassTy):
            method = self._find_method(ty.name, name)
            info = self._classes.get(ty.name)
            if method is not None and ty.args and info is not None and info.type_params:
                substituted = self._substitute(
                    method,
                    dict(zip(info.type_params, ty.args, strict=True)),
                )
                assert isinstance(substituted, FnTy)
                return substituted
            return method
        if isinstance(ty, InterfaceTy):
            interface_info = self._interfaces.get(ty.name)
            if interface_info is None:
                return None
            return interface_info.methods.get(name)

        return None

    def _iterator_element(self, iterable: Ty, token: Token) -> Ty:
        iter_method = self._method_on_type(iterable, "iter")
        if iter_method is None:
            self._error(
                token,
                f"'{display(iterable)}' is not iterable: define "
                "iter() returning an iterator with next() -> T?.",
                code=Code.INVALID_ITERATION,
            )
            return ERROR
        if len(iter_method.params) != 0 or iter_method.min_params != 0:
            self._error(
                token,
                "iter() must take no arguments.",
                code=Code.INVALID_ITERATION,
            )
            return ERROR

        iterator = iter_method.ret
        next_method = self._method_on_type(iterator, "next")
        if next_method is None:
            self._error(
                token,
                f"iter() must return an iterator with next() -> T?, found '{display(iterator)}'.",
                code=Code.INVALID_ITERATION,
            )
            return ERROR
        if len(next_method.params) != 0 or next_method.min_params != 0:
            self._error(
                token,
                "next() must take no arguments.",
                code=Code.INVALID_ITERATION,
            )
            return ERROR

        result = next_method.ret
        if not is_nilable(result):
            self._error(
                token,
                f"next() must return T?, found '{display(result)}'.",
                code=Code.INVALID_ITERATION,
            )
            return ERROR
        element = non_nil(result)
        if element is ANY or element is NEVER:
            self._error(
                token,
                "next() must return T? with a concrete T.",
                code=Code.INVALID_ITERATION,
            )
            return ERROR
        return element

    def visit_function_stmt(self, stmt: Function) -> None:
        signature = self._signatures.get(stmt)
        if signature is None:
            signature = self._signature(stmt, is_init=False)

        self._define(stmt.name, self._function_value_type(stmt.name.lexeme, signature))
        self._check_function_body(
            stmt,
            signature.fn,
            self._current_class,
            is_init=False,
            preserve_class=True,
            type_params=signature.type_params,
            type_param_names=signature.type_param_names,
        )

    def _signature(
        self, stmt: Function, *, is_init: bool, allow_type_params: bool = True
    ) -> FunctionSignature:
        names: tuple[str, ...] = ()
        variables: tuple[TyVar, ...] = ()

        if stmt.type_params and not allow_type_params:
            self._error(
                stmt.type_params[0],
                "Generic methods aren't supported yet.",
                code=Code.GENERIC_UNSUPPORTED,
            )
        elif stmt.type_params:
            variables, names = self._declare_type_params(stmt.type_params, stmt.type_param_bounds)

        type_params = variables
        type_param_names = names
        public = self._function_depth == 0
        self._push_type_params(type_param_names, type_params)
        try:
            param_types: list[Ty] = []
            minimum = 0
            variadic = False

            for index, param in enumerate(stmt.params):
                if param.variadic:
                    variadic = True
                    if index != len(stmt.params) - 1:
                        self._error(
                            param.name,
                            "Variadic parameter must be last.",
                            code=Code.INVALID_CHECKER_DECLARATION,
                        )
                    if param.default is not None:
                        self._error(
                            param.name,
                            "Variadic parameter can't have a default value.",
                            code=Code.INVALID_CHECKER_DECLARATION,
                        )
                    if param.type_annotation is None:
                        self._error(
                            param.name,
                            f"Variadic parameter '{param.name.lexeme}' needs a type annotation.",
                            code=Code.MISSING_ANNOTATION,
                        )
                        param_ty: Ty = ANY
                    else:
                        param_ty = self._storage_annotation(
                            self._resolve_type(param.type_annotation, param.name),
                            param.name,
                            "Parameters",
                        )
                    param_types.append(param_ty)
                    continue

                if param.type_annotation is None:
                    suggested = (
                        self._literal_type(param.default) if param.default is not None else None
                    )
                    self._error(
                        param.name,
                        f"Parameter '{param.name.lexeme}' needs a type annotation.",
                        code=Code.MISSING_ANNOTATION,
                        fixes=self._annotation_fix(
                            param.name,
                            suggested,
                            prefix=": ",
                            public=public,
                        ),
                    )
                    param_ty = ANY
                else:
                    param_ty = self._storage_annotation(
                        self._resolve_type(param.type_annotation, param.name),
                        param.name,
                        "Parameters",
                    )

                if param.default is not None:
                    self._check(param.default, param_ty, param.name)
                else:
                    minimum += 1

                param_types.append(param_ty)

            if is_init and variadic:
                self._error(
                    stmt.name,
                    "Variadic parameters aren't supported in 'init' yet.",
                    code=Code.GENERIC_UNSUPPORTED,
                )

            if is_init:
                if stmt.return_type is not None:
                    self._error(
                        stmt.name,
                        "Initializer can't declare a return type.",
                        code=Code.INVALID_CHECKER_DECLARATION,
                    )
                assert self._current_class is not None
                return_ty: Ty = ClassTy(self._current_class.name, self._current_class.type_params)
            elif stmt.return_type is None:
                self._error(
                    stmt.name,
                    f"Function '{stmt.name.lexeme}' needs a return type annotation.",
                    code=Code.MISSING_ANNOTATION,
                    fixes=self._annotation_fix(
                        stmt.params_end,
                        self._return_literal_type(stmt),
                        prefix=" -> ",
                        public=public,
                    ),
                )
                return_ty = ANY
            else:
                return_ty = self._resolve_type(stmt.return_type, stmt.name)
        finally:
            self._pop_type_params()

        return FunctionSignature(
            type_params,
            type_param_names,
            FnTy(tuple(param_types), return_ty, minimum, variadic),
        )

    def _implicit_type_param_name(self, taken: list[str]) -> str:
        """Nome determinístico para um parâmetro sem anotação (`T`, `T2`, ...)."""
        index = 1
        while True:
            name = "T" if index == 1 else f"T{index}"
            if name not in taken:
                return name
            index += 1

    def _check_function_body(
        self,
        stmt: Function | Lambda,
        signature: FnTy,
        class_info: ClassInfo | None,
        *,
        is_init: bool,
        preserve_class: bool = False,
        collect_returns: bool = False,
        check_return_paths: bool = True,
        type_params: tuple[TyVar, ...] = (),
        type_param_names: tuple[str, ...] = (),
        interface_info: InterfaceInfo | None = None,
    ) -> list[Ty]:
        enclosing_class = self._current_class
        enclosing_interface = self._current_interface
        enclosing_return = self._current_return
        enclosing_init = self._in_initializer
        enclosing_collector = self._return_collector
        enclosing_narrowings = dict(self._narrowings)
        self._narrowings = {}

        if not preserve_class:
            self._current_class = class_info
            if interface_info is not None:
                self._current_interface = interface_info
                self._current_class = None
        self._current_return = NIL if is_init else signature.ret
        self._in_initializer = is_init
        self._return_collector = [] if collect_returns else None

        generic = bool(type_params)
        if generic:
            self._push_type_params(type_param_names, type_params)
            assert isinstance(stmt, Function)
            self._generic_context.append((stmt.name.lexeme, type_params))

        self._function_depth += 1
        try:
            self._begin_scope()
            if not preserve_class and class_info is not None:
                self._scopes[-1]["this"] = ClassTy(class_info.name, class_info.type_params)
                if class_info.superclass is not None:
                    self._scopes[-1]["super"] = ClassObjectTy(class_info.superclass)
            elif not preserve_class and interface_info is not None:
                self._scopes[-1]["this"] = InterfaceTy(interface_info.name)

            for param, param_ty in zip(stmt.params, signature.params, strict=True):
                self._define(
                    param.name,
                    ListTy(param_ty) if param.variadic else param_ty,
                )

            for statement in stmt.body:
                self._check_stmt(statement)

            if (
                check_return_paths
                and isinstance(stmt, Function)
                and not is_init
                and signature.ret not in (ANY, NEVER, ERROR)
                and not is_nilable(signature.ret)
                and not self._body_always_returns(stmt.body)
            ):
                kind = (
                    "Method" if class_info is not None or interface_info is not None else "Function"
                )
                default = self._default_value(signature.ret)
                fixes: tuple[Fix, ...] = ()
                if default is not None and stmt.end is not None:
                    span = span_of_token(stmt.end, self._reporter.file)
                    at = Span(span.file, span.start, span.start)
                    fixes = (
                        Fix(
                            Applicability.UNSAFE,
                            f"Add 'return {default}' at the end.",
                            (Edit(at, f"\n  return {default}\n"),),
                        ),
                    )
                self._error(
                    stmt.name,
                    f"{kind} '{stmt.name.lexeme}' must return "
                    f"{display(signature.ret)} on all paths.",
                    code=Code.RETURN_PATH,
                    fixes=fixes,
                )

            self._end_scope()
        finally:
            self._function_depth -= 1
            self._current_class = enclosing_class
            self._current_interface = enclosing_interface
            self._current_return = enclosing_return
            self._in_initializer = enclosing_init
            collected = self._return_collector or []
            self._return_collector = enclosing_collector
            self._narrowings = enclosing_narrowings
            if generic:
                self._generic_context.pop()
                self._pop_type_params()

        return collected

    def visit_lambda_expr(self, expr: Lambda) -> Ty:
        return self._lambda_type(expr, None)

    def visit_is_expr(self, expr: Is) -> Ty:
        test_type = self._resolve_type(expr.test_type, expr.operator)
        self._validate_is_type(test_type, expr.operator)

        if isinstance(expr.left, ListLiteral) and not expr.left.elements:
            element = self._expected_element(test_type)
            if element is not None:
                self._check(expr.left, ListTy(element), expr.left.bracket)
            else:
                self._infer(expr.left)
        elif isinstance(expr.left, MapLiteral) and not expr.left.entries:
            entry_types = self._expected_map(test_type)
            if entry_types is not None:
                key_ty, value_ty = entry_types
                self._check(expr.left, MapTy(key_ty, value_ty), expr.left.brace)
            else:
                self._infer(expr.left)
        else:
            self._infer(expr.left)

        return BOOL

    def visit_as_expr(self, expr: As) -> Ty:
        target = self._resolve_type(expr.target_type, expr.operator)
        self._validate_as_target(target, expr.operator)
        source = self._infer(expr.left)

        if target is ERROR or source is ERROR:
            return target if target is not ERROR else ERROR
        if target is ANY:
            return ANY
        if source is ANY or source is target:
            return target
        if isinstance(target, TupleTy):
            if source == target:
                return target
            self._error(
                expr.operator,
                f"Can't cast {display(source)} to {display(target)}.",
                code=Code.INVALID_CAST,
            )
            return ERROR
        if target in (INT, FLOAT):
            if source in (INT, FLOAT):
                return target
        elif isinstance(target, ClassTy):
            if isinstance(source, ClassTy):
                return target
        elif source == target and (
            isinstance(target, (ListTy, MapTy)) or target in (BOOL, STRING, NIL, RANGE)
        ):
            return target

        self._error(
            expr.operator,
            f"Can't cast {display(source)} to {display(target)}.",
            code=Code.INVALID_CAST,
        )
        return ERROR

    def _validate_as_target(self, ty: Ty, token: Token) -> None:
        if ty is ERROR or ty is ANY:
            return
        if isinstance(ty, TyVar):
            # `x as T` é o cast dinâmico explícito de `Any` para um parâmetro
            # de tipo; a monomorfização resolve T para um tipo concreto.
            return
        if isinstance(ty, InterfaceTy):
            self._error(
                token,
                "Interface types aren't supported in 'as' yet.",
                code=Code.INVALID_CAST,
            )
            return
        if ty in (NIL, BOOL, INT, FLOAT, STRING, BYTES, RANGE):
            return
        if isinstance(ty, ClassTy):
            if ty.args:
                self._error(
                    token,
                    "as doesn't support type arguments on classes yet.",
                    code=Code.INVALID_CAST,
                )
            return
        if isinstance(ty, EnumTy):
            if ty.args:
                self._error(
                    token,
                    "as doesn't support type arguments on enums yet.",
                    code=Code.INVALID_CAST,
                )
            return
        if isinstance(ty, ListTy):
            self._validate_is_type(ty.element, token)
            return
        if isinstance(ty, MapTy):
            self._validate_is_type(ty.key, token)
            self._validate_is_type(ty.value, token)
            return
        if isinstance(ty, TupleTy):
            for item in ty.items:
                self._validate_is_type(item, token)
            return
        if isinstance(ty, UnionTy):
            self._error(
                token, "as doesn't support union types yet; narrow first.", code=Code.INVALID_CAST
            )
            return

        self._error(token, "as doesn't support this type yet.", code=Code.INVALID_CAST)

    def _validate_is_type(self, ty: Ty, token: Token) -> None:
        if ty is ERROR or ty is ANY or ty is NEVER:
            return
        if isinstance(ty, InterfaceTy):
            self._error(
                token,
                "Interface types aren't supported in 'is' yet.",
                code=Code.INVALID_TYPE_ANNOTATION,
            )
            return
        if ty in (NIL, BOOL, INT, FLOAT, STRING, BYTES, RANGE):
            return
        if isinstance(ty, ClassTy):
            if ty.args:
                self._error(
                    token,
                    "is doesn't support type arguments on classes yet.",
                    code=Code.TYPE_ARGUMENTS,
                )
            return
        if isinstance(ty, EnumTy):
            if ty.args:
                self._error(
                    token,
                    "is doesn't support type arguments on enums yet.",
                    code=Code.TYPE_ARGUMENTS,
                )
            return
        if isinstance(ty, ListTy):
            self._validate_is_type(ty.element, token)
            return
        if isinstance(ty, MapTy):
            self._validate_is_type(ty.key, token)
            self._validate_is_type(ty.value, token)
            return
        if isinstance(ty, TupleTy):
            for item in ty.items:
                self._validate_is_type(item, token)
            return
        if isinstance(ty, UnionTy):
            for member in ty.members:
                self._validate_is_type(member, token)
            return

        self._error(token, "is doesn't support this type yet.", code=Code.INVALID_OPERANDS)

    def _polymorphic_lambda(self, expr: Lambda) -> Ty:
        """Inferência + generalização de lambda em `val` (let-polymorphism, T4).

        Parâmetros sem anotação viram `TyVar`; o retorno é inferido; as variáveis que
        continuam livres no tipo final formam o esquema (`GenericFnTy`). Só vale para
        `val`: com `var` a mutação quebraria o esquema.
        """
        names: list[str] = []
        variables: list[TyVar] = []
        param_types: list[Ty] = []
        minimum = 0
        variadic = False

        for index, param in enumerate(expr.params):
            if param.variadic:
                variadic = True
                if index != len(expr.params) - 1:
                    self._error(
                        param.name,
                        "Variadic parameter must be last.",
                        code=Code.INVALID_CHECKER_DECLARATION,
                    )
                if param.default is not None:
                    self._error(
                        param.name,
                        "Variadic parameter can't have a default value.",
                        code=Code.INVALID_CHECKER_DECLARATION,
                    )
                if param.type_annotation is None:
                    self._error(
                        param.name,
                        f"Variadic parameter '{param.name.lexeme}' needs a type annotation.",
                        code=Code.MISSING_ANNOTATION,
                    )
                    param_ty: Ty = ANY
                else:
                    param_ty = self._resolve_type(param.type_annotation, param.name)
                param_types.append(param_ty)
                continue

            if param.type_annotation is not None:
                param_ty = self._resolve_type(param.type_annotation, param.name)
            else:
                name = self._implicit_type_param_name(names)
                variable = self._fresh_type_var(name)
                names.append(name)
                variables.append(variable)
                param_ty = variable

            if param.default is not None:
                self._check(param.default, param_ty, param.name)
            else:
                minimum += 1

            param_types.append(param_ty)

        declared_return: Ty | None = None
        if expr.return_type is not None:
            declared_return = self._resolve_type(expr.return_type, expr.keyword)

        signature = FnTy(
            tuple(param_types),
            declared_return if declared_return is not None else ANY,
            minimum,
            variadic,
        )
        returns = self._check_function_body(
            expr,
            signature,
            None,
            is_init=False,
            preserve_class=True,
            collect_returns=True,
            check_return_paths=False,
        )
        all_paths_return = self._body_always_returns(expr.body)
        if declared_return is not None:
            if (
                not all_paths_return
                and not is_nilable(declared_return)
                and declared_return not in (ANY, NEVER)
            ):
                self._error(
                    expr.keyword,
                    f"Lambda body must return {display(declared_return)}.",
                    code=Code.TYPE_MISMATCH,
                )
            return_ty = declared_return
        else:
            return_ty = self._infer_lambda_return(expr, returns, all_paths_return)
        fn = FnTy(tuple(param_types), return_ty, minimum, variadic)

        free = [variable for variable in variables if self._contains_any_type_var(fn, (variable,))]
        if not free:
            return fn

        return GenericFnTy("lambda", tuple(free), fn)

    def _lambda_type(self, expr: Lambda, expected: FnTy | None) -> Ty:
        param_types: list[Ty] = []
        variadic = False

        for index, param in enumerate(expr.params):
            if param.variadic:
                variadic = True
                if index != len(expr.params) - 1:
                    self._error(
                        param.name,
                        "Variadic parameter must be last.",
                        code=Code.INVALID_CHECKER_DECLARATION,
                    )
                if param.default is not None:
                    self._error(
                        param.name,
                        "Variadic parameter can't have a default value.",
                        code=Code.INVALID_CHECKER_DECLARATION,
                    )
                if param.type_annotation is not None:
                    param_ty = self._resolve_type(param.type_annotation, param.name)
                elif (
                    expected is not None and expected.variadic and index == len(expected.params) - 1
                ):
                    param_ty = expected.params[index]
                else:
                    self._error(
                        param.name,
                        f"Variadic parameter '{param.name.lexeme}' needs a type annotation.",
                        code=Code.MISSING_ANNOTATION,
                    )
                    param_ty = ANY
                param_types.append(param_ty)
                continue

            if param.type_annotation is not None:
                param_ty = self._resolve_type(param.type_annotation, param.name)
            elif expected is not None and index < len(expected.params):
                param_ty = expected.params[index]
            else:
                suggested = self._literal_type(param.default) if param.default is not None else None
                self._error(
                    param.name,
                    f"Parameter '{param.name.lexeme}' needs a type annotation; "
                    "use the lambda where a function type is expected.",
                    code=Code.MISSING_ANNOTATION,
                    fixes=self._annotation_fix(
                        param.name,
                        suggested,
                        prefix=": ",
                        public=False,
                    ),
                )
                param_ty = ANY

            if param.default is not None:
                self._check(param.default, param_ty, param.name)

            param_types.append(param_ty)

        declared_return: Ty | None = None
        if expr.return_type is not None:
            declared_return = self._resolve_type(expr.return_type, expr.keyword)
        elif expected is not None and not self._has_any_type_var(expected.ret):
            declared_return = expected.ret

        minimum = sum(1 for param in expr.params if param.default is None and not param.variadic)
        signature = FnTy(
            tuple(param_types),
            declared_return if declared_return is not None else ANY,
            minimum,
            variadic,
        )
        returns = self._check_function_body(
            expr,
            signature,
            None,
            is_init=False,
            preserve_class=True,
            collect_returns=True,
            check_return_paths=False,
        )

        all_paths_return = self._body_always_returns(expr.body)
        if declared_return is not None:
            if (
                not all_paths_return
                and not is_nilable(declared_return)
                and declared_return not in (ANY, NEVER)
            ):
                self._error(
                    expr.keyword,
                    f"Lambda body must return {display(declared_return)}.",
                    code=Code.TYPE_MISMATCH,
                )
            return_ty = declared_return
        else:
            return_ty = self._infer_lambda_return(expr, returns, all_paths_return)

        return FnTy(tuple(param_types), return_ty, minimum, variadic)

    def _infer_lambda_return(self, expr: Lambda, returns: list[Ty], all_paths_return: bool) -> Ty:
        if not returns:
            return NIL

        inferred = union(*returns)
        if not all_paths_return:
            inferred = union(inferred, NIL)

        if isinstance(inferred, UnionTy):
            non_nil = [member for member in inferred.members if member is not NIL]
            if len(non_nil) > 1 and len(returns) > 1:
                self._error(
                    expr.keyword,
                    f"Lambda returns {display(inferred)}; annotate the return type.",
                    code=Code.MISSING_ANNOTATION,
                )
                return ANY

        return inferred

    def visit_if_stmt(self, stmt: If) -> None:
        self._infer(stmt.condition)
        then_refinements = self._refinements(stmt.condition, True)
        else_refinements = self._refinements(stmt.condition, False)
        base = dict(self._narrowings)

        then_state, then_returns = self._check_branch(stmt.then_branch, then_refinements)
        if stmt.else_branch is not None:
            else_state, else_returns = self._check_branch(stmt.else_branch, else_refinements)
        else:
            else_state = dict(base)
            else_state.update(else_refinements)
            else_returns = False

        # Junta o estado dos caminhos que chegam ao fim do `if`.
        if then_returns and else_returns:
            self._narrowings = base
        elif then_returns:
            self._narrowings = dict(else_state)
        elif else_returns:
            self._narrowings = dict(then_state)
        else:
            self._narrowings = self._join_states(then_state, else_state)

    def _check_branch(
        self, stmt: Stmt, refinements: dict[RefinementKey, Ty]
    ) -> tuple[dict[RefinementKey, Ty], bool]:
        base = dict(self._narrowings)
        try:
            self._apply_refinements(refinements)
            self._check_stmt(stmt)
            state = dict(self._narrowings)
            returns = self._always_returns(stmt)
        finally:
            self._narrowings = base
        return state, returns

    def _join_states(
        self,
        left: dict[RefinementKey, Ty],
        right: dict[RefinementKey, Ty],
    ) -> dict[RefinementKey, Ty]:
        result: dict[RefinementKey, Ty] = {}
        for key in left.keys() & right.keys():
            left_ty = left[key]
            right_ty = right[key]
            if left_ty == right_ty:
                result[key] = left_ty
                continue
            merged = union(left_ty, right_ty)
            if merged is not NEVER:
                result[key] = merged
        return result

    def _refinements(self, expr: Expr, truth: bool) -> dict[RefinementKey, Ty]:
        if isinstance(expr, Grouping):
            return self._refinements(expr.expression, truth)

        if isinstance(expr, Unary) and expr.operator.type is TokenType.NOT:
            return self._refinements(expr.right, not truth)

        if isinstance(expr, Binary) and expr.operator.type in (
            TokenType.EQUAL_EQUAL,
            TokenType.NOT_EQUAL,
        ):
            left, right = expr.left, expr.right
            equal = expr.operator.type is TokenType.EQUAL_EQUAL
            if self._is_nil_literal(right):
                target = self._narrowable(left)
                if target is not None:
                    return self._nil_refinement(*target, truth, equal=equal)

            if self._is_nil_literal(left):
                target = self._narrowable(right)
                if target is not None:
                    return self._nil_refinement(*target, truth, equal=equal)

        if isinstance(expr, Is):
            target = self._narrowable(expr.left)
            if target is None:
                return {}

            key, current = target
            narrowed = (
                self._narrow_to(current, expr.test_type)
                if truth
                else self._narrow_away(current, expr.test_type)
            )
            if narrowed is None or narrowed == current:
                return {}

            return {key: narrowed}

        if isinstance(expr, Logical) and (
            (expr.operator.type is TokenType.AND and truth)
            or (expr.operator.type is TokenType.OR and not truth)
        ):
            return self._merge_refinements(
                self._refinements(expr.left, truth),
                self._refinements(expr.right, truth),
            )

        target = self._narrowable(expr)
        if target is not None:
            key, current = target
            ty = truthy(current) if truth else falsy(current)
            return {key: ty} if ty != current else {}

        return {}

    def _narrowable(self, expr: Expr) -> tuple[RefinementKey, Ty] | None:
        key = self._refinement_path(expr)
        if key is None:
            return None
        current = self._peek_type(expr)
        if current is None or current is ERROR:
            return None
        return key, current

    def _refinement_path(self, expr: Expr) -> RefinementKey | None:
        """Caminho refinável: variável, ou campos/índices literais encadeados."""
        if isinstance(expr, Variable):
            found = self._find_decl(expr.name.lexeme)
            if found is None:
                return None
            return found[0], expr.name.lexeme, ()

        if isinstance(expr, Get):
            base = self._refinement_path(expr.object)
            if base is None:
                return None
            return base[0], base[1], base[2] + (("field", expr.name.lexeme),)

        if isinstance(expr, Index):
            base = self._refinement_path(expr.object)
            segment = self._literal_segment(expr.index)
            if base is None or segment is None:
                return None
            return base[0], base[1], base[2] + (segment,)

        return None

    def _literal_segment(self, expr: Expr) -> tuple[str, object] | None:
        if isinstance(expr, Grouping):
            return self._literal_segment(expr.expression)
        if not isinstance(expr, Literal):
            return None
        value = expr.value
        if value is None:
            return None
        return "index", (type(value).__name__, value)

    def _peek_type(self, expr: Expr) -> Ty | None:
        """Tipo atual sem reportar erro: usado só para calcular refinamentos."""
        if isinstance(expr, Variable):
            if self._find_decl(expr.name.lexeme) is None:
                return None
            return self._lookup(expr.name)

        if isinstance(expr, Get):
            return self._peek_member(self._peek_type(expr.object), expr.name.lexeme)

        if isinstance(expr, Index):
            base = self._peek_type(expr.object)
            if base is None or base is ANY or base is ERROR:
                return None
            if isinstance(base, UnionTy):
                members = [member for member in base.members if member is not NIL]
                if len(members) != 1:
                    return None
                base = members[0]
            if isinstance(base, ListTy):
                return base.element
            if isinstance(base, MapTy):
                return base.value
            return None

        return None

    def _peek_member(self, base: Ty | None, name: str) -> Ty | None:
        if base is None or base is ANY or base is ERROR:
            return None
        if isinstance(base, UnionTy):
            members = [member for member in base.members if member is not NIL]
            if len(members) != 1:
                return None
            base = members[0]
        if not isinstance(base, ClassTy):
            return None
        field = self._find_field(base.name, name)
        return field.ty if field is not None else None

    def _narrowed_at(self, key: RefinementKey) -> Ty | None:
        return self._narrowings.get(key)

    def _nil_refinement(
        self, key: RefinementKey, declared: Ty, truth: bool, *, equal: bool
    ) -> dict[RefinementKey, Ty]:
        if equal:
            # x == nil
            narrowed = NIL if truth else non_nil(declared)
        else:
            # x != nil
            narrowed = non_nil(declared) if truth else NIL

        return {key: narrowed} if narrowed != declared else {}

    def _narrow_to(self, current: Ty, test: Ty) -> Ty | None:
        narrowed = self._intersect_types(current, test)
        if narrowed is NEVER or narrowed == current:
            return None

        return narrowed

    def _narrow_away(self, current: Ty, test: Ty) -> Ty | None:
        if current is ANY or current is ERROR:
            return None
        if self._is_test_subtype(current, test):
            return None
        if isinstance(current, UnionTy):
            remaining = [
                member for member in current.members if not self._is_test_subtype(member, test)
            ]
            if not remaining:
                return None
            narrowed = union(*remaining)
            return narrowed if narrowed != current else None

        return None

    def _is_test_subtype(self, actual: Ty, expected: Ty) -> bool:
        """Subtipo para teste de runtime, **sem** promoção `Int → Float`.

        `_assignable` é a relação de atribuição (aceita `Int` onde se espera `Float`); para
        `is`, `1` não é `Float`, então a relação precisa ser mais estrita.
        """
        if expected is ANY:
            return True
        if actual is NEVER:
            return True
        if actual == expected:
            return True
        if isinstance(expected, UnionTy):
            return any(self._is_test_subtype(actual, member) for member in expected.members)
        if isinstance(actual, UnionTy):
            return all(self._is_test_subtype(member, expected) for member in actual.members)
        if isinstance(actual, ClassTy) and isinstance(expected, ClassTy):
            if expected.args or actual.args:
                return actual.name == expected.name and actual.args == expected.args
            return self._is_subclass(actual.name, expected.name)
        if isinstance(actual, EnumTy) and isinstance(expected, EnumTy):
            return actual.name == expected.name and (
                not expected.args or actual.args == expected.args
            )
        if isinstance(actual, ListTy) and isinstance(expected, ListTy):
            return expected.element is ANY or self._is_test_subtype(
                actual.element, expected.element
            )
        if isinstance(actual, MapTy) and isinstance(expected, MapTy):
            key_ok = expected.key is ANY or self._is_test_subtype(actual.key, expected.key)
            value_ok = expected.value is ANY or self._is_test_subtype(actual.value, expected.value)
            return key_ok and value_ok
        if isinstance(actual, TupleTy) and isinstance(expected, TupleTy):
            return len(actual.items) == len(expected.items) and all(
                self._is_test_subtype(actual_item, expected_item)
                for actual_item, expected_item in zip(actual.items, expected.items, strict=True)
            )

        return False

    def _intersect_types(self, left: Ty, right: Ty) -> Ty:
        if left is ANY:
            return right
        if right is ANY:
            return left
        if left is ERROR or right is ERROR:
            return ERROR
        if left is NEVER or right is NEVER:
            return NEVER
        if left == right:
            return left
        if isinstance(left, UnionTy):
            return union(*(self._intersect_types(member, right) for member in left.members))
        if isinstance(right, UnionTy):
            return union(*(self._intersect_types(left, member) for member in right.members))
        if self._is_test_subtype(left, right):
            return left
        if self._is_test_subtype(right, left):
            return right

        return NEVER

    def _merge_refinements(
        self, left: dict[RefinementKey, Ty], right: dict[RefinementKey, Ty]
    ) -> dict[RefinementKey, Ty]:
        result = dict(left)
        for name, ty in right.items():
            if name not in result:
                result[name] = ty
                continue

            merged = self._intersect_types(result[name], ty)
            if merged is NEVER:
                result.pop(name)
            else:
                result[name] = merged

        return result

    def _is_nil_literal(self, expr: Expr) -> bool:
        return isinstance(expr, Literal) and expr.value is None

    def _as_variable(self, expr: Expr) -> Variable | None:
        if isinstance(expr, Grouping):
            return self._as_variable(expr.expression)
        if isinstance(expr, Variable):
            return expr

        return None

    def _always_returns(self, stmt: Stmt) -> bool:
        if isinstance(stmt, Return):
            return True
        if isinstance(stmt, Raise):
            return True
        if isinstance(stmt, Try):
            if stmt.finally_body is not None and self._body_always_returns(stmt.finally_body):
                return True
            if not self._body_always_returns(stmt.body):
                return False
            return all(self._body_always_returns(clause.body) for clause in stmt.handlers)
        if isinstance(stmt, Block):
            return any(self._always_returns(inner) for inner in stmt.statements)
        if isinstance(stmt, If):
            return (
                stmt.else_branch is not None
                and self._always_returns(stmt.then_branch)
                and self._always_returns(stmt.else_branch)
            )

        return False

    def _body_always_returns(self, body: list[Stmt]) -> bool:
        return any(self._always_returns(stmt) for stmt in body)

    def _resolve_exception_type(self, token: Token) -> Ty:
        info = self._classes.get(token.lexeme)
        if info is None:
            self._error(token, f"Unknown exception type '{token.lexeme}'.", code=Code.UNKNOWN_TYPE)
            return ERROR
        if not self._is_subclass(token.lexeme, "Exception"):
            self._error(
                token,
                f"Type '{token.lexeme}' isn't an exception.",
                code=Code.TYPE_MISMATCH,
            )
            return ERROR

        return ClassTy(token.lexeme)

    def _check_list_from(
        self, statements: list[Stmt], state: dict[RefinementKey, Ty]
    ) -> dict[RefinementKey, Ty]:
        """Checa uma lista em escopo novo, partindo de `state`, e devolve a saída."""
        self._narrowings = dict(state)
        self._begin_scope()
        try:
            for statement in statements:
                self._check_stmt(statement)
        finally:
            self._end_scope()
        return dict(self._narrowings)

    def visit_try_stmt(self, stmt: Try) -> None:
        base = dict(self._narrowings)
        body_state = self._check_list_from(stmt.body, base)
        body_returns = self._body_always_returns(stmt.body)

        handler_states: list[dict[RefinementKey, Ty]] = []
        handler_returns: list[bool] = []
        for index, clause in enumerate(stmt.handlers):
            exception_ty = self._resolve_exception_type(clause.type_name)
            if clause.type_name.lexeme == "Exception" and index != len(stmt.handlers) - 1:
                self._error(
                    clause.type_name,
                    "Catch-all 'Exception' must be the last handler.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )

            self._narrowings = dict(base)
            self._begin_scope()
            self._define(clause.binding, exception_ty)
            self._except_depth += 1
            try:
                for statement in clause.body:
                    self._check_stmt(statement)
            finally:
                self._except_depth -= 1
                self._end_scope()
            handler_states.append(dict(self._narrowings))
            handler_returns.append(self._body_always_returns(clause.body))

        continuing: list[dict[RefinementKey, Ty]] = []
        if not body_returns:
            continuing.append(body_state)
        for state, returns in zip(handler_states, handler_returns, strict=True):
            if not returns:
                continuing.append(state)
        if not continuing:
            continuing.append(base)
        merged = continuing[0]
        for state in continuing[1:]:
            merged = self._join_states(merged, state)
        self._narrowings = merged

        if stmt.finally_body is not None:
            self._narrowings = self._check_list_from(stmt.finally_body, merged)

    def visit_raise_stmt(self, stmt: Raise) -> None:
        if stmt.value is None:
            if self._except_depth == 0:
                self._error(
                    stmt.keyword,
                    "Can't re-raise outside of an except block.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
            return

        raised = self._infer(stmt.value)
        if raised is ERROR:
            return
        if raised is ANY or not self._assignable(ClassTy("Exception"), raised):
            self._error(
                stmt.keyword,
                f"Can only raise Exception instances, found {display(raised)}.",
                notes=self._provenance_notes(stmt.value, stmt.keyword),
                code=Code.TYPE_MISMATCH,
            )

    def _expr_token(self, expr: Expr) -> Token | None:
        if isinstance(expr, Variable):
            return expr.name
        if isinstance(expr, Get):
            return expr.name
        if isinstance(expr, Index):
            return expr.bracket
        if isinstance(expr, Call):
            return expr.paren
        if isinstance(expr, Grouping):
            return self._expr_token(expr.expression)
        if isinstance(expr, Lambda):
            return expr.keyword

        return None

    def visit_return_stmt(self, stmt: Return) -> None:
        if stmt.value is None:
            if self._return_collector is not None:
                self._return_collector.append(NIL)

            if (
                self._current_return is not None
                and not is_nilable(self._current_return)
                and self._current_return not in (ANY, NEVER, ERROR)
            ):
                self._error(
                    stmt.keyword,
                    f"Expected {display(self._current_return)}, found Nil.",
                    code=Code.TYPE_MISMATCH,
                )
            return

        if self._in_initializer:
            self._error(
                stmt.keyword,
                "Can't return a value from an initializer.",
                code=Code.INVALID_CHECKER_DECLARATION,
            )
            return

        if self._current_return is not None:
            actual = self._check(stmt.value, self._current_return, stmt.keyword)
        else:
            actual = self._infer(stmt.value)

        if self._return_collector is not None:
            self._return_collector.append(actual)

    def _storage_annotation(self, ty: Ty, token: Token, what: str) -> Ty:
        """`Nil` não tem representação de slot no backend; recusa no check."""
        if ty is NIL:
            self._error(
                token,
                f"{what} of type Nil are not supported; use `Any`.",
                code=Code.INVALID_TYPE_ANNOTATION,
            )
            return ANY
        return ty

    def visit_var_stmt(self, stmt: Var) -> None:
        if (
            stmt.type_annotation is None
            and not stmt.mutable
            and isinstance(stmt.initializer, Lambda)
        ):
            # T4: `val f = fn(x) => x` generaliza para um esquema polimórfico.
            scheme = self._polymorphic_lambda(stmt.initializer)
            self.types[stmt.initializer] = scheme
            self.storage_types[stmt.initializer] = scheme
            self._define(stmt.name, scheme)
            return

        if stmt.type_annotation is not None:
            annotated = self._storage_annotation(
                self._resolve_type(stmt.type_annotation, stmt.name), stmt.name, "Variables"
            )
            if stmt.initializer is not None:
                self._check(stmt.initializer, annotated, stmt.name)
            self._define(stmt.name, annotated)
            return

        if stmt.initializer is None:
            self._error(
                stmt.name,
                f"Can't infer type of '{stmt.name.lexeme}'; add an annotation.",
                code=Code.MISSING_ANNOTATION,
            )
            self._define(stmt.name, ANY)
            return

        inferred = self._infer(stmt.initializer)
        if isinstance(inferred, GenericFnTy):
            self._generic_value_error(stmt.name, inferred.name)
            self._define(stmt.name, ANY)
            return
        if stmt.mutable and inferred is NIL:
            self._error(
                stmt.name,
                f"Can't infer type of '{stmt.name.lexeme}' from nil; add an annotation.",
                code=Code.MISSING_ANNOTATION,
            )
            self._define(stmt.name, ANY)
            return

        self._define(stmt.name, inferred)

    def visit_error_stmt(self, stmt: ErrorStmt) -> None:
        return

    def visit_while_stmt(self, stmt: While) -> None:
        self._infer(stmt.condition)
        base = dict(self._narrowings)
        body_state, _ = self._check_branch(stmt.body, self._refinements(stmt.condition, True))
        # O laço pode executar zero vezes: junta a entrada com a saída do corpo e
        # depois aplica a condição falsa da saída normal.
        self._narrowings = self._join_states(base, body_state)
        self._apply_refinements(self._refinements(stmt.condition, False))

    # --- expressões ---

    def visit_assign_expr(self, expr: Assign) -> Ty:
        expected = self._lookup_declared(expr.name)
        assigned = self._check(expr.value, expected, expr.name)
        found = self._find_decl(expr.name.lexeme)
        if found is not None:
            index = found[0]
            self._invalidate(expr.name.lexeme, index)
            if assigned is not ERROR:
                self._narrowings[(index, expr.name.lexeme, ())] = assigned
        return expected

    def visit_binary_expr(self, expr: Binary) -> Ty:
        left = self._infer(expr.left)
        right = self._infer(expr.right)
        operator = expr.operator

        match operator.type:
            case TokenType.PLUS:
                if self._is_string(left) and self._is_string(right):
                    return STRING
                if left is ANY or right is ANY:
                    return ANY
                self._numeric(left, operator)
                self._numeric(right, operator)
                return self._promote(left, right, operator)
            case TokenType.MINUS | TokenType.STAR | TokenType.PERCENT:
                if left is ANY or right is ANY:
                    return ANY
                self._numeric(left, operator)
                self._numeric(right, operator)
                return self._promote(left, right, operator)
            case TokenType.SLASH:
                if left is ANY or right is ANY:
                    return ANY
                if isinstance(left, TyVar) or isinstance(right, TyVar):
                    self._error(
                        operator,
                        "Operator '/' always returns Float; it isn't "
                        "available on a type parameter.",
                        code=Code.INVALID_OPERANDS,
                    )
                    return ERROR
                self._numeric(left, operator)
                self._numeric(right, operator)
                return FLOAT
            case TokenType.SLASH_SLASH:
                return self._integer_result(left, right, operator)
            case TokenType.STAR_STAR:
                return self._power_type(left, right, operator)
            case (
                TokenType.AMPERSAND
                | TokenType.PIPE
                | TokenType.CARET
                | TokenType.LESS_LESS
                | TokenType.GREATER_GREATER
                | TokenType.GREATER_GREATER_GREATER
            ):
                return self._integer_result(left, right, operator)
            case TokenType.GREATER | TokenType.GREATER_EQUAL:
                return self._comparison(left, right, operator)
            case TokenType.LESS | TokenType.LESS_EQUAL:
                return self._comparison(left, right, operator)
            case TokenType.EQUAL_EQUAL | TokenType.NOT_EQUAL:
                return BOOL

        return ANY

    def _integer_result(self, left: Ty, right: Ty, operator: Token) -> Ty:
        if left is ANY or right is ANY:
            return ANY

        self._integer(left, operator)
        self._integer(right, operator)
        return INT

    def _integer(self, ty: Ty, token: Token) -> None:
        if ty is INT or ty is ANY:
            return

        self._error(token, "Operands must be integers.", lowerable=True, code=Code.INVALID_OPERANDS)

    def _power_type(self, left: Ty, right: Ty, operator: Token) -> Ty:
        if left is ANY or right is ANY:
            return ANY
        if isinstance(left, TyVar) or isinstance(right, TyVar):
            if (
                isinstance(left, TyVar)
                and isinstance(right, TyVar)
                and left == right
                and "Num" in left.bounds
            ):
                return left
            if (isinstance(left, TyVar) and left.bounds) or (
                isinstance(right, TyVar) and right.bounds
            ):
                self._error(
                    operator,
                    "Operands must be the same type parameter constrained by 'Num'.",
                    code=Code.INVALID_OPERANDS,
                )
            else:
                self._error(
                    operator,
                    "Operands must be numbers.",
                    code=Code.INVALID_OPERANDS,
                    lowerable=True,
                )
            return ERROR
        for ty in (left, right):
            if ty is INT or ty is FLOAT:
                continue
            self._error(
                operator, "Operands must be numbers.", lowerable=True, code=Code.INVALID_OPERANDS
            )
            return ERROR

        if left is FLOAT or right is FLOAT:
            return FLOAT

        return INT

    def _is_string(self, ty: Ty) -> bool:
        return ty is STRING

    def _comparison(self, left: Ty, right: Ty, operator: Token) -> Ty:
        if left is ANY or right is ANY:
            return BOOL
        if isinstance(left, TyVar) or isinstance(right, TyVar):
            if (
                isinstance(left, TyVar)
                and isinstance(right, TyVar)
                and left == right
                and "Ord" in left.bounds
            ):
                return BOOL
            if (isinstance(left, TyVar) and left.bounds) or (
                isinstance(right, TyVar) and right.bounds
            ):
                self._error(
                    operator,
                    "Comparisons need the same type parameter constrained by 'Ord'.",
                    code=Code.INVALID_OPERANDS,
                )
            else:
                self._error(
                    operator,
                    "Operands must be numbers.",
                    code=Code.INVALID_OPERANDS,
                    lowerable=True,
                )
            return BOOL
        if self._is_string(left) and self._is_string(right):
            return BOOL
        self._numeric(left, operator)
        self._numeric(right, operator)
        return BOOL

    def visit_call_expr(self, expr: Call) -> Ty:
        result = self._infer_call(expr, None, expr.paren)
        self._invalidate_members()
        if self._call_may_run_user_code(expr):
            self._invalidate_captured()
        return result

    def _infer_call(self, expr: Call, expected: Ty | None, token: Token) -> Ty:
        callee = self._infer(expr.callee)
        if isinstance(callee, GenericFnTy):
            return self._infer_generic_call(expr, callee, expected, token)
        if isinstance(callee, ClassObjectTy):
            info = self._classes.get(callee.name)
            if info is not None and info.type_params:
                return self._infer_class_construction(expr, callee, expected, token)

        signature = self._call_signature(callee, expr)
        arguments: list[Ty] = []

        for index, argument in enumerate(expr.arguments):
            expected_ty: Ty | None = None
            if signature is not None:
                if signature.variadic and index >= signature.fixed_params:
                    expected_ty = signature.params[-1]
                elif index < len(signature.params):
                    expected_ty = signature.params[index]
            expected_param = (
                self._expected_element(expected_ty) if expected_ty is not None else None
            )

            if isinstance(argument, Lambda) and expected_ty is not None:
                arguments.append(self._check(argument, expected_ty, expr.paren))
            elif (
                (isinstance(argument, ListLiteral) and expected_param is not None)
                or (
                    isinstance(argument, MapLiteral)
                    and expected_ty is not None
                    and self._expected_map(expected_ty) is not None
                )
                or (isinstance(argument, TupleLiteral) and isinstance(expected_ty, TupleTy))
            ):
                assert expected_ty is not None
                arguments.append(self._check(argument, expected_ty, expr.paren))
            else:
                arguments.append(self._infer(argument))

        return self._call_type(callee, expr, arguments)

    def _native_signature(self, name: str) -> FnTy | None:
        if name == "chars":
            return FnTy((STRING,), ListTy(STRING), 1)
        if name == "len":
            return FnTy((ANY,), INT, 1)
        if name in {"str", "repr"}:
            return FnTy((ANY,), STRING, 1)
        if name == "print":
            return FnTy((ANY,), NIL, 1)

        return None

    def _call_signature(self, callee: Ty, expr: Call) -> FnTy | None:
        if isinstance(callee, NativeFnTy):
            return self._native_signature(callee.name)
        if isinstance(callee, FnTy):
            return callee
        if isinstance(callee, ClassObjectTy):
            info = self._classes.get(callee.name)
            if info is None:
                return None
            return self._initializer(info) or FnTy((), ClassTy(callee.name), 0)
        if isinstance(callee, UnionTy):
            members = list(callee.members)
            if expr.optional:
                members = [member for member in members if member is not NIL]
            if len(members) != 1:
                return None

            member = members[0]
            if isinstance(member, FnTy):
                return member
            if isinstance(member, ClassObjectTy):
                info = self._classes.get(member.name)
                if info is None:
                    return None
                return self._initializer(info) or FnTy((), ClassTy(member.name), 0)

        return None

    def _call_type(self, callee: Ty, expr: Call, arguments: list[Ty]) -> Ty:
        if callee is ANY:
            return ANY
        if callee is ERROR:
            return ERROR

        nilable = callee is NIL or (
            isinstance(callee, UnionTy) and any(member is NIL for member in callee.members)
        )
        if nilable and not expr.optional:
            self._error(
                expr.paren,
                "Can only call functions and classes.",
                code=Code.NOT_CALLABLE,
            )
            return ERROR
        if callee is NIL:
            return NIL

        members = list(callee.members) if isinstance(callee, UnionTy) else [callee]
        if expr.optional:
            members = [member for member in members if member is not NIL]
        if not members:
            return NIL
        if any(member != members[0] for member in members):
            self._error(
                expr.paren,
                "Can only call functions and classes.",
                code=Code.NOT_CALLABLE,
            )
            return ERROR

        callable_ty = members[0]
        result: Ty

        if isinstance(callable_ty, ClassObjectTy):
            info = self._classes.get(callable_ty.name)
            if info is None:
                self._error(
                    expr.paren,
                    f"Unknown class '{callable_ty.name}'.",
                    code=Code.UNKNOWN_TYPE,
                )
                return ERROR

            signature = self._initializer(info) or FnTy((), ClassTy(callable_ty.name), 0)
            self._check_call(expr.paren, signature, arguments, expr.spread, expr)
            result = ClassTy(callable_ty.name)
        elif isinstance(callable_ty, FnTy):
            self._check_call(expr.paren, callable_ty, arguments, expr.spread, expr)
            result = callable_ty.ret
        elif isinstance(callable_ty, NativeFnTy):
            result = self._call_native(callable_ty, expr, arguments)
        else:
            self._error(
                expr.paren,
                "Can only call functions and classes.",
                code=Code.NOT_CALLABLE,
            )
            return ERROR

        return union(result, NIL) if expr.optional and nilable else result

    def _call_native(self, callee: NativeFnTy, expr: Call, arguments: list[Ty]) -> Ty:
        if expr.spread:
            self._error(
                expr.paren,
                "Spread arguments are only supported for variadic functions.",
                code=Code.ARITY_MISMATCH,
            )
            return ERROR
        for expression, argument in zip(expr.arguments, arguments, strict=True):
            if isinstance(argument, GenericFnTy):
                token = self._expr_token(expression) or expr.paren
                self._generic_value_error(token, argument.name)
                return ERROR
        if callee.name == "len":
            if len(arguments) != 1:
                self._error(
                    expr.paren,
                    f"Expected 1 arguments but got {len(arguments)}.",
                    code=Code.ARITY_MISMATCH,
                )
                return ERROR

            argument = arguments[0]
            if not self._is_len_able(argument):
                self._error(
                    expr.paren,
                    f"Expected a string, a list or a map, found {display(argument)}.",
                    code=Code.INVALID_OPERANDS,
                    notes=self._argument_notes(expr, 1, expr.paren),
                )
                return ERROR

            return INT

        if callee.name == "chars":
            if len(arguments) != 1:
                self._error(
                    expr.paren,
                    f"Expected 1 arguments but got {len(arguments)}.",
                    code=Code.ARITY_MISMATCH,
                )
                return ERROR

            argument = arguments[0]
            if argument is ERROR:
                return ERROR
            if argument is not ANY and not self._is_string(argument):
                self._error(
                    expr.paren,
                    f"chars() expects a string, found {display(argument)}.",
                    code=Code.INVALID_OPERANDS,
                    notes=self._argument_notes(expr, 1, expr.paren),
                )
                return ERROR

            return ListTy(STRING)

        if callee.name in {"str", "repr"}:
            if len(arguments) != 1:
                self._error(
                    expr.paren,
                    f"Expected 1 arguments but got {len(arguments)}.",
                    code=Code.ARITY_MISMATCH,
                )
                return ERROR

            if arguments[0] is ERROR:
                return ERROR

            return STRING

        if callee.name == "print":
            if len(arguments) != 1:
                self._error(
                    expr.paren,
                    f"Expected 1 arguments but got {len(arguments)}.",
                    code=Code.ARITY_MISMATCH,
                )
                return ERROR

            return NIL

        if callee.name.startswith("math."):
            return self._call_math(callee.name, expr, arguments)

        self._error(
            expr.paren,
            "Can only call functions and classes.",
            code=Code.NOT_CALLABLE,
        )
        return ERROR

    def _call_math(self, name: str, expr: Call, arguments: list[Ty]) -> Ty:
        expected = (
            3
            if name == "math.clamp"
            else 2
            if name
            in {
                "math.min",
                "math.max",
            }
            else 1
        )
        if len(arguments) != expected:
            self._error(
                expr.paren,
                f"Expected {expected} arguments but got {len(arguments)}.",
                code=Code.ARITY_MISMATCH,
            )
            return ERROR

        if any(argument is ERROR for argument in arguments):
            return ERROR
        if name == "math.abs":
            return self._math_numeric_result("math.abs", arguments, expr.paren, expr.arguments)
        if name in {"math.min", "math.max", "math.clamp"}:
            return self._math_numeric_result(name, arguments, expr.paren, expr.arguments)

        self._error(
            expr.paren,
            "Can only call functions and classes.",
            code=Code.NOT_CALLABLE,
        )
        return ERROR

    def _math_numeric_result(
        self,
        name: str,
        arguments: list[Ty],
        token: Token,
        expressions: list[Expr],
    ) -> Ty:
        for index, argument in enumerate(arguments):
            if argument is ANY:
                continue
            if argument is INT or argument is FLOAT:
                continue
            notes = (
                self._provenance_notes(expressions[index], token)
                if index < len(expressions)
                else ()
            )
            self._error(
                token,
                f"{name}() expects numbers.",
                code=Code.MATH_ARGUMENT,
                notes=notes,
            )
            return ERROR

        if any(argument is FLOAT for argument in arguments):
            return FLOAT
        if all(argument is INT for argument in arguments):
            return INT
        return union(INT, FLOAT)

    def _is_len_able(self, ty: Ty) -> bool:
        if ty is ANY or ty is STRING or ty is BYTES or ty is ERROR or isinstance(ty, ListTy):
            return True
        if isinstance(ty, MapTy):
            return True
        if isinstance(ty, TupleTy):
            return True
        if isinstance(ty, UnionTy):
            return all(self._is_len_able(member) for member in ty.members)

        return False

    def _check_call(
        self,
        token: Token,
        signature: FnTy,
        arguments: list[Ty],
        spread: bool = False,
        expr: Call | None = None,
    ) -> None:
        fixed = signature.fixed_params
        minimum = signature.min_params
        count = len(arguments)

        if spread:
            if not signature.variadic:
                self._error(
                    token,
                    "Spread arguments are only supported for variadic functions.",
                    code=Code.ARITY_MISMATCH,
                    lowerable=True,
                )
                return
            if count != fixed + 1:
                self._error(
                    token,
                    "Spread arguments only fill the variadic parameter; "
                    "pass the fixed parameters explicitly.",
                    code=Code.ARITY_MISMATCH,
                    lowerable=True,
                )
                return
            for index, argument in enumerate(arguments[:-1], start=1):
                if isinstance(argument, GenericFnTy):
                    self._generic_value_error(token, argument.name)
                    continue
                if not self._assignable(signature.params[index - 1], argument):
                    self._argument_error(
                        token, index, signature.params[index - 1], argument, call=expr
                    )
            expected_list = ListTy(signature.params[-1])
            if not self._assignable(expected_list, arguments[-1]):
                self._argument_error(token, count, expected_list, arguments[-1], call=expr)
            return

        if signature.variadic:
            if count < minimum:
                self._error(
                    token,
                    f"Expected at least {minimum} arguments but got {count}.",
                    code=Code.ARITY_MISMATCH,
                    lowerable=True,
                )
                return
            for index, argument in enumerate(arguments, start=1):
                if isinstance(argument, GenericFnTy):
                    self._generic_value_error(token, argument.name)
                    continue
                expected = (
                    signature.params[index - 1] if index - 1 < fixed else signature.params[-1]
                )
                if not self._assignable(expected, argument):
                    self._argument_error(token, index, expected, argument, call=expr)
            return

        maximum = len(signature.params)
        if not minimum <= count <= maximum:
            if minimum == maximum:
                message = f"Expected {minimum} arguments but got {count}."
            elif count < minimum:
                message = f"Expected at least {minimum} arguments but got {count}."
            else:
                message = f"Expected {minimum} to {maximum} arguments but got {count}."
            fixes: tuple[Fix, ...] = ()
            if (
                count > maximum
                and not spread
                and expr is not None
                and expr.arg_ends
                and maximum > 0
                and len(expr.commas) >= maximum
            ):
                start = expr.commas[maximum - 1]
                end = expr.arg_ends[-1]
                start_span = span_of_token(start, self._reporter.file)
                end_span = span_of_token(end, self._reporter.file)
                fixes = (
                    Fix(
                        Applicability.UNSAFE,
                        "Remove the extra arguments.",
                        (
                            Edit(
                                Span(
                                    start_span.file,
                                    start_span.start,
                                    end_span.end,
                                ),
                                "",
                            ),
                        ),
                    ),
                )
            self._error(
                token,
                message,
                code=Code.ARITY_MISMATCH,
                lowerable=True,
                fixes=fixes,
            )
            return

        for index, (argument, param) in enumerate(
            zip(arguments, signature.params, strict=False), start=1
        ):
            if isinstance(argument, GenericFnTy):
                self._generic_value_error(token, argument.name)
                continue
            if not self._assignable(param, argument):
                self._argument_error(token, index, param, argument, call=expr)

    def _instantiate_generic(self, callee: GenericFnTy) -> GenericFnTy:
        fresh = [
            self._fresh_type_var(parameter.name, parameter.bounds)
            for parameter in callee.type_params
        ]
        mapping: dict[TyVar, Ty] = {
            parameter: variable
            for parameter, variable in zip(callee.type_params, fresh, strict=True)
        }
        fn = self._substitute(callee.fn, mapping)
        assert isinstance(fn, FnTy)
        return GenericFnTy(callee.name, tuple(fresh), fn)

    def _infer_class_construction(
        self,
        expr: Call,
        callee: ClassObjectTy,
        expected: Ty | None,
        token: Token,
    ) -> Ty:
        if expr.spread:
            self._error(
                expr.paren,
                "Spread arguments are only supported for variadic functions.",
                code=Code.ARITY_MISMATCH,
            )
            return ERROR
        info = self._classes[callee.name]
        fresh = tuple(self._fresh_type_var(type_param.name) for type_param in info.type_params)
        mapping: dict[TyVar, Ty] = dict(zip(info.type_params, fresh, strict=True))
        # `init` herdado: `B(A)` sem `init` chama o `init` de `A`, mas o resultado é
        # uma instância de `B`. O template é sempre a própria classe.
        initializer = self._initializer(info)
        result_template = self._substitute(ClassTy(info.name, info.type_params), mapping)
        base = initializer or FnTy((), result_template, 0)
        signature_ty = self._substitute(base, mapping)
        assert isinstance(signature_ty, FnTy)
        signature = signature_ty
        bindings: dict[TyVar, Ty] = {}

        if (
            isinstance(expected, ClassTy)
            and expected.name == info.name
            and len(expected.args) == len(fresh)
        ):
            for variable, expected_arg in zip(fresh, expected.args, strict=True):
                bindings[variable] = expected_arg
        elif expected is not None and expected not in (ANY, ERROR):
            self._unify(result_template, expected, bindings, token)

        maximum = len(signature.params)
        minimum = signature.min_params
        count = len(expr.arguments)
        if not minimum <= count <= maximum:
            if minimum == maximum:
                message = f"Expected {minimum} arguments but got {count}."
            elif count < minimum:
                message = f"Expected at least {minimum} arguments but got {count}."
            else:
                message = f"Expected {minimum} to {maximum} arguments but got {count}."
            self._error(token, message, code=Code.ARITY_MISMATCH)
            return ERROR

        for index, argument in enumerate(expr.arguments):
            if index >= len(signature.params):
                break
            parameter_type = self._substitute(signature.params[index], bindings)
            actual = self._check_generic_argument(
                argument, parameter_type, bindings, token, index + 1
            )
            if actual is ERROR:
                return ERROR

        result = self._substitute(result_template, bindings)
        unbound = self._unbound_type_vars(result, fresh)
        if unbound:
            names = ", ".join(f"'{member.name}'" for member in unbound)
            self._error(
                token,
                f"Can't infer type argument(s) {names} for '{info.name}'; annotate the value.",
                code=Code.GENERIC_INFERENCE,
            )
            return ERROR

        if isinstance(result, ClassTy) and result.args:
            self.generic_classes.add(result)
            self.generic_class_sites[expr] = result
        return result

    def _infer_generic_call(
        self,
        expr: Call,
        callee: GenericFnTy,
        expected: Ty | None,
        token: Token,
    ) -> Ty:
        instance = self._instantiate_generic(callee)
        signature = instance.fn
        bindings: dict[TyVar, Ty] = {}

        if expected is not None and expected not in (ANY, ERROR):
            self._unify(signature.ret, expected, bindings, token)

        fixed = signature.fixed_params
        minimum = signature.min_params
        count = len(expr.arguments)
        if expr.spread:
            if not signature.variadic:
                self._error(
                    token,
                    "Spread arguments are only supported for variadic functions.",
                    code=Code.ARITY_MISMATCH,
                )
                return ERROR
            if count != fixed + 1:
                self._error(
                    token,
                    "Spread arguments only fill the variadic parameter; "
                    "pass the fixed parameters explicitly.",
                    code=Code.ARITY_MISMATCH,
                )
                return ERROR
        elif signature.variadic:
            if count < minimum:
                self._error(
                    token,
                    f"Expected at least {minimum} arguments but got {count}.",
                    code=Code.ARITY_MISMATCH,
                )
                return ERROR
        elif not minimum <= count <= len(signature.params):
            if minimum == len(signature.params):
                message = f"Expected {minimum} arguments but got {count}."
            elif count < minimum:
                message = f"Expected at least {minimum} arguments but got {count}."
            else:
                message = (
                    f"Expected {minimum} to {len(signature.params)} arguments but got {count}."
                )
            self._error(token, message, code=Code.ARITY_MISMATCH)
            return ERROR

        for index, argument in enumerate(expr.arguments):
            if index >= len(signature.params) and not signature.variadic:
                break
            parameter_type: Ty
            if expr.spread and index == len(expr.arguments) - 1:
                parameter_type = ListTy(signature.params[-1])
            elif signature.variadic and index >= fixed:
                parameter_type = signature.params[-1]
            else:
                parameter_type = signature.params[index]
            parameter_type = self._substitute(parameter_type, bindings)
            actual = self._check_generic_argument(
                argument, parameter_type, bindings, token, index + 1
            )
            if actual is ERROR:
                return ERROR

        self._check_type_bounds(instance.type_params, bindings, token)

        result = self._substitute(signature.ret, bindings)
        unbound = self._unbound_type_vars(result, instance.type_params)
        if unbound:
            names = ", ".join(f"'{variable.name}'" for variable in unbound)
            self._error(
                token,
                f"Can't infer type argument(s) {names}.",
                code=Code.GENERIC_INFERENCE,
            )
            return ERROR

        self._check_polymorphic_recursion(instance, bindings, token)
        if all(variable in bindings for variable in instance.type_params):
            self.generic_fn_instances[expr] = GenericFnInstance(
                callee.name,
                tuple(bindings[variable] for variable in instance.type_params),
            )
        return result

    def _check_type_bounds(
        self,
        variables: tuple[TyVar, ...],
        bindings: dict[TyVar, Ty],
        token: Token,
    ) -> None:
        for variable in variables:
            if not variable.bounds:
                continue
            actual = bindings.get(variable)
            if actual is None:
                continue
            for bound in variable.bounds:
                if self._satisfies_bound(actual, bound):
                    continue
                self._error(
                    token,
                    f"Type argument '{display(actual)}' for '{variable.name}' "
                    f"doesn't satisfy constraint '{bound}'.",
                    code=Code.TYPE_MISMATCH,
                )

    def _satisfies_bound(self, actual: Ty, bound: str) -> bool:
        if isinstance(actual, TyVar):
            return bound in actual.bounds
        if isinstance(actual, InterfaceTy):
            return actual.name == bound
        if bound == "Ord":
            return any(actual is candidate for candidate in ORD_TYPES)
        if bound == "Num":
            return any(actual is candidate for candidate in NUM_TYPES)
        if isinstance(actual, ClassTy):
            return self._implements_interface(actual.name, bound)
        return False

    def _check_generic_argument(
        self,
        expr: Expr,
        expected: Ty,
        bindings: dict[TyVar, Ty],
        token: Token,
        index: int,
    ) -> Ty:
        resolved = self._substitute(expected, bindings)

        if isinstance(resolved, TyVar):
            actual = self._infer(expr)
            if isinstance(actual, GenericFnTy):
                return self._generic_value_error(token, actual.name)
            if not self._unify(resolved, actual, bindings, token):
                self._argument_error(token, index, resolved, actual)
                return ERROR
            return actual

        if not self._has_any_type_var(resolved):
            return self._check(expr, resolved, token)

        if isinstance(expr, ListLiteral) and isinstance(resolved, ListTy):
            element = resolved.element
            for item in expr.elements:
                if self._check_generic_argument(item, element, bindings, token, index) is ERROR:
                    return ERROR
            return ListTy(self._substitute(element, bindings))

        if isinstance(expr, MapLiteral) and isinstance(resolved, MapTy):
            for key, value in expr.entries:
                if (
                    self._check_generic_argument(key, resolved.key, bindings, token, index) is ERROR
                    or self._check_generic_argument(value, resolved.value, bindings, token, index)
                    is ERROR
                ):
                    return ERROR
            return MapTy(
                self._substitute(resolved.key, bindings),
                self._substitute(resolved.value, bindings),
            )

        if isinstance(expr, Lambda) and isinstance(resolved, FnTy):
            actual = self._lambda_type(expr, resolved)
            if not self._unify(resolved, actual, bindings, token):
                self._argument_error(token, index, resolved, actual)
                return ERROR
            concrete = self._substitute(actual, bindings)
            self.types[expr] = concrete
            self.storage_types[expr] = concrete
            return actual

        if isinstance(expr, Call):
            actual = self._infer_call(expr, resolved, token)
            if actual is ERROR:
                return ERROR
            if not self._unify(resolved, actual, bindings, token):
                self._argument_error(token, index, resolved, actual)
                return ERROR
            return actual

        actual = self._infer(expr)
        if isinstance(actual, GenericFnTy):
            return self._generic_value_error(token, actual.name)
        if not self._unify(resolved, actual, bindings, token):
            self._error(
                token,
                f"Argument {index}: {self._mismatch_message(resolved, actual)}",
                code=Code.TYPE_MISMATCH,
            )
            return ERROR

        return actual

    def _generic_value_error(self, token: Token, name: str) -> Ty:
        self._error(
            token,
            f"Generic function '{name}' can't be used as a value yet; "
            "call it so its type arguments can be inferred.",
            code=Code.GENERIC_INFERENCE,
        )
        return ERROR

    def _substitute(self, ty: Ty, bindings: dict[TyVar, Ty]) -> Ty:
        if isinstance(ty, TyVar):
            replacement = bindings.get(ty)
            if replacement is None or replacement == ty:
                return ty
            return self._substitute(replacement, bindings)
        if isinstance(ty, ClassTy):
            return ClassTy(
                ty.name,
                tuple(self._substitute(arg, bindings) for arg in ty.args),
            )
        if isinstance(ty, EnumTy):
            return EnumTy(
                ty.name,
                tuple(self._substitute(arg, bindings) for arg in ty.args),
            )
        if isinstance(ty, ListTy):
            return ListTy(self._substitute(ty.element, bindings))
        if isinstance(ty, MapTy):
            return MapTy(
                self._substitute(ty.key, bindings),
                self._substitute(ty.value, bindings),
            )
        if isinstance(ty, TupleTy):
            return TupleTy(tuple(self._substitute(item, bindings) for item in ty.items))
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self._substitute(param, bindings) for param in ty.params),
                self._substitute(ty.ret, bindings),
                ty.min_params,
                ty.variadic,
            )
        if isinstance(ty, UnionTy):
            return union(*(self._substitute(member, bindings) for member in ty.members))

        return ty

    def _has_any_type_var(self, ty: Ty) -> bool:
        if isinstance(ty, TyVar):
            return True
        if isinstance(ty, ClassTy):
            return any(self._has_any_type_var(arg) for arg in ty.args)
        if isinstance(ty, EnumTy):
            return any(self._has_any_type_var(arg) for arg in ty.args)
        if isinstance(ty, ListTy):
            return self._has_any_type_var(ty.element)
        if isinstance(ty, MapTy):
            return self._has_any_type_var(ty.key) or self._has_any_type_var(ty.value)
        if isinstance(ty, TupleTy):
            return any(self._has_any_type_var(item) for item in ty.items)
        if isinstance(ty, FnTy):
            return any(self._has_any_type_var(param) for param in ty.params) or (
                self._has_any_type_var(ty.ret)
            )
        if isinstance(ty, UnionTy):
            return any(self._has_any_type_var(member) for member in ty.members)

        return False

    def _occurs(self, variable: TyVar, ty: Ty, bindings: dict[TyVar, Ty]) -> bool:
        ty = self._substitute(ty, bindings)
        if isinstance(ty, TyVar):
            return ty == variable
        if isinstance(ty, ClassTy):
            return any(self._occurs(variable, arg, bindings) for arg in ty.args)
        if isinstance(ty, EnumTy):
            return any(self._occurs(variable, arg, bindings) for arg in ty.args)
        if isinstance(ty, ListTy):
            return self._occurs(variable, ty.element, bindings)
        if isinstance(ty, MapTy):
            return self._occurs(variable, ty.key, bindings) or self._occurs(
                variable, ty.value, bindings
            )
        if isinstance(ty, TupleTy):
            return any(self._occurs(variable, item, bindings) for item in ty.items)
        if isinstance(ty, FnTy):
            return any(
                self._occurs(variable, param, bindings) for param in ty.params
            ) or self._occurs(variable, ty.ret, bindings)
        if isinstance(ty, UnionTy):
            return any(self._occurs(variable, member, bindings) for member in ty.members)

        return False

    def _unify(
        self,
        expected: Ty,
        actual: Ty,
        bindings: dict[TyVar, Ty],
        token: Token,
    ) -> bool:
        expected = self._substitute(expected, bindings)
        actual = self._substitute(actual, bindings)

        if expected is ERROR or actual is ERROR:
            return True
        if expected is ANY:
            return True
        if isinstance(expected, TyVar):
            if isinstance(actual, TyVar) and actual == expected:
                return True
            if actual is ANY:
                self._error(
                    token,
                    f"Can't infer type argument '{expected.name}' from Any.",
                    code=Code.GENERIC_INFERENCE,
                )
                return False
            if self._occurs(expected, actual, bindings):
                self._error(
                    token,
                    f"Recursive type inferred for '{expected.name}'.",
                    code=Code.GENERIC_INFERENCE,
                )
                return False
            bindings[expected] = actual
            return True

        if expected == actual:
            return True

        if isinstance(expected, ClassTy) and isinstance(actual, ClassTy):
            if expected.name != actual.name or len(expected.args) != len(actual.args):
                return False
            if not expected.args:
                return self._assignable(expected, actual)
            return all(
                self._unify(expected_arg, actual_arg, bindings, token)
                for expected_arg, actual_arg in zip(expected.args, actual.args, strict=True)
            )
        if isinstance(expected, EnumTy) and isinstance(actual, EnumTy):
            if expected.name != actual.name or len(expected.args) != len(actual.args):
                return False
            return all(
                self._unify(expected_arg, actual_arg, bindings, token)
                for expected_arg, actual_arg in zip(expected.args, actual.args, strict=True)
            )

        if not self._has_any_type_var(expected) and not self._has_any_type_var(actual):
            return self._assignable(expected, actual)

        if isinstance(expected, ListTy) and isinstance(actual, ListTy):
            return self._unify(expected.element, actual.element, bindings, token)
        if isinstance(expected, MapTy) and isinstance(actual, MapTy):
            return self._unify(expected.key, actual.key, bindings, token) and self._unify(
                expected.value, actual.value, bindings, token
            )
        if isinstance(expected, TupleTy) and isinstance(actual, TupleTy):
            return len(expected.items) == len(actual.items) and all(
                self._unify(expected_item, actual_item, bindings, token)
                for expected_item, actual_item in zip(expected.items, actual.items, strict=True)
            )
        if isinstance(expected, FnTy) and isinstance(actual, FnTy):
            if expected.variadic != actual.variadic:
                return False
            if actual.variadic:
                if len(expected.params) != len(actual.params):
                    return False
            elif not actual.min_params <= len(expected.params) <= len(actual.params):
                return False
            for expected_param, actual_param in zip(expected.params, actual.params, strict=False):
                if not self._unify(expected_param, actual_param, bindings, token):
                    return False
            return self._unify(expected.ret, actual.ret, bindings, token)
        if isinstance(expected, UnionTy):
            # `T?` unifica com `Int?` como T=Int, não T=Int? (opcional aninhado).
            if isinstance(actual, UnionTy):
                expected_non_nil = [member for member in expected.members if member is not NIL]
                actual_non_nil = [member for member in actual.members if member is not NIL]
                if len(expected_non_nil) == 1 and len(actual_non_nil) == 1:
                    return self._unify(
                        expected_non_nil[0],
                        actual_non_nil[0],
                        bindings,
                        token,
                    )
            for member in expected.members:
                trial = dict(bindings)
                if self._unify(member, actual, trial, token):
                    bindings.clear()
                    bindings.update(trial)
                    return True
            return False

        return False

    def _unbound_type_vars(self, ty: Ty, variables: tuple[TyVar, ...]) -> list[TyVar]:
        if isinstance(ty, TyVar):
            return [ty] if ty in variables else []
        if isinstance(ty, ClassTy):
            class_vars: list[TyVar] = []
            for arg in ty.args:
                class_vars.extend(self._unbound_type_vars(arg, variables))
            return class_vars
        if isinstance(ty, EnumTy):
            enum_vars: list[TyVar] = []
            for arg in ty.args:
                enum_vars.extend(self._unbound_type_vars(arg, variables))
            return enum_vars
        if isinstance(ty, ListTy):
            return self._unbound_type_vars(ty.element, variables)
        if isinstance(ty, MapTy):
            return self._unbound_type_vars(ty.key, variables) + self._unbound_type_vars(
                ty.value, variables
            )
        if isinstance(ty, TupleTy):
            tuple_vars: list[TyVar] = []
            for item in ty.items:
                tuple_vars.extend(self._unbound_type_vars(item, variables))
            return tuple_vars
        if isinstance(ty, FnTy):
            found: list[TyVar] = []
            for param in ty.params:
                found.extend(self._unbound_type_vars(param, variables))
            found.extend(self._unbound_type_vars(ty.ret, variables))
            return found
        if isinstance(ty, UnionTy):
            found = []
            for member in ty.members:
                found.extend(self._unbound_type_vars(member, variables))
            return found

        return []

    def _contains_any_type_var(self, ty: Ty, variables: tuple[TyVar, ...]) -> bool:
        if isinstance(ty, TyVar):
            return ty in variables
        if isinstance(ty, ClassTy):
            return any(self._contains_any_type_var(arg, variables) for arg in ty.args)
        if isinstance(ty, EnumTy):
            return any(self._contains_any_type_var(arg, variables) for arg in ty.args)
        if isinstance(ty, ListTy):
            return self._contains_any_type_var(ty.element, variables)
        if isinstance(ty, MapTy):
            return self._contains_any_type_var(ty.key, variables) or self._contains_any_type_var(
                ty.value, variables
            )
        if isinstance(ty, TupleTy):
            return any(self._contains_any_type_var(item, variables) for item in ty.items)
        if isinstance(ty, FnTy):
            return any(
                self._contains_any_type_var(param, variables) for param in ty.params
            ) or self._contains_any_type_var(ty.ret, variables)
        if isinstance(ty, UnionTy):
            return any(self._contains_any_type_var(member, variables) for member in ty.members)

        return False

    def _check_polymorphic_recursion(
        self,
        instance: GenericFnTy,
        bindings: dict[TyVar, Ty],
        token: Token,
    ) -> None:
        if not self._generic_context:
            return

        name, current_params = self._generic_context[-1]
        if instance.name != name:
            return

        for fresh, current in zip(instance.type_params, current_params, strict=False):
            argument = self._substitute(fresh, bindings)
            if argument == current:
                continue
            if self._contains_any_type_var(argument, current_params):
                self._error(
                    token,
                    "Polymorphic recursion is not supported yet; "
                    "the type arguments must stay the same.",
                    code=Code.GENERIC_UNSUPPORTED,
                )
                return

    def visit_get_expr(self, expr: Get) -> Ty:
        key = self._refinement_path(expr)
        narrowed = self._narrowed_at(key) if key is not None else None
        if narrowed is not None:
            self.types[expr] = narrowed
            return narrowed

        obj = self._infer(expr.object)
        return self._get_property_type(obj, expr.name, expr.optional)

    def _get_property_type(self, obj: Ty, name: Token, optional: bool) -> Ty:
        if obj is ANY:
            return ANY
        if isinstance(obj, TyVar):
            found: list[FnTy] = []
            for bound in obj.bounds:
                interface_info = self._interfaces.get(bound)
                if interface_info is None:
                    continue
                signature = interface_info.methods.get(name.lexeme)
                if signature is not None:
                    found.append(signature)
            if not found:
                self._error(
                    name,
                    f"Type parameter '{obj.name}' has no method "
                    f"'{name.lexeme}'; add an interface bound.",
                    code=Code.UNDEFINED_NAME,
                )
                return ERROR
            if any(signature != found[0] for signature in found):
                self._error(
                    name,
                    f"Method '{name.lexeme}' is ambiguous between interface "
                    f"bounds of '{obj.name}'.",
                    code=Code.INVALID_OVERRIDE,
                )
                return ERROR
            return found[0]
        if isinstance(obj, EnumObjectTy):
            info = self._enums.get(obj.name)
            if info is None:
                self._error(name, f"Unknown enum '{obj.name}'.", code=Code.UNKNOWN_TYPE)
                return ERROR
            variant = info.variants.get(name.lexeme)
            if variant is None:
                self._error(name, f"Unknown variant '{name.lexeme}'.", code=Code.UNDEFINED_NAME)
                return ERROR
            if info.type_params:
                if not variant.payload:
                    self._error(
                        name,
                        "Nullary variants of generic enums aren't supported yet; add a payload.",
                        code=Code.GENERIC_UNSUPPORTED,
                    )
                    return ERROR
                return GenericFnTy(
                    f"{obj.name}.{name.lexeme}",
                    info.type_params,
                    FnTy(
                        variant.payload,
                        EnumTy(obj.name, info.type_params),
                        len(variant.payload),
                    ),
                )
            if not variant.payload:
                return EnumTy(obj.name)
            return FnTy(
                variant.payload,
                EnumTy(obj.name),
                len(variant.payload),
            )

        if isinstance(obj, NativeModuleTy):
            member = self._native_modules.get(obj.name, {}).get(name.lexeme)
            if member is None:
                self._error(
                    name,
                    f"Undefined property '{name.lexeme}'.",
                    code=Code.UNDEFINED_NAME,
                )
                return ERROR
            return member

        nilable = obj is NIL or (
            isinstance(obj, UnionTy) and any(member is NIL for member in obj.members)
        )
        if nilable and not optional:
            self._error(name, "Only instances have properties.", code=Code.TYPE_MISMATCH)
            return ERROR
        if obj is NIL:
            return NIL

        members = list(obj.members) if isinstance(obj, UnionTy) else [obj]
        if optional:
            members = [member for member in members if member is not NIL]
        if not members:
            return NIL

        result: Ty
        if all(isinstance(member, ListTy) for member in members):
            lists = [member for member in members if isinstance(member, ListTy)]
            result = self._list_property(lists, name)
        elif all(isinstance(member, MapTy) for member in members):
            maps = [member for member in members if isinstance(member, MapTy)]
            result = self._map_property(maps, name)
        elif all(member is BYTES for member in members):
            result = self._bytes_property(name)
        elif all(isinstance(member, ClassTy) for member in members):
            classes = [member for member in members if isinstance(member, ClassTy)]
            if len(classes) == 1:
                result = self._instance_property(classes[0], name)
            else:
                results = [
                    self._instance_property(member, name, report=False) for member in classes
                ]
                if any(item != results[0] for item in results):
                    self._error(name, "Only instances have properties.", code=Code.TYPE_MISMATCH)
                    return ERROR
                result = results[0]
        elif all(isinstance(member, InterfaceTy) for member in members):
            interfaces = [member for member in members if isinstance(member, InterfaceTy)]
            if len(interfaces) == 1:
                result = self._interface_property(interfaces[0], name)
            else:
                results = [
                    self._interface_property(member, name, report=False) for member in interfaces
                ]
                if any(item != results[0] for item in results):
                    self._error(name, "Only instances have properties.", code=Code.TYPE_MISMATCH)
                    return ERROR
                result = results[0]
        else:
            self._error(name, "Only instances have properties.", code=Code.TYPE_MISMATCH)
            return ERROR

        return union(result, NIL) if optional and nilable else result

    def _bytes_property(self, name: Token) -> Ty:
        signature = BYTES_METHODS.get(name.lexeme)
        if signature is None:
            self._error(name, f"Undefined property '{name.lexeme}'.", code=Code.UNDEFINED_NAME)
            return ERROR
        return signature

    def _list_property(self, lists: list[ListTy], name: Token) -> Ty:
        element = lists[0].element
        if any(item.element != element for item in lists[1:]):
            self._error(
                name,
                "List method requires a single element type.",
                code=Code.INVALID_LIST,
            )
            return ERROR

        if name.lexeme == "push":
            return FnTy((element,), NIL, 1)
        if name.lexeme == "pop":
            return FnTy((), element, 0)

        self._error(name, f"Undefined property '{name.lexeme}'.", code=Code.UNDEFINED_NAME)
        return ERROR

    def _map_property(self, maps: list[MapTy], name: Token) -> Ty:
        key = maps[0].key
        value = maps[0].value
        if any(item.key != key or item.value != value for item in maps[1:]):
            self._error(
                name,
                "Map method requires a single key/value type.",
                code=Code.INVALID_MAP,
            )
            return ERROR

        if name.lexeme == "get":
            return FnTy((key,), union(value, NIL), 1)
        if name.lexeme == "has":
            return FnTy((key,), BOOL, 1)
        if name.lexeme == "remove":
            return FnTy((key,), value, 1)
        if name.lexeme == "keys":
            return FnTy((), ListTy(key), 0)
        if name.lexeme == "values":
            return FnTy((), ListTy(value), 0)

        self._error(name, f"Undefined property '{name.lexeme}'.", code=Code.UNDEFINED_NAME)
        return ERROR

    def _class_bindings(self, obj: ClassTy) -> dict[TyVar, Ty]:
        info = self._classes.get(obj.name)
        if info is None or not info.type_params:
            return {}
        if len(info.type_params) != len(obj.args):
            return {}
        return {
            param: arg
            for param, arg in zip(info.type_params, obj.args, strict=True)
            if param != arg
        }

    def _instance_property(self, obj: ClassTy, name: Token, *, report: bool = True) -> Ty:
        bindings = self._class_bindings(obj)
        field_info = self._find_field(obj.name, name.lexeme)
        if field_info is not None:
            return self._substitute(field_info.ty, bindings)

        method = self._find_method(obj.name, name.lexeme)
        if method is not None:
            return self._substitute(method, bindings)

        if report:
            self._error(name, f"Undefined property '{name.lexeme}'.", code=Code.UNDEFINED_NAME)

        return ERROR

    def _interface_property(self, obj: InterfaceTy, name: Token, *, report: bool = True) -> Ty:
        info = self._interfaces.get(obj.name)
        if info is not None:
            method = info.methods.get(name.lexeme)
            if method is not None:
                return method

        if report:
            self._error(
                name,
                f"Interface '{obj.name}' has no method '{name.lexeme}'.",
                code=Code.UNDEFINED_NAME,
            )

        return ERROR

    def visit_grouping_expr(self, expr: Grouping) -> Ty:
        return self._infer(expr.expression)

    def visit_literal_expr(self, expr: Literal) -> Ty:
        value = expr.value
        if value is None:
            return NIL
        if isinstance(value, bool):
            return BOOL
        if isinstance(value, int):
            return INT
        if isinstance(value, float):
            return FLOAT
        if isinstance(value, str):
            return STRING

        return ANY

    def visit_list_expr(self, expr: ListLiteral) -> Ty:
        if not expr.elements:
            self._error(
                expr.bracket,
                "Can't infer the element type of an empty list; annotate it as List[T].",
                code=Code.INVALID_LIST,
            )
            return ListTy(ERROR)

        element = self._infer(expr.elements[0])
        for item in expr.elements[1:]:
            element = self._join_element(element, self._infer(item), expr.bracket)

        return ListTy(element)

    def _join_element(self, left: Ty, right: Ty, token: Token) -> Ty:
        if left is ERROR or right is ERROR:
            return ERROR
        if left == right:
            return left
        if left is ANY or right is ANY:
            return ANY
        if (left is INT and right is FLOAT) or (left is FLOAT and right is INT):
            return FLOAT
        if isinstance(left, UnionTy) or isinstance(right, UnionTy):
            self._error(
                token,
                "List elements must have a common type; annotate the list as "
                "List[A | B] to allow mixed elements.",
                code=Code.INVALID_LIST,
            )
            return ERROR
        if self._assignable(left, right):
            return left
        if self._assignable(right, left):
            return right

        self._error(
            token,
            "List elements must have a common type; found "
            f"{display(left)} and {display(right)}. Annotate as "
            f"List[{display(left)} | {display(right)}] to allow mixed elements.",
            code=Code.INVALID_LIST,
        )
        return ERROR

    def visit_interpolated_expr(self, expr: InterpolatedString) -> Ty:
        for part in expr.parts:
            if not isinstance(part, str):
                self._infer(part)

        return STRING

    def visit_map_expr(self, expr: MapLiteral) -> Ty:
        if not expr.entries:
            self._error(
                expr.brace,
                "Can't infer the key and value types of an empty map; annotate it as Map[K, V].",
                code=Code.INVALID_MAP,
            )
            return MapTy(ERROR, ERROR)

        key_ty = self._infer(expr.entries[0][0])
        value_ty = self._infer(expr.entries[0][1])
        for key, value in expr.entries[1:]:
            key_ty = self._join_map_key(key_ty, self._infer(key), expr.brace)
            value_ty = self._join_map_value(value_ty, self._infer(value), expr.brace)

        if not self._valid_map_key(key_ty):
            self._error(expr.brace, "Map keys must be String, Int or Bool.", code=Code.INVALID_MAP)
            key_ty = ERROR

        return MapTy(key_ty, value_ty)

    def _join_map_key(self, left: Ty, right: Ty, token: Token) -> Ty:
        if left is ERROR or right is ERROR:
            return ERROR
        if left == right:
            return left
        if left is ANY or right is ANY:
            return ANY
        if isinstance(left, UnionTy) or isinstance(right, UnionTy):
            self._error(
                token,
                "Map keys must have a common type; annotate the map as "
                "Map[K, V] to allow mixed keys.",
                code=Code.INVALID_MAP,
            )
            return ERROR
        if self._assignable(left, right):
            return left
        if self._assignable(right, left):
            return right

        self._error(
            token,
            "Map keys must have a common type; found "
            f"{display(left)} and {display(right)}. Annotate as "
            f"Map[{display(left)} | {display(right)}, V] to allow mixed keys.",
            code=Code.INVALID_MAP,
        )
        return ERROR

    def _join_map_value(self, left: Ty, right: Ty, token: Token) -> Ty:
        if left is ERROR or right is ERROR:
            return ERROR
        if left == right:
            return left
        if left is ANY or right is ANY:
            return ANY
        if (left is INT and right is FLOAT) or (left is FLOAT and right is INT):
            return FLOAT
        if isinstance(left, UnionTy) or isinstance(right, UnionTy):
            self._error(
                token,
                "Map values must have a common type; annotate the map as "
                "Map[K, V] to allow mixed values.",
                code=Code.INVALID_MAP,
            )
            return ERROR
        if self._assignable(left, right):
            return left
        if self._assignable(right, left):
            return right

        self._error(
            token,
            "Map values must have a common type; found "
            f"{display(left)} and {display(right)}. Annotate as "
            f"Map[K, {display(left)} | {display(right)}] to allow mixed values.",
            code=Code.INVALID_MAP,
        )
        return ERROR

    def _tuple_index(self, tuple_ty: TupleTy, index: Ty, expr: Index) -> Ty:
        if index not in (INT, ANY, ERROR):
            self._error(
                expr.bracket,
                f"Tuple index must be an integer, found {display(index)}.",
                code=Code.INVALID_LIST,
            )
            return ERROR

        literal = self._literal_int(expr.index)
        if literal is None:
            return union(*tuple_ty.items)
        if not 0 <= literal < len(tuple_ty.items):
            self._error(
                expr.bracket,
                f"Tuple index {literal} out of bounds for length {len(tuple_ty.items)}.",
                code=Code.INVALID_LIST,
            )
            return ERROR

        return tuple_ty.items[literal]

    def _literal_int(self, expr: Expr) -> int | None:
        if isinstance(expr, Grouping):
            return self._literal_int(expr.expression)
        if isinstance(expr, Literal) and type(expr.value) is int:
            return expr.value

        return None

    def visit_match_expr(self, expr: Match) -> Ty:
        scrutinee = self._infer(expr.scrutinee)
        if scrutinee is ERROR:
            return ERROR
        if not isinstance(scrutinee, EnumTy):
            self._error(
                expr.keyword,
                "match requires an enum value; narrow it first.",
                code=Code.TYPE_MISMATCH,
            )
            return ERROR

        info = self._enums.get(scrutinee.name)
        if info is None:
            self._error(expr.keyword, f"Unknown enum '{scrutinee.name}'.", code=Code.UNKNOWN_TYPE)
            return ERROR

        bindings: dict[TyVar, Ty] = {}
        if scrutinee.args:
            bindings = dict(zip(info.type_params, scrutinee.args, strict=True))

        covered: set[str] = set()
        wildcard = False
        arm_types: list[Ty] = []

        for arm in expr.arms:
            pattern = arm.pattern
            if isinstance(pattern, WildcardPattern):
                if wildcard:
                    self._error(
                        pattern.token, "Unreachable match arm.", code=Code.UNREACHABLE_MATCH
                    )
                wildcard = True
                arm_types.append(self._infer(arm.body))
                continue

            assert isinstance(pattern, VariantPattern)
            if wildcard:
                self._error(pattern.variant, "Unreachable match arm.", code=Code.UNREACHABLE_MATCH)
            if pattern.enum.lexeme != scrutinee.name:
                self._error(
                    pattern.enum,
                    f"Pattern '{pattern.enum.lexeme}.{pattern.variant.lexeme}' "
                    f"doesn't match enum '{scrutinee.name}'.",
                    code=Code.TYPE_MISMATCH,
                )
                arm_types.append(self._infer(arm.body))
                continue

            variant = info.variants.get(pattern.variant.lexeme)
            if variant is None:
                self._error(
                    pattern.variant,
                    f"Unknown variant '{pattern.variant.lexeme}'.",
                    code=Code.UNDEFINED_NAME,
                )
                arm_types.append(self._infer(arm.body))
                continue

            if len(variant.payload) != len(pattern.bindings):
                self._error(
                    pattern.variant,
                    f"Variant '{scrutinee.name}.{variant.name}' expects "
                    f"{len(variant.payload)} binding(s), got "
                    f"{len(pattern.bindings)}.",
                    code=Code.ARITY_MISMATCH,
                )
            if variant.name in covered:
                self._error(pattern.variant, "Unreachable match arm.", code=Code.UNREACHABLE_MATCH)
            covered.add(variant.name)

            self._begin_scope()
            seen: set[str] = set()
            for token, item_ty in zip(pattern.bindings, variant.payload, strict=False):
                if token.lexeme in seen:
                    self._error(
                        token,
                        f"Binding '{token.lexeme}' is declared twice in this pattern.",
                        code=Code.INVALID_CHECKER_DECLARATION,
                    )
                seen.add(token.lexeme)
                self._define(token, self._substitute(item_ty, bindings))

            arm_types.append(self._infer(arm.body))
            self._end_scope()

        if not wildcard:
            missing = [f"{scrutinee.name}.{name}" for name in info.variants if name not in covered]
            if missing:
                self._error(
                    expr.keyword,
                    "Non-exhaustive match; missing " + ", ".join(missing) + ".",
                    code=Code.MATCH_EXHAUSTIVENESS,
                )

        return union(*arm_types)

    def visit_tuple_expr(self, expr: TupleLiteral) -> Ty:
        return TupleTy(tuple(self._infer(element) for element in expr.elements))

    def visit_destructure_stmt(self, stmt: Destructure) -> None:
        names = pattern_names(stmt.pattern)
        seen: set[str] = set()
        for name in names:
            if name.lexeme in seen:
                self._error(
                    name,
                    f"Variable '{name.lexeme}' is declared twice in this destructuring.",
                    code=Code.INVALID_CHECKER_DECLARATION,
                )
            seen.add(name.lexeme)

        token = first_token(stmt.pattern)
        if stmt.type_annotation is not None:
            declared = self._resolve_type(stmt.type_annotation, token)
            self._check(stmt.initializer, declared, token)
            ty = declared
        else:
            ty = self._infer(stmt.initializer)

        self._bind_pattern(stmt.pattern, ty)

    def _bind_pattern(self, pattern: DestructurePattern, ty: Ty) -> None:
        if isinstance(pattern, NamePattern):
            self._define(pattern.name, ty)
            return

        token = first_token(pattern)
        items = self._destructure_items(ty, token)
        if items is None or len(items) != len(pattern.elements):
            if items is not None:
                self._error(
                    token,
                    f"Destructuring expects {len(pattern.elements)} values, found {len(items)}.",
                    code=Code.ARITY_MISMATCH,
                )
            for name in pattern_names(pattern):
                self._define(name, ERROR)
            return

        for element, item in zip(pattern.elements, items, strict=True):
            self._bind_pattern(element, item)

    def _destructure_items(self, ty: Ty, token: Token) -> tuple[Ty, ...] | None:
        if ty is ANY:
            self._error(
                token,
                "Can't destructure Any; add a tuple annotation.",
                code=Code.MISSING_ANNOTATION,
            )
            return None
        if isinstance(ty, TupleTy):
            return ty.items
        if isinstance(ty, UnionTy) and all(isinstance(member, TupleTy) for member in ty.members):
            members = [member for member in ty.members if isinstance(member, TupleTy)]
            arity = len(members[0].items)
            if any(len(member.items) != arity for member in members):
                self._error(
                    token,
                    "Tuple members of the union have different arity.",
                    code=Code.TYPE_MISMATCH,
                )
                return None
            return tuple(
                union(*(member.items[position] for member in members)) for position in range(arity)
            )

        self._error(
            token, f"Can only destructure tuples, found {display(ty)}.", code=Code.TYPE_MISMATCH
        )
        return None

    def visit_index_expr(self, expr: Index) -> Ty:
        key = self._refinement_path(expr)
        narrowed = self._narrowed_at(key) if key is not None else None
        if narrowed is not None:
            self.types[expr] = narrowed
            return narrowed

        obj = self._infer(expr.object)
        if isinstance(obj, GenericFnTy):
            self._error(
                expr.bracket,
                "Type arguments on a call aren't supported; let the checker infer them.",
                code=Code.TYPE_ARGUMENTS,
            )
            return ERROR

        index = self._infer(expr.index)

        if obj is ANY:
            return ANY
        if obj is ERROR:
            return ERROR
        if isinstance(obj, TupleTy):
            return self._tuple_index(obj, index, expr)
        if isinstance(obj, UnionTy) and all(isinstance(member, TupleTy) for member in obj.members):
            return union(
                *(
                    self._tuple_index(member, index, expr)
                    for member in obj.members
                    if isinstance(member, TupleTy)
                )
            )
        if isinstance(obj, MapTy):
            if not self._assignable(obj.key, index):
                self._error(
                    expr.bracket,
                    f"Expected {display(obj.key)}, found {display(index)}.",
                    notes=self._provenance_notes(expr.index, expr.bracket),
                    code=Code.TYPE_MISMATCH,
                )
            return obj.value
        if obj is BYTES:
            self._check_index_type(index, expr, expr.index, owner="Bytes")
            return INT
        if not isinstance(obj, ListTy):
            self._error(expr.bracket, "Only lists and maps can be indexed.", code=Code.INVALID_LIST)
            return ERROR

        self._check_index_type(index, expr, expr.index)
        return obj.element

    def visit_index_set_expr(self, expr: IndexSet) -> Ty:
        result = self._index_set(expr)
        self._invalidate_members()
        return result

    def _index_set(self, expr: IndexSet) -> Ty:
        obj = self._infer(expr.object)
        index = self._infer(expr.index)
        value = self._infer(expr.value)

        if obj is ANY:
            return value
        if obj is ERROR:
            return ERROR
        if isinstance(obj, MapTy):
            if not self._assignable(obj.key, index):
                self._error(
                    expr.bracket,
                    f"Expected {display(obj.key)}, found {display(index)}.",
                    notes=self._provenance_notes(expr.index, expr.bracket),
                    code=Code.TYPE_MISMATCH,
                )
            if not self._assignable(obj.value, value):
                self._error(
                    expr.bracket,
                    f"Expected {display(obj.value)}, found {display(value)}.",
                    notes=self._provenance_notes(expr.value, expr.bracket),
                    code=Code.TYPE_MISMATCH,
                )
            return value
        if not isinstance(obj, ListTy):
            self._error(expr.bracket, "Only lists and maps can be indexed.", code=Code.INVALID_LIST)
            return value

        self._check_index_type(index, expr, expr.index)
        if not self._assignable(obj.element, value):
            self._error(
                expr.bracket,
                f"Expected {display(obj.element)}, found {display(value)}.",
                notes=self._provenance_notes(expr.value, expr.bracket),
                code=Code.TYPE_MISMATCH,
            )

        return value

    def _check_index_type(
        self,
        index: Ty,
        expr: Index | IndexSet,
        index_expr: Expr | None = None,
        *,
        owner: str = "List",
    ) -> None:
        if index is INT or index is ERROR:
            return

        notes = self._provenance_notes(index_expr, expr.bracket) if index_expr is not None else ()
        self._error(
            expr.bracket,
            f"{owner} index must be an integer, found {display(index)}.",
            code=Code.INVALID_LIST,
            notes=notes,
        )

    def visit_conditional_expr(self, expr: Conditional) -> Ty:
        self._infer(expr.condition)
        then_ty = self._infer(expr.then_branch)
        else_ty = self._infer(expr.else_branch)
        return union(then_ty, else_ty)

    def visit_logical_expr(self, expr: Logical) -> Ty:
        left = self._infer(expr.left)

        if (
            expr.operator.type is TokenType.QUESTION_QUESTION
            and left is not ANY
            and is_nilable(left)
        ):
            expected = non_nil(left)
            if isinstance(expr.right, ListLiteral) and self._expected_element(expected) is not None:
                right = self._check(expr.right, expected, expr.operator)
            else:
                right = self._infer(expr.right)
        else:
            right = self._infer(expr.right)

        if expr.operator.type is TokenType.QUESTION_QUESTION:
            if left is ANY:
                return ANY
            if not is_nilable(left):
                return left
            return union(non_nil(left), right)
        if expr.operator.type is TokenType.OR:
            return union(truthy(left), right)

        return union(falsy(left), right)

    def visit_range_expr(self, expr: Range) -> Ty:
        start = self._infer(expr.start)
        end = self._infer(expr.end)

        for bound in (start, end):
            if bound is INT:
                continue
            if bound is ANY:
                return RANGE

            self._error(expr.operator, "Range bounds must be integers.", code=Code.INVALID_OPERANDS)
            return ERROR

        return RANGE

    def visit_set_expr(self, expr: Set) -> Ty:
        obj = self._infer(expr.object)

        if obj is ANY:
            return self._infer(expr.value)

        if isinstance(obj, InterfaceTy):
            self._infer(expr.value)
            self._error(
                expr.name, f"Interface '{obj.name}' has no fields.", code=Code.UNDEFINED_NAME
            )
            return ANY

        if not isinstance(obj, ClassTy):
            self._infer(expr.value)
            self._error(expr.name, "Only instances have fields.", code=Code.TYPE_MISMATCH)
            return ANY

        field_info = self._find_field(obj.name, expr.name.lexeme)
        if field_info is None:
            self._infer(expr.value)
            self._error(
                expr.name,
                f"Undefined field '{expr.name.lexeme}'.",
                code=Code.UNDEFINED_NAME,
            )
            return ANY

        value = self._check(
            expr.value,
            self._substitute(field_info.ty, self._class_bindings(obj)),
            expr.name,
        )

        path = self._refinement_path(expr.object)
        if path is not None:
            self._invalidate_path((path[0], path[1], path[2] + (("field", expr.name.lexeme),)))
        self._invalidate_members()

        is_initializer_this = self._in_initializer and isinstance(expr.object, This)
        if not field_info.mutable and not is_initializer_this:
            self._error(
                expr.name,
                f"Can't assign to immutable field '{expr.name.lexeme}'.",
                code=Code.INVALID_CHECKER_DECLARATION,
            )

        return value

    def visit_super_expr(self, expr: Super) -> Ty:
        if self._current_class is None or self._current_class.superclass is None:
            return ERROR

        method = self._find_method(self._current_class.superclass, expr.method.lexeme)
        if method is None:
            self._error(
                expr.method,
                f"Undefined property '{expr.method.lexeme}'.",
                code=Code.UNDEFINED_NAME,
            )
            return ERROR

        return method

    def visit_this_expr(self, expr: This) -> Ty:
        if self._current_interface is not None:
            return InterfaceTy(self._current_interface.name)
        if self._current_class is None:
            return ERROR

        return ClassTy(self._current_class.name, self._current_class.type_params)

    def visit_unary_expr(self, expr: Unary) -> Ty:
        right = self._infer(expr.right)

        if expr.operator.type is TokenType.NOT:
            return BOOL
        if expr.operator.type is TokenType.TILDE:
            if right is ANY:
                return ANY
            if right is INT:
                return INT
            self._error(
                expr.operator,
                "Operand must be an integer.",
                lowerable=True,
                code=Code.INVALID_OPERANDS,
            )
            return ERROR
        if right is ANY:
            return ANY
        if isinstance(right, TyVar):
            if "Num" in right.bounds:
                return right
            if right.bounds:
                self._error(
                    expr.operator,
                    f"Type parameter '{right.name}' needs a 'Num' constraint.",
                    code=Code.INVALID_OPERANDS,
                )
                return ERROR
            self._error(
                expr.operator,
                "Operand must be a number.",
                code=Code.INVALID_OPERANDS,
                lowerable=True,
            )
            return ERROR
        if right is INT or right is FLOAT:
            return right

        self._error(
            expr.operator, "Operand must be a number.", lowerable=True, code=Code.INVALID_OPERANDS
        )
        return ERROR

    def visit_error_expr(self, expr: ErrorExpr) -> Ty:
        return ERROR

    def visit_variable_expr(self, expr: Variable) -> Ty:
        if expr.name.lexeme in self._interfaces:
            self._error(
                expr.name,
                f"Interface '{expr.name.lexeme}' is a type, not a value.",
                code=Code.UNDEFINED_NAME,
            )
            return ERROR
        return self._lookup(expr.name)
