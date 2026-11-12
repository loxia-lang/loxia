"""Type checker estático (gradual) — roda depois do resolver, antes de executar.

Anotações são opcionais no runtime; em `--check` as funções precisam de parâmetros e
retorno anotados. Tipos são apagados: o interpretador continua dinâmico.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.diagnostics.error_reporter import ErrorReporter
from src.execution.prelude import BUILTIN_NAMES
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
    Range,
    Set,
    Super,
    This,
    Unary,
    Variable,
)
from src.frontend.expr import Visitor as ExprVisitor
from src.frontend.stmt import (
    Block,
    Class,
    Expression,
    ForIn,
    Function,
    If,
    Print,
    Return,
    Stmt,
    Var,
    While,
)
from src.frontend.stmt import Visitor as StmtVisitor
from src.frontend.token_type import TokenType
from src.frontend.tokens import Token
from src.frontend.ty import (
    ANY,
    BOOL,
    ERROR,
    FLOAT,
    INT,
    NEVER,
    NIL,
    RANGE,
    STRING,
    ClassObjectTy,
    ClassTy,
    FnTy,
    GenericFnTy,
    ListTy,
    MapTy,
    NativeFnTy,
    NativeModuleTy,
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
    {"Any", "Bool", "Float", "Int", "List", "Map", "Never", "Nil", "Range", "String"}
)


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


@dataclass(frozen=True)
class FunctionSignature:
    type_params: tuple[TyVar, ...]
    type_param_names: tuple[str, ...]
    fn: FnTy


class Checker(ExprVisitor[Ty], StmtVisitor[None]):
    def __init__(self, reporter: ErrorReporter) -> None:
        self._reporter = reporter
        self._scopes: list[dict[str, Ty]] = [{}]
        self._narrowings: list[dict[str, tuple[int, Ty]]] = [{}]
        self._classes: dict[str, ClassInfo] = {}
        self._current_class: ClassInfo | None = None
        self._current_return: Ty | None = None
        self._in_initializer = False
        self._signatures: dict[Function, FunctionSignature] = {}
        self._predeclared_by_name: dict[str, FunctionSignature] = {}
        self._type_param_scopes: list[dict[str, TyVar]] = []
        self._next_type_var_id = 0
        self._generic_context: list[tuple[str, tuple[TyVar, ...]]] = []
        self._native_modules: dict[str, dict[str, Ty]] = {}
        self._function_depth = 0
        self._return_collector: list[Ty] | None = None
        self._define_builtins()

    def check(self, statements: list[Stmt]) -> None:
        self._predeclare_classes(statements)
        self._predeclare_functions(statements)
        for statement in statements:
            self._check_stmt(statement)

        self._check_overrides()

    # --- infraestrutura ---

    def _define_builtins(self) -> None:
        self._scopes[0]["len"] = NativeFnTy("len")
        self._scopes[0]["range"] = FnTy((INT, INT, INT), RANGE, 3)
        self._scopes[0]["repr"] = NativeFnTy("repr")
        self._scopes[0]["str"] = NativeFnTy("str")

        self._native_modules = {
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
        for name in self._native_modules:
            self._scopes[0][name] = NativeModuleTy(name)

    def _function_value_type(self, name: str, signature: FunctionSignature) -> Ty:
        if signature.type_params:
            return GenericFnTy(name, signature.type_params, signature.fn)
        return signature.fn

    def _fresh_type_var(self, name: str) -> TyVar:
        self._next_type_var_id += 1
        return TyVar(name, self._next_type_var_id)

    def _push_type_params(
        self, names: tuple[str, ...], variables: tuple[TyVar, ...]
    ) -> None:
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
                statement.superclass.name.lexeme
                if statement.superclass is not None
                else None
            )
            self._classes.setdefault(
                statement.name.lexeme, ClassInfo(statement.name.lexeme, superclass)
            )
            self._scopes[0].setdefault(
                statement.name.lexeme, ClassObjectTy(statement.name.lexeme)
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
        self._narrowings.append({})

    def _end_scope(self) -> None:
        self._scopes.pop()
        self._narrowings.pop()

    def _define(self, name: Token, ty: Ty) -> None:
        if len(self._scopes) == 1 and name.lexeme in BUILTIN_NAMES:
            self._error(name, f"Can't redefine builtin '{name.lexeme}'.")

        self._scopes[-1][name.lexeme] = ty
        self._narrowings[-1].pop(name.lexeme, None)

    def _find_decl(self, name: str) -> tuple[int, Ty] | None:
        for index in range(len(self._scopes) - 1, -1, -1):
            ty = self._scopes[index].get(name)
            if ty is not None:
                return index, ty

        return None

    def _lookup(self, name: Token) -> Ty:
        found = self._find_decl(name.lexeme)
        if found is None:
            predeclared = self._predeclared_by_name.get(name.lexeme)
            if predeclared is not None and self._function_depth > 0:
                return self._function_value_type(name.lexeme, predeclared)

            self._error(name, f"Undefined variable '{name.lexeme}'.")
            return ERROR

        index, declared = found
        for narrowing in reversed(self._narrowings):
            entry = narrowing.get(name.lexeme)
            if entry is not None and entry[0] == index:
                return entry[1]

        return declared

    def _lookup_declared(self, name: Token) -> Ty:
        found = self._find_decl(name.lexeme)
        if found is None:
            self._error(name, f"Undefined variable '{name.lexeme}'.")
            return ERROR

        return found[1]

    def _invalidate(self, name: str) -> None:
        for narrowing in self._narrowings:
            narrowing.pop(name, None)

    def _apply_refinements(self, refinements: dict[str, Ty]) -> None:
        for name, ty in refinements.items():
            found = self._find_decl(name)
            if found is not None:
                self._narrowings[-1][name] = (found[0], ty)

    def _error(self, token: Token, message: str, *, lowerable: bool = False) -> None:
        """Reporta erro de tipo.

        `lowerable=True` para os erros que o interpretador também levantaria em runtime
        (operandos de tipo errado): o backend os rebaixa a panic site (ADR-0031).
        """
        self._reporter.error(token, message, lowerable=lowerable)

    def _mismatch_message(self, expected: Ty, actual: Ty) -> str:
        if (
            isinstance(expected, ClassTy)
            and isinstance(actual, ClassObjectTy)
            and expected.name == actual.name
        ):
            return (
                f"Expected an instance of {expected.name}, "
                f"found the class {actual.name}."
            )
        if isinstance(expected, FnTy) and isinstance(actual, ClassObjectTy):
            return (
                f"Expected a function {display(expected)}, "
                f"found the class {actual.name}."
            )

        return f"Expected {display(expected)}, found {display(actual)}."

    def _check_stmt(self, stmt: Stmt) -> None:
        stmt.accept(self)

    def _infer(self, expr: Expr) -> Ty:
        return expr.accept(self)

    def _check(
        self, expr: Expr, expected: Ty, token: Token
    ) -> Ty:
        if isinstance(expr, Call):
            actual = self._infer_call(expr, expected, token)
            if actual is ERROR:
                return ERROR
            if not self._assignable(expected, actual):
                self._error(token, self._mismatch_message(expected, actual))
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

        if isinstance(expr, Lambda):
            actual = self._lambda_type(expr, self._expected_fn(expected))
            if not self._assignable(expected, actual):
                self._error(token, self._mismatch_message(expected, actual))
                return ERROR

            return actual

        actual = self._infer(expr)
        if isinstance(actual, GenericFnTy):
            self._error(
                token,
                f"Generic function '{actual.name}' can't be used as a value yet; "
                "call it so its type arguments can be inferred.",
            )
            return ERROR
        if not self._assignable(expected, actual):
            self._error(token, self._mismatch_message(expected, actual))

        return actual

    def _expected_element(self, expected: Ty) -> Ty | None:
        if expected is ANY:
            return ANY
        if isinstance(expected, ListTy):
            return expected.element

        if isinstance(expected, UnionTy):
            lists = [
                member for member in expected.members if isinstance(member, ListTy)
            ]
            if len(lists) == 1:
                return lists[0].element

        return None

    def _expected_map(self, expected: Ty) -> tuple[Ty, Ty] | None:
        if expected is ANY:
            return (ANY, ANY)
        if isinstance(expected, MapTy):
            return (expected.key, expected.value)

        if isinstance(expected, UnionTy):
            maps = [
                member for member in expected.members if isinstance(member, MapTy)
            ]
            if len(maps) == 1:
                return (maps[0].key, maps[0].value)

        return None

    def _expected_fn(self, expected: Ty) -> FnTy | None:
        if isinstance(expected, FnTy):
            return expected
        if isinstance(expected, UnionTy):
            functions = [
                member for member in expected.members if isinstance(member, FnTy)
            ]
            if len(functions) == 1:
                return functions[0]

        return None

    def _assignable(self, expected: Ty, actual: Ty) -> bool:
        if expected is ANY or actual is ANY or expected is ERROR or actual is ERROR:
            return True
        if actual is NEVER:
            return True
        if expected == actual:
            return True
        if isinstance(actual, UnionTy):
            return all(self._assignable(expected, member) for member in actual.members)
        if isinstance(expected, UnionTy):
            return any(self._assignable(member, actual) for member in expected.members)
        if isinstance(expected, TyVar) or isinstance(actual, TyVar):
            return False
        if actual is INT and expected is FLOAT:
            return True
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
        if isinstance(expected, FnTy):
            if isinstance(actual, FnTy):
                return self._assignable_fn(expected, actual)
            if isinstance(actual, ClassObjectTy):
                info = self._classes.get(actual.name)
                if info is None:
                    return False
                signature = info.init or FnTy((), ClassTy(actual.name), 0)
                return self._assignable_fn(expected, signature)
            if isinstance(actual, NativeFnTy):
                native_signature = self._native_signature(actual.name)
                return native_signature is not None and self._assignable_fn(
                    expected, native_signature
                )
        if isinstance(expected, ClassTy) and isinstance(actual, ClassTy):
            return self._is_subclass(actual.name, expected.name)

        return False

    def _assignable_fn(self, expected: FnTy, actual: FnTy) -> bool:
        """Função é contravariante nos parâmetros e covariante no retorno."""
        count = len(expected.params)
        if not actual.min_params <= count <= len(actual.params):
            return False

        for expected_param, actual_param in zip(
            expected.params, actual.params, strict=False
        ):
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

    def _resolve_type(self, ty: Ty, token: Token) -> Ty:
        if isinstance(ty, ClassTy):
            parameter = self._lookup_type_param(ty.name)
            if parameter is not None:
                return parameter
            if ty.name not in self._classes:
                self._error(token, f"Unknown type '{ty.name}'.")
                return ERROR
            return ty
        if isinstance(ty, ListTy):
            return ListTy(self._resolve_type(ty.element, token))
        if isinstance(ty, MapTy):
            key = self._resolve_type(ty.key, token)
            value = self._resolve_type(ty.value, token)
            if not self._valid_map_key(key):
                self._error(token, "Map keys must be String, Int or Bool.")
                key = ERROR
            return MapTy(key, value)
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self._resolve_type(param, token) for param in ty.params),
                self._resolve_type(ty.ret, token),
                ty.min_params,
            )
        if isinstance(ty, UnionTy):
            return union(
                *(self._resolve_type(member, token) for member in ty.members)
            )

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

        return None

    def _numeric(self, ty: Ty, token: Token) -> Ty:
        if ty is ANY:
            return ANY
        if ty is INT or ty is FLOAT:
            return ty

        self._error(token, "Operands must be numbers.", lowerable=True)
        return ERROR

    def _promote(self, left: Ty, right: Ty) -> Ty:
        if left is ANY or right is ANY:
            return ANY
        if left is FLOAT or right is FLOAT:
            return FLOAT

        return INT

    # --- statements ---

    def visit_block_stmt(self, stmt: Block) -> None:
        self._begin_scope()
        for statement in stmt.statements:
            self._check_stmt(statement)
        self._end_scope()

    def visit_class_stmt(self, stmt: Class) -> None:
        name = stmt.name.lexeme
        if name in BUILTIN_NAMES:
            self._error(stmt.name, f"Can't redefine builtin '{name}'.")

        superclass_token = (
            stmt.superclass.name if stmt.superclass is not None else None
        )
        superclass = superclass_token.lexeme if superclass_token is not None else None

        if superclass_token is not None and superclass not in self._classes:
            self._error(superclass_token, f"Unknown superclass '{superclass}'.")

        info = self._classes.get(name)
        if info is None:
            info = ClassInfo(name, superclass)
            self._classes[name] = info
            self._define(stmt.name, ClassObjectTy(name))

        info.superclass = superclass
        enclosing = self._current_class
        self._current_class = info

        for field_decl in stmt.fields:
            if field_decl.type_annotation is not None:
                field_ty = self._resolve_type(
                    field_decl.type_annotation, field_decl.name
                )
            elif field_decl.initializer is not None:
                field_ty = self._infer(field_decl.initializer)
                if field_decl.mutable and field_ty is NIL:
                    self._error(
                        field_decl.name,
                        f"Field '{field_decl.name.lexeme}' initialized with nil "
                        "needs a type annotation.",
                    )
                    field_ty = ANY
            else:
                self._error(
                    field_decl.name,
                    f"Field '{field_decl.name.lexeme}' needs a type annotation.",
                )
                field_ty = ANY

            if field_decl.initializer is not None:
                self._check(field_decl.initializer, field_ty, field_decl.name)

            info.fields[field_decl.name.lexeme] = FieldBinding(
                field_ty, field_decl.mutable, field_decl.name
            )

        for method in stmt.methods:
            is_init = method.name.lexeme == "init"
            signature = self._signature(
                method, is_init=is_init, allow_type_params=False
            ).fn
            if is_init:
                info.init = signature
            else:
                info.methods[method.name.lexeme] = signature
                info.method_tokens[method.name.lexeme] = method.name

        for method in stmt.methods:
            is_init = method.name.lexeme == "init"
            body_signature = (
                info.init if is_init else info.methods.get(method.name.lexeme)
            )
            assert body_signature is not None
            self._check_function_body(method, body_signature, info, is_init=is_init)

        self._check_field_initialization(stmt, info)
        self._current_class = enclosing

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
                    self._error(
                        token,
                        f"Method '{name}' is incompatible with the superclass "
                        f"method: expected {display(superclass_signature)}, "
                        f"found {display(signature)}.",
                    )

    def _check_field_initialization(self, stmt: Class, info: ClassInfo) -> None:
        required = {
            field.name.lexeme: field
            for field in stmt.fields
            if field.initializer is None
        }
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
                    )
            return

        assigned = {
            field.name.lexeme for field in stmt.fields if field.initializer is not None
        }
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
                    field.name, f"Field '{field.name.lexeme}' must be initialized."
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
            then_state = self._init_flow(
                [stmt.then_branch], set(assigned), returns
            )
            if stmt.else_branch is None:
                else_state: set[str] | None = set(assigned)
            else:
                else_state = self._init_flow(
                    [stmt.else_branch], set(assigned), returns
                )

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
        if isinstance(stmt, Print):
            self._mark_field_assignments(stmt.expression, assigned)
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
        element = self._element_type(iterable, stmt.name)

        self._begin_scope()
        self._define(stmt.name, element)
        self._check_stmt(stmt.body)
        self._end_scope()

    def _element_type(self, iterable: Ty, token: Token) -> Ty:
        if iterable is ANY:
            return ANY
        if iterable is RANGE:
            return INT
        if iterable is STRING:
            return STRING
        if isinstance(iterable, ListTy):
            return iterable.element
        if isinstance(iterable, MapTy):
            return iterable.key

        self._error(
            token, "Can only iterate over a range, a list, a map or a string."
        )
        return ERROR

    def visit_function_stmt(self, stmt: Function) -> None:
        signature = self._signatures.get(stmt)
        if signature is None:
            signature = self._signature(stmt, is_init=False)

        self._define(
            stmt.name, self._function_value_type(stmt.name.lexeme, signature)
        )
        self._check_function_body(
            stmt,
            signature.fn,
            None,
            is_init=False,
            type_params=signature.type_params,
            type_param_names=signature.type_param_names,
        )

    def _signature(
        self, stmt: Function, *, is_init: bool, allow_type_params: bool = True
    ) -> FunctionSignature:
        names: list[str] = []
        variables: list[TyVar] = []

        if stmt.type_params and not allow_type_params:
            self._error(
                stmt.type_params[0], "Generic methods aren't supported yet."
            )
        elif stmt.type_params:
            for token in stmt.type_params:
                if token.lexeme in RESERVED_TYPE_PARAM_NAMES:
                    self._error(
                        token,
                        f"Type parameter can't be named '{token.lexeme}'.",
                    )
                    continue
                if token.lexeme in names:
                    self._error(
                        token,
                        f"Type parameter '{token.lexeme}' is already declared.",
                    )
                    continue
                names.append(token.lexeme)
                variables.append(self._fresh_type_var(token.lexeme))

        type_params = tuple(variables)
        type_param_names = tuple(names)
        self._push_type_params(type_param_names, type_params)
        try:
            param_types: list[Ty] = []
            minimum = 0

            for param in stmt.params:
                if param.type_annotation is None:
                    self._error(
                        param.name,
                        f"Parameter '{param.name.lexeme}' needs a type annotation.",
                    )
                    param_ty: Ty = ANY
                else:
                    param_ty = self._resolve_type(param.type_annotation, param.name)

                if param.default is not None:
                    self._check(param.default, param_ty, param.name)
                else:
                    minimum += 1

                param_types.append(param_ty)

            if is_init:
                if stmt.return_type is not None:
                    self._error(
                        stmt.name, "Initializer can't declare a return type."
                    )
                assert self._current_class is not None
                return_ty: Ty = ClassTy(self._current_class.name)
            elif stmt.return_type is None:
                self._error(
                    stmt.name,
                    f"Function '{stmt.name.lexeme}' needs a return type annotation.",
                )
                return_ty = ANY
            else:
                return_ty = self._resolve_type(stmt.return_type, stmt.name)
        finally:
            self._pop_type_params()

        return FunctionSignature(
            type_params, type_param_names, FnTy(tuple(param_types), return_ty, minimum)
        )

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
    ) -> list[Ty]:
        enclosing_class = self._current_class
        enclosing_return = self._current_return
        enclosing_init = self._in_initializer
        enclosing_collector = self._return_collector

        if not preserve_class:
            self._current_class = class_info
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
                self._scopes[-1]["this"] = ClassTy(class_info.name)
                if class_info.superclass is not None:
                    self._scopes[-1]["super"] = ClassObjectTy(
                        class_info.superclass
                    )

            for param, param_ty in zip(stmt.params, signature.params, strict=True):
                self._define(param.name, param_ty)

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
                kind = "Method" if class_info is not None else "Function"
                self._error(
                    stmt.name,
                    f"{kind} '{stmt.name.lexeme}' must return "
                    f"{display(signature.ret)} on all paths.",
                )

            self._end_scope()
        finally:
            self._function_depth -= 1
            self._current_class = enclosing_class
            self._current_return = enclosing_return
            self._in_initializer = enclosing_init
            collected = self._return_collector or []
            self._return_collector = enclosing_collector
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
        if target in (INT, FLOAT):
            if source in (INT, FLOAT):
                return target
        elif isinstance(target, ClassTy):
            if isinstance(source, ClassTy):
                return target
        elif source == target and (
            isinstance(target, (ListTy, MapTy))
            or target in (BOOL, STRING, NIL, RANGE)
        ):
            return target

        self._error(
            expr.operator,
            f"Can't cast {display(source)} to {display(target)}.",
        )
        return ERROR

    def _validate_as_target(self, ty: Ty, token: Token) -> None:
        if ty is ERROR or ty is ANY:
            return
        if ty in (NIL, BOOL, INT, FLOAT, STRING, RANGE):
            return
        if isinstance(ty, ClassTy):
            return
        if isinstance(ty, ListTy):
            self._validate_is_type(ty.element, token)
            return
        if isinstance(ty, MapTy):
            self._validate_is_type(ty.key, token)
            self._validate_is_type(ty.value, token)
            return
        if isinstance(ty, UnionTy):
            self._error(token, "as doesn't support union types yet; narrow first.")
            return

        self._error(token, "as doesn't support this type yet.")

    def _validate_is_type(self, ty: Ty, token: Token) -> None:
        if ty is ERROR or ty is ANY or ty is NEVER:
            return
        if ty in (NIL, BOOL, INT, FLOAT, STRING, RANGE):
            return
        if isinstance(ty, ClassTy):
            return
        if isinstance(ty, ListTy):
            self._validate_is_type(ty.element, token)
            return
        if isinstance(ty, MapTy):
            self._validate_is_type(ty.key, token)
            self._validate_is_type(ty.value, token)
            return
        if isinstance(ty, UnionTy):
            for member in ty.members:
                self._validate_is_type(member, token)
            return

        self._error(token, "is doesn't support this type yet.")

    def _lambda_type(self, expr: Lambda, expected: FnTy | None) -> Ty:
        param_types: list[Ty] = []

        for index, param in enumerate(expr.params):
            if param.type_annotation is not None:
                param_ty = self._resolve_type(param.type_annotation, param.name)
            elif expected is not None and index < len(expected.params):
                param_ty = expected.params[index]
            else:
                self._error(
                    param.name,
                    f"Parameter '{param.name.lexeme}' needs a type annotation; "
                    "use the lambda where a function type is expected.",
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

        minimum = sum(1 for param in expr.params if param.default is None)
        signature = FnTy(
            tuple(param_types),
            declared_return if declared_return is not None else ANY,
            minimum,
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
                )
            return_ty = declared_return
        else:
            return_ty = self._infer_lambda_return(expr, returns, all_paths_return)

        return FnTy(tuple(param_types), return_ty, minimum)

    def _infer_lambda_return(
        self, expr: Lambda, returns: list[Ty], all_paths_return: bool
    ) -> Ty:
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
                )
                return ANY

        return inferred

    def visit_if_stmt(self, stmt: If) -> None:
        self._infer(stmt.condition)
        then_refinements = self._refinements(stmt.condition, True)
        else_refinements = self._refinements(stmt.condition, False)

        then_returns = self._check_branch(stmt.then_branch, then_refinements)
        else_returns = False
        if stmt.else_branch is not None:
            else_returns = self._check_branch(stmt.else_branch, else_refinements)

        # `if (x == nil) { return }` refina o resto do bloco com o ramo oposto.
        if then_returns and not else_returns:
            self._apply_refinements(else_refinements)
        elif else_returns and not then_returns:
            self._apply_refinements(then_refinements)

    def _check_branch(self, stmt: Stmt, refinements: dict[str, Ty]) -> bool:
        self._narrowings.append({})
        try:
            self._apply_refinements(refinements)
            self._check_stmt(stmt)
            return self._always_returns(stmt)
        finally:
            self._narrowings.pop()

    def _refinements(self, expr: Expr, truth: bool) -> dict[str, Ty]:
        if isinstance(expr, Grouping):
            return self._refinements(expr.expression, truth)

        if isinstance(expr, Unary) and expr.operator.type is TokenType.BANG:
            return self._refinements(expr.right, not truth)

        if isinstance(expr, Binary) and expr.operator.type in (
            TokenType.EQUAL_EQUAL,
            TokenType.BANG_EQUAL,
        ):
            left, right = expr.left, expr.right
            equal = expr.operator.type is TokenType.EQUAL_EQUAL
            variable = self._as_variable(left)
            if self._is_nil_literal(right) and variable is not None:
                return self._nil_refinement(variable.name.lexeme, truth, equal=equal)

            variable = self._as_variable(right)
            if self._is_nil_literal(left) and variable is not None:
                return self._nil_refinement(variable.name.lexeme, truth, equal=equal)

        if isinstance(expr, Is):
            variable = self._as_variable(expr.left)
            if variable is None or self._find_decl(variable.name.lexeme) is None:
                return {}

            current = self._lookup(variable.name)
            narrowed = (
                self._narrow_to(current, expr.test_type)
                if truth
                else self._narrow_away(current, expr.test_type)
            )
            if narrowed is None or narrowed == current:
                return {}

            return {variable.name.lexeme: narrowed}

        if isinstance(expr, Logical) and (
            (expr.operator.type is TokenType.AND and truth)
            or (expr.operator.type is TokenType.OR and not truth)
        ):
            return self._merge_refinements(
                self._refinements(expr.left, truth),
                self._refinements(expr.right, truth),
            )

        if isinstance(expr, Variable):
            found = self._find_decl(expr.name.lexeme)
            if found is None:
                return {}

            ty = truthy(found[1]) if truth else falsy(found[1])
            return {expr.name.lexeme: ty} if ty != found[1] else {}

        return {}

    def _nil_refinement(self, name: str, truth: bool, *, equal: bool) -> dict[str, Ty]:
        found = self._find_decl(name)
        if found is None:
            return {}

        declared = found[1]
        if equal:
            # x == nil
            narrowed = NIL if truth else non_nil(declared)
        else:
            # x != nil
            narrowed = non_nil(declared) if truth else NIL

        return {name: narrowed} if narrowed != declared else {}

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
                member
                for member in current.members
                if not self._is_test_subtype(member, test)
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
            return any(
                self._is_test_subtype(actual, member)
                for member in expected.members
            )
        if isinstance(actual, UnionTy):
            return all(
                self._is_test_subtype(member, expected)
                for member in actual.members
            )
        if isinstance(actual, ClassTy) and isinstance(expected, ClassTy):
            return self._is_subclass(actual.name, expected.name)
        if isinstance(actual, ListTy) and isinstance(expected, ListTy):
            return expected.element is ANY or self._is_test_subtype(
                actual.element, expected.element
            )
        if isinstance(actual, MapTy) and isinstance(expected, MapTy):
            key_ok = expected.key is ANY or self._is_test_subtype(
                actual.key, expected.key
            )
            value_ok = expected.value is ANY or self._is_test_subtype(
                actual.value, expected.value
            )
            return key_ok and value_ok

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
            return union(
                *(self._intersect_types(member, right) for member in left.members)
            )
        if isinstance(right, UnionTy):
            return union(
                *(self._intersect_types(left, member) for member in right.members)
            )
        if self._is_test_subtype(left, right):
            return left
        if self._is_test_subtype(right, left):
            return right

        return NEVER

    def _merge_refinements(
        self, left: dict[str, Ty], right: dict[str, Ty]
    ) -> dict[str, Ty]:
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

    def visit_print_stmt(self, stmt: Print) -> None:
        self._infer(stmt.expression)

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
                )
            return

        if self._in_initializer:
            self._error(stmt.keyword, "Can't return a value from an initializer.")
            return

        if self._current_return is not None:
            actual = self._check(stmt.value, self._current_return, stmt.keyword)
        else:
            actual = self._infer(stmt.value)

        if self._return_collector is not None:
            self._return_collector.append(actual)

    def visit_var_stmt(self, stmt: Var) -> None:
        if stmt.type_annotation is not None:
            annotated = self._resolve_type(stmt.type_annotation, stmt.name)
            if stmt.initializer is not None:
                self._check(stmt.initializer, annotated, stmt.name)
            self._define(stmt.name, annotated)
            return

        if stmt.initializer is None:
            self._error(
                stmt.name,
                f"Can't infer type of '{stmt.name.lexeme}'; add an annotation.",
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
                f"Can't infer type of '{stmt.name.lexeme}' from nil; "
                "add an annotation.",
            )
            self._define(stmt.name, ANY)
            return

        self._define(stmt.name, inferred)

    def visit_while_stmt(self, stmt: While) -> None:
        self._infer(stmt.condition)
        self._check_branch(stmt.body, self._refinements(stmt.condition, True))

    # --- expressões ---

    def visit_assign_expr(self, expr: Assign) -> Ty:
        expected = self._lookup_declared(expr.name)
        self._check(expr.value, expected, expr.name)
        self._invalidate(expr.name.lexeme)
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
                return self._promote(left, right)
            case TokenType.MINUS | TokenType.STAR | TokenType.PERCENT:
                if left is ANY or right is ANY:
                    return ANY
                self._numeric(left, operator)
                self._numeric(right, operator)
                return self._promote(left, right)
            case TokenType.SLASH:
                if left is ANY or right is ANY:
                    return ANY
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
            case TokenType.EQUAL_EQUAL | TokenType.BANG_EQUAL:
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

        self._error(token, "Operands must be integers.", lowerable=True)

    def _power_type(self, left: Ty, right: Ty, operator: Token) -> Ty:
        if left is ANY or right is ANY:
            return ANY
        for ty in (left, right):
            if ty is INT or ty is FLOAT:
                continue
            self._error(operator, "Operands must be numbers.", lowerable=True)
            return ERROR

        if left is FLOAT or right is FLOAT:
            return FLOAT

        return INT

    def _is_string(self, ty: Ty) -> bool:
        return ty is STRING

    def _comparison(self, left: Ty, right: Ty, operator: Token) -> Ty:
        if left is ANY or right is ANY:
            return BOOL
        self._numeric(left, operator)
        self._numeric(right, operator)
        return BOOL

    def visit_call_expr(self, expr: Call) -> Ty:
        return self._infer_call(expr, None, expr.paren)

    def _infer_call(
        self, expr: Call, expected: Ty | None, token: Token
    ) -> Ty:
        callee = self._infer(expr.callee)
        if isinstance(callee, GenericFnTy):
            return self._infer_generic_call(expr, callee, expected, token)

        signature = self._call_signature(callee, expr)
        arguments: list[Ty] = []

        for index, argument in enumerate(expr.arguments):
            expected_param: Ty | None = None
            if signature is not None and index < len(signature.params):
                expected_param = self._expected_element(signature.params[index])

            if (
                isinstance(argument, Lambda)
                and signature is not None
                and index < len(signature.params)
            ):
                arguments.append(
                    self._check(argument, signature.params[index], expr.paren)
                )
            elif isinstance(argument, ListLiteral) and expected_param is not None:
                assert signature is not None
                arguments.append(
                    self._check(argument, signature.params[index], expr.paren)
                )
            elif (
                isinstance(argument, MapLiteral)
                and signature is not None
                and index < len(signature.params)
                and self._expected_map(signature.params[index]) is not None
            ):
                arguments.append(
                    self._check(argument, signature.params[index], expr.paren)
                )
            else:
                arguments.append(self._infer(argument))

        return self._call_type(callee, expr, arguments)

    def _native_signature(self, name: str) -> FnTy | None:
        if name == "len":
            return FnTy((ANY,), INT, 1)
        if name in {"str", "repr"}:
            return FnTy((ANY,), STRING, 1)

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
            return info.init or FnTy((), ClassTy(callee.name), 0)
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
                return info.init or FnTy((), ClassTy(member.name), 0)

        return None

    def _call_type(self, callee: Ty, expr: Call, arguments: list[Ty]) -> Ty:
        if callee is ANY:
            return ANY
        if callee is ERROR:
            return ERROR

        nilable = callee is NIL or (
            isinstance(callee, UnionTy)
            and any(member is NIL for member in callee.members)
        )
        if nilable and not expr.optional:
            self._error(expr.paren, "Can only call functions and classes.")
            return ERROR
        if callee is NIL:
            return NIL

        members = list(callee.members) if isinstance(callee, UnionTy) else [callee]
        if expr.optional:
            members = [member for member in members if member is not NIL]
        if not members:
            return NIL
        if any(member != members[0] for member in members):
            self._error(expr.paren, "Can only call functions and classes.")
            return ERROR

        callable_ty = members[0]
        result: Ty

        if isinstance(callable_ty, ClassObjectTy):
            info = self._classes.get(callable_ty.name)
            if info is None:
                self._error(expr.paren, f"Unknown class '{callable_ty.name}'.")
                return ERROR

            signature = info.init or FnTy((), ClassTy(callable_ty.name), 0)
            self._check_call(expr.paren, signature, arguments)
            result = ClassTy(callable_ty.name)
        elif isinstance(callable_ty, FnTy):
            self._check_call(expr.paren, callable_ty, arguments)
            result = callable_ty.ret
        elif isinstance(callable_ty, NativeFnTy):
            result = self._call_native(callable_ty, expr, arguments)
        else:
            self._error(expr.paren, "Can only call functions and classes.")
            return ERROR

        return union(result, NIL) if expr.optional and nilable else result

    def _call_native(
        self, callee: NativeFnTy, expr: Call, arguments: list[Ty]
    ) -> Ty:
        if callee.name == "len":
            if len(arguments) != 1:
                self._error(
                    expr.paren, f"Expected 1 arguments but got {len(arguments)}."
                )
                return ERROR

            argument = arguments[0]
            if not self._is_len_able(argument):
                self._error(
                    expr.paren,
                    f"Expected a string, a list or a map, found {display(argument)}.",
                )
                return ERROR

            return INT

        if callee.name in {"str", "repr"}:
            if len(arguments) != 1:
                self._error(
                    expr.paren, f"Expected 1 arguments but got {len(arguments)}."
                )
                return ERROR

            if arguments[0] is ERROR:
                return ERROR

            return STRING

        if callee.name.startswith("math."):
            return self._call_math(callee.name, expr, arguments)

        self._error(expr.paren, "Can only call functions and classes.")
        return ERROR

    def _call_math(
        self, name: str, expr: Call, arguments: list[Ty]
    ) -> Ty:
        expected = 3 if name == "math.clamp" else 2 if name in {
            "math.min",
            "math.max",
        } else 1
        if len(arguments) != expected:
            self._error(
                expr.paren,
                f"Expected {expected} arguments but got {len(arguments)}.",
            )
            return ERROR

        if any(argument is ERROR for argument in arguments):
            return ERROR
        if name == "math.abs":
            return self._math_numeric_result("math.abs", arguments, expr.paren)
        if name in {"math.min", "math.max", "math.clamp"}:
            return self._math_numeric_result(name, arguments, expr.paren)

        self._error(expr.paren, "Can only call functions and classes.")
        return ERROR

    def _math_numeric_result(
        self, name: str, arguments: list[Ty], token: Token
    ) -> Ty:
        for argument in arguments:
            if argument is ANY:
                continue
            if argument is INT or argument is FLOAT:
                continue
            self._error(token, f"{name}() expects numbers.")
            return ERROR

        if any(argument is FLOAT for argument in arguments):
            return FLOAT
        if all(argument is INT for argument in arguments):
            return INT
        return union(INT, FLOAT)

    def _is_len_able(self, ty: Ty) -> bool:
        if ty is ANY or ty is STRING or ty is ERROR or isinstance(ty, ListTy):
            return True
        if isinstance(ty, MapTy):
            return True
        if isinstance(ty, UnionTy):
            return all(self._is_len_able(member) for member in ty.members)

        return False

    def _check_call(self, token: Token, signature: FnTy, arguments: list[Ty]) -> None:
        maximum = len(signature.params)
        minimum = signature.min_params
        count = len(arguments)

        if not minimum <= count <= maximum:
            if minimum == maximum:
                message = f"Expected {minimum} arguments but got {count}."
            elif count < minimum:
                message = f"Expected at least {minimum} arguments but got {count}."
            else:
                message = f"Expected {minimum} to {maximum} arguments but got {count}."
            self._error(token, message)
            return

        for index, (argument, param) in enumerate(
            zip(arguments, signature.params, strict=False), start=1
        ):
            if isinstance(argument, GenericFnTy):
                self._generic_value_error(token, argument.name)
                continue
            if not self._assignable(param, argument):
                self._error(
                    token,
                    f"Argument {index}: {self._mismatch_message(param, argument)}",
                )

    def _instantiate_generic(self, callee: GenericFnTy) -> GenericFnTy:
        fresh = [
            self._fresh_type_var(parameter.name)
            for parameter in callee.type_params
        ]
        mapping: dict[TyVar, Ty] = {
            parameter: variable
            for parameter, variable in zip(
                callee.type_params, fresh, strict=True
            )
        }
        fn = self._substitute(callee.fn, mapping)
        assert isinstance(fn, FnTy)
        return GenericFnTy(callee.name, tuple(fresh), fn)

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

        maximum = len(signature.params)
        minimum = signature.min_params
        count = len(expr.arguments)
        if not minimum <= count <= maximum:
            if minimum == maximum:
                message = f"Expected {minimum} arguments but got {count}."
            elif count < minimum:
                message = f"Expected at least {minimum} arguments but got {count}."
            else:
                message = (
                    f"Expected {minimum} to {maximum} arguments but got {count}."
                )
            self._error(token, message)
            return ERROR

        for index, argument in enumerate(expr.arguments):
            if index >= len(signature.params):
                break

            param = self._substitute(signature.params[index], bindings)
            actual = self._check_generic_argument(
                argument, param, bindings, token, index + 1
            )
            if actual is ERROR:
                return ERROR

        result = self._substitute(signature.ret, bindings)
        unbound = self._unbound_type_vars(result, instance.type_params)
        if unbound:
            names = ", ".join(f"'{variable.name}'" for variable in unbound)
            self._error(token, f"Can't infer type argument(s) {names}.")
            return ERROR

        self._check_polymorphic_recursion(instance, bindings, token)
        return result

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
                self._error(
                    token,
                    f"Argument {index}: {self._mismatch_message(resolved, actual)}",
                )
                return ERROR
            return actual

        if not self._has_any_type_var(resolved):
            return self._check(expr, resolved, token)

        if isinstance(expr, ListLiteral) and isinstance(resolved, ListTy):
            element = resolved.element
            for item in expr.elements:
                if (
                    self._check_generic_argument(
                        item, element, bindings, token, index
                    )
                    is ERROR
                ):
                    return ERROR
            return ListTy(self._substitute(element, bindings))

        if isinstance(expr, MapLiteral) and isinstance(resolved, MapTy):
            for key, value in expr.entries:
                if (
                    self._check_generic_argument(
                        key, resolved.key, bindings, token, index
                    )
                    is ERROR
                    or self._check_generic_argument(
                        value, resolved.value, bindings, token, index
                    )
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
                self._error(
                    token,
                    f"Argument {index}: {self._mismatch_message(resolved, actual)}",
                )
                return ERROR
            return actual

        if isinstance(expr, Call):
            actual = self._infer_call(expr, resolved, token)
            if actual is ERROR:
                return ERROR
            if not self._unify(resolved, actual, bindings, token):
                self._error(
                    token,
                    f"Argument {index}: {self._mismatch_message(resolved, actual)}",
                )
                return ERROR
            return actual

        actual = self._infer(expr)
        if isinstance(actual, GenericFnTy):
            return self._generic_value_error(token, actual.name)
        if not self._unify(resolved, actual, bindings, token):
            self._error(
                token,
                f"Argument {index}: {self._mismatch_message(resolved, actual)}",
            )
            return ERROR

        return actual

    def _generic_value_error(self, token: Token, name: str) -> Ty:
        self._error(
            token,
            f"Generic function '{name}' can't be used as a value yet; "
            "call it so its type arguments can be inferred.",
        )
        return ERROR

    def _substitute(self, ty: Ty, bindings: dict[TyVar, Ty]) -> Ty:
        if isinstance(ty, TyVar):
            replacement = bindings.get(ty)
            return self._substitute(replacement, bindings) if replacement else ty
        if isinstance(ty, ListTy):
            return ListTy(self._substitute(ty.element, bindings))
        if isinstance(ty, MapTy):
            return MapTy(
                self._substitute(ty.key, bindings),
                self._substitute(ty.value, bindings),
            )
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self._substitute(param, bindings) for param in ty.params),
                self._substitute(ty.ret, bindings),
                ty.min_params,
            )
        if isinstance(ty, UnionTy):
            return union(
                *(self._substitute(member, bindings) for member in ty.members)
            )

        return ty

    def _has_any_type_var(self, ty: Ty) -> bool:
        if isinstance(ty, TyVar):
            return True
        if isinstance(ty, ListTy):
            return self._has_any_type_var(ty.element)
        if isinstance(ty, MapTy):
            return self._has_any_type_var(ty.key) or self._has_any_type_var(ty.value)
        if isinstance(ty, FnTy):
            return any(self._has_any_type_var(param) for param in ty.params) or (
                self._has_any_type_var(ty.ret)
            )
        if isinstance(ty, UnionTy):
            return any(self._has_any_type_var(member) for member in ty.members)

        return False

    def _occurs(
        self, variable: TyVar, ty: Ty, bindings: dict[TyVar, Ty]
    ) -> bool:
        ty = self._substitute(ty, bindings)
        if isinstance(ty, TyVar):
            return ty == variable
        if isinstance(ty, ListTy):
            return self._occurs(variable, ty.element, bindings)
        if isinstance(ty, MapTy):
            return self._occurs(variable, ty.key, bindings) or self._occurs(
                variable, ty.value, bindings
            )
        if isinstance(ty, FnTy):
            return any(
                self._occurs(variable, param, bindings) for param in ty.params
            ) or self._occurs(variable, ty.ret, bindings)
        if isinstance(ty, UnionTy):
            return any(
                self._occurs(variable, member, bindings)
                for member in ty.members
            )

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
                )
                return False
            if self._occurs(expected, actual, bindings):
                self._error(
                    token,
                    f"Recursive type inferred for '{expected.name}'.",
                )
                return False
            bindings[expected] = actual
            return True

        if expected == actual:
            return True

        if not self._has_any_type_var(expected) and not self._has_any_type_var(
            actual
        ):
            return self._assignable(expected, actual)

        if isinstance(expected, ListTy) and isinstance(actual, ListTy):
            return self._unify(expected.element, actual.element, bindings, token)
        if isinstance(expected, MapTy) and isinstance(actual, MapTy):
            return self._unify(
                expected.key, actual.key, bindings, token
            ) and self._unify(expected.value, actual.value, bindings, token)
        if isinstance(expected, FnTy) and isinstance(actual, FnTy):
            if not actual.min_params <= len(expected.params) <= len(actual.params):
                return False
            for expected_param, actual_param in zip(
                expected.params, actual.params, strict=False
            ):
                if not self._unify(
                    expected_param, actual_param, bindings, token
                ):
                    return False
            return self._unify(expected.ret, actual.ret, bindings, token)
        if isinstance(expected, UnionTy):
            for member in expected.members:
                trial = dict(bindings)
                if self._unify(member, actual, trial, token):
                    bindings.clear()
                    bindings.update(trial)
                    return True
            return False

        return False

    def _unbound_type_vars(
        self, ty: Ty, variables: tuple[TyVar, ...]
    ) -> list[TyVar]:
        if isinstance(ty, TyVar):
            return [ty] if ty in variables else []
        if isinstance(ty, ListTy):
            return self._unbound_type_vars(ty.element, variables)
        if isinstance(ty, MapTy):
            return self._unbound_type_vars(
                ty.key, variables
            ) + self._unbound_type_vars(ty.value, variables)
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
        if isinstance(ty, ListTy):
            return self._contains_any_type_var(ty.element, variables)
        if isinstance(ty, MapTy):
            return self._contains_any_type_var(
                ty.key, variables
            ) or self._contains_any_type_var(ty.value, variables)
        if isinstance(ty, FnTy):
            return any(
                self._contains_any_type_var(param, variables)
                for param in ty.params
            ) or self._contains_any_type_var(ty.ret, variables)
        if isinstance(ty, UnionTy):
            return any(
                self._contains_any_type_var(member, variables)
                for member in ty.members
            )

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

        for fresh, current in zip(
            instance.type_params, current_params, strict=False
        ):
            argument = self._substitute(fresh, bindings)
            if argument == current:
                continue
            if self._contains_any_type_var(argument, current_params):
                self._error(
                    token,
                    "Polymorphic recursion is not supported yet; "
                    "the type arguments must stay the same.",
                )
                return


    def visit_get_expr(self, expr: Get) -> Ty:
        obj = self._infer(expr.object)
        return self._get_property_type(obj, expr.name, expr.optional)

    def _get_property_type(self, obj: Ty, name: Token, optional: bool) -> Ty:
        if obj is ANY:
            return ANY
        if isinstance(obj, NativeModuleTy):
            member = self._native_modules.get(obj.name, {}).get(name.lexeme)
            if member is None:
                self._error(
                    name, f"Undefined property '{name.lexeme}'."
                )
                return ERROR
            return member

        nilable = obj is NIL or (
            isinstance(obj, UnionTy) and any(member is NIL for member in obj.members)
        )
        if nilable and not optional:
            self._error(name, "Only instances have properties.")
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
        elif all(isinstance(member, ClassTy) for member in members):
            classes = [member for member in members if isinstance(member, ClassTy)]
            if len(classes) == 1:
                result = self._instance_property(classes[0], name)
            else:
                results = [
                    self._instance_property(member, name, report=False)
                    for member in classes
                ]
                if any(item != results[0] for item in results):
                    self._error(name, "Only instances have properties.")
                    return ERROR
                result = results[0]
        else:
            self._error(name, "Only instances have properties.")
            return ERROR

        return union(result, NIL) if optional and nilable else result

    def _list_property(self, lists: list[ListTy], name: Token) -> Ty:
        element = lists[0].element
        if any(item.element != element for item in lists[1:]):
            self._error(name, "List method requires a single element type.")
            return ERROR

        if name.lexeme == "push":
            return FnTy((element,), NIL, 1)
        if name.lexeme == "pop":
            return FnTy((), element, 0)

        self._error(name, f"Undefined property '{name.lexeme}'.")
        return ERROR

    def _map_property(self, maps: list[MapTy], name: Token) -> Ty:
        key = maps[0].key
        value = maps[0].value
        if any(item.key != key or item.value != value for item in maps[1:]):
            self._error(name, "Map method requires a single key/value type.")
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

        self._error(name, f"Undefined property '{name.lexeme}'.")
        return ERROR

    def _instance_property(
        self, obj: ClassTy, name: Token, *, report: bool = True
    ) -> Ty:
        field_info = self._find_field(obj.name, name.lexeme)
        if field_info is not None:
            return field_info.ty

        method = self._find_method(obj.name, name.lexeme)
        if method is not None:
            return method

        if report:
            self._error(name, f"Undefined property '{name.lexeme}'.")

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
                "Can't infer the element type of an empty list; "
                "annotate it as List[T].",
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
                "Can't infer the key and value types of an empty map; "
                "annotate it as Map[K, V].",
            )
            return MapTy(ERROR, ERROR)

        key_ty = self._infer(expr.entries[0][0])
        value_ty = self._infer(expr.entries[0][1])
        for key, value in expr.entries[1:]:
            key_ty = self._join_map_key(key_ty, self._infer(key), expr.brace)
            value_ty = self._join_map_value(value_ty, self._infer(value), expr.brace)

        if not self._valid_map_key(key_ty):
            self._error(expr.brace, "Map keys must be String, Int or Bool.")
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
        )
        return ERROR

    def visit_index_expr(self, expr: Index) -> Ty:
        obj = self._infer(expr.object)
        if isinstance(obj, GenericFnTy):
            self._error(
                expr.bracket,
                "Type arguments on a call aren't supported; "
                "let the checker infer them.",
            )
            return ERROR

        index = self._infer(expr.index)

        if obj is ANY:
            return ANY
        if obj is ERROR:
            return ERROR
        if isinstance(obj, MapTy):
            if not self._assignable(obj.key, index):
                self._error(
                    expr.bracket,
                    f"Expected {display(obj.key)}, found {display(index)}.",
                )
            return obj.value
        if not isinstance(obj, ListTy):
            self._error(expr.bracket, "Only lists and maps can be indexed.")
            return ERROR

        self._check_index_type(index, expr)
        return obj.element

    def visit_index_set_expr(self, expr: IndexSet) -> Ty:
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
                )
            if not self._assignable(obj.value, value):
                self._error(
                    expr.bracket,
                    f"Expected {display(obj.value)}, found {display(value)}.",
                )
            return value
        if not isinstance(obj, ListTy):
            self._error(expr.bracket, "Only lists and maps can be indexed.")
            return value

        self._check_index_type(index, expr)
        if not self._assignable(obj.element, value):
            self._error(
                expr.bracket,
                f"Expected {display(obj.element)}, found {display(value)}.",
            )

        return value

    def _check_index_type(self, index: Ty, expr: Index | IndexSet) -> None:
        if index is INT or index is ANY or index is ERROR:
            return

        self._error(
            expr.bracket,
            f"List index must be an integer, found {display(index)}.",
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
            if (
                isinstance(expr.right, ListLiteral)
                and self._expected_element(expected) is not None
            ):
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

            self._error(expr.operator, "Range bounds must be integers.")
            return ERROR

        return RANGE

    def visit_set_expr(self, expr: Set) -> Ty:
        obj = self._infer(expr.object)

        if obj is ANY:
            return self._infer(expr.value)

        if not isinstance(obj, ClassTy):
            self._infer(expr.value)
            self._error(expr.name, "Only instances have fields.")
            return ANY

        field_info = self._find_field(obj.name, expr.name.lexeme)
        if field_info is None:
            self._infer(expr.value)
            self._error(expr.name, f"Undefined field '{expr.name.lexeme}'.")
            return ANY

        value = self._check(expr.value, field_info.ty, expr.name)

        is_initializer_this = self._in_initializer and isinstance(expr.object, This)
        if not field_info.mutable and not is_initializer_this:
            self._error(
                expr.name,
                f"Can't assign to immutable field '{expr.name.lexeme}'.",
            )

        return value

    def visit_super_expr(self, expr: Super) -> Ty:
        if self._current_class is None or self._current_class.superclass is None:
            return ERROR

        method = self._find_method(
            self._current_class.superclass, expr.method.lexeme
        )
        if method is None:
            self._error(expr.method, f"Undefined property '{expr.method.lexeme}'.")
            return ERROR

        return method

    def visit_this_expr(self, expr: This) -> Ty:
        if self._current_class is None:
            return ERROR

        return ClassTy(self._current_class.name)

    def visit_unary_expr(self, expr: Unary) -> Ty:
        right = self._infer(expr.right)

        if expr.operator.type is TokenType.BANG:
            return BOOL
        if expr.operator.type is TokenType.TILDE:
            if right is ANY:
                return ANY
            if right is INT:
                return INT
            self._error(expr.operator, "Operand must be an integer.", lowerable=True)
            return ERROR
        if right is ANY:
            return ANY
        if right is INT or right is FLOAT:
            return right

        self._error(expr.operator, "Operand must be a number.", lowerable=True)
        return ERROR

    def visit_variable_expr(self, expr: Variable) -> Ty:
        return self._lookup(expr.name)
