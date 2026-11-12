"""Type checker estático (gradual) — roda depois do resolver, antes de executar.

Anotações são opcionais no runtime; em `--check` as funções precisam de parâmetros e
retorno anotados. Tipos são apagados: o interpretador continua dinâmico.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.error_reporter import ErrorReporter
from src.expr import (
    Assign,
    Binary,
    Call,
    Conditional,
    Expr,
    Get,
    Grouping,
    Index,
    IndexSet,
    ListLiteral,
    Literal,
    Logical,
    Range,
    Set,
    Super,
    This,
    Unary,
    Variable,
)
from src.expr import Visitor as ExprVisitor
from src.stmt import (
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
from src.stmt import Visitor as StmtVisitor
from src.token_type import TokenType
from src.tokens import Token
from src.ty import (
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
    ListTy,
    MapTy,
    NativeFnTy,
    Ty,
    UnionTy,
    display,
    falsy,
    is_nilable,
    non_nil,
    truthy,
    union,
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
    init: FnTy | None = None


class Checker(ExprVisitor[Ty], StmtVisitor[None]):
    def __init__(self, reporter: ErrorReporter) -> None:
        self._reporter = reporter
        self._scopes: list[dict[str, Ty]] = [{}]
        self._classes: dict[str, ClassInfo] = {}
        self._current_class: ClassInfo | None = None
        self._current_return: Ty | None = None
        self._in_initializer = False
        self._define_builtins()

    def check(self, statements: list[Stmt]) -> None:
        self._predeclare_classes(statements)
        for statement in statements:
            self._check_stmt(statement)

    # --- infraestrutura ---

    def _define_builtins(self) -> None:
        self._scopes[0]["clock"] = FnTy((), FLOAT, 0)
        self._scopes[0]["len"] = NativeFnTy("len")
        self._scopes[0]["range"] = FnTy((INT, INT, INT), RANGE, 3)

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

    def _begin_scope(self) -> None:
        self._scopes.append({})

    def _end_scope(self) -> None:
        self._scopes.pop()

    def _define(self, name: Token, ty: Ty) -> None:
        self._scopes[-1][name.lexeme] = ty

    def _lookup(self, name: Token) -> Ty:
        for scope in reversed(self._scopes):
            if name.lexeme in scope:
                return scope[name.lexeme]

        self._error(name, f"Undefined variable '{name.lexeme}'.")
        return ERROR

    def _error(self, token: Token, message: str) -> None:
        self._reporter.error(token, message)

    def _check_stmt(self, stmt: Stmt) -> None:
        stmt.accept(self)

    def _infer(self, expr: Expr) -> Ty:
        return expr.accept(self)

    def _check(
        self, expr: Expr, expected: Ty, token: Token
    ) -> Ty:
        if isinstance(expr, ListLiteral):
            element = self._expected_element(expected)
            if element is not None:
                for item in expr.elements:
                    self._check(item, element, expr.bracket)

                return ListTy(element)

        actual = self._infer(expr)
        if not self._assignable(expected, actual):
            self._error(
                token, f"Expected {display(expected)}, found {display(actual)}."
            )

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
        if actual is INT and expected is FLOAT:
            return True
        if isinstance(expected, ListTy) and isinstance(actual, ListTy):
            if expected.element is ERROR or actual.element is ERROR:
                return True
            return expected.element == actual.element
        if isinstance(expected, ClassTy) and isinstance(actual, ClassTy):
            return self._is_subclass(actual.name, expected.name)

        return False

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
            if ty.name not in self._classes:
                self._error(token, f"Unknown type '{ty.name}'.")
                return ERROR
            return ty
        if isinstance(ty, ListTy):
            return ListTy(self._resolve_type(ty.element, token))
        if isinstance(ty, MapTy):
            return MapTy(
                self._resolve_type(ty.key, token),
                self._resolve_type(ty.value, token),
            )
        if isinstance(ty, UnionTy):
            return union(
                *(self._resolve_type(member, token) for member in ty.members)
            )

        return ty

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

        self._error(token, "Operands must be numbers.")
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
            signature = self._signature(method, is_init=is_init)
            if is_init:
                info.init = signature
            else:
                info.methods[method.name.lexeme] = signature

        for method in stmt.methods:
            is_init = method.name.lexeme == "init"
            body_signature = (
                info.init if is_init else info.methods.get(method.name.lexeme)
            )
            assert body_signature is not None
            self._check_function_body(method, body_signature, info, is_init=is_init)

        self._current_class = enclosing

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

        self._error(token, "Can only iterate over a range, a list or a string.")
        return ERROR

    def visit_function_stmt(self, stmt: Function) -> None:
        signature = self._signature(stmt, is_init=False)
        self._define(stmt.name, signature)
        self._check_function_body(stmt, signature, None, is_init=False)

    def _signature(self, stmt: Function, *, is_init: bool) -> FnTy:
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

        return FnTy(tuple(param_types), return_ty, minimum)

    def _check_function_body(
        self,
        stmt: Function,
        signature: FnTy,
        class_info: ClassInfo | None,
        *,
        is_init: bool,
    ) -> None:
        enclosing_class = self._current_class
        enclosing_return = self._current_return
        enclosing_init = self._in_initializer

        self._current_class = class_info
        self._current_return = NIL if is_init else signature.ret
        self._in_initializer = is_init

        self._begin_scope()
        if class_info is not None:
            self._scopes[-1]["this"] = ClassTy(class_info.name)
            if class_info.superclass is not None:
                self._scopes[-1]["super"] = ClassObjectTy(class_info.superclass)

        for param, param_ty in zip(stmt.params, signature.params, strict=True):
            self._define(param.name, param_ty)

        for statement in stmt.body:
            self._check_stmt(statement)

        self._end_scope()

        self._current_class = enclosing_class
        self._current_return = enclosing_return
        self._in_initializer = enclosing_init

    def visit_if_stmt(self, stmt: If) -> None:
        self._infer(stmt.condition)
        self._check_stmt(stmt.then_branch)
        if stmt.else_branch is not None:
            self._check_stmt(stmt.else_branch)

    def visit_print_stmt(self, stmt: Print) -> None:
        self._infer(stmt.expression)

    def visit_return_stmt(self, stmt: Return) -> None:
        if stmt.value is None:
            return

        if self._in_initializer:
            self._error(stmt.keyword, "Can't return a value from an initializer.")
            return

        if self._current_return is not None:
            self._check(stmt.value, self._current_return, stmt.keyword)

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

        self._define(stmt.name, self._infer(stmt.initializer))

    def visit_while_stmt(self, stmt: While) -> None:
        self._infer(stmt.condition)
        self._check_stmt(stmt.body)

    # --- expressões ---

    def visit_assign_expr(self, expr: Assign) -> Ty:
        expected = self._lookup(expr.name)
        self._check(expr.value, expected, expr.name)
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

        self._error(token, "Operands must be integers.")

    def _power_type(self, left: Ty, right: Ty, operator: Token) -> Ty:
        if left is ANY or right is ANY:
            return ANY
        for ty in (left, right):
            if ty is INT or ty is FLOAT:
                continue
            self._error(operator, "Operands must be numbers.")
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
        callee = self._infer(expr.callee)
        signature = self._call_signature(callee, expr)
        arguments: list[Ty] = []

        for index, argument in enumerate(expr.arguments):
            expected: Ty | None = None
            if signature is not None and index < len(signature.params):
                expected = self._expected_element(signature.params[index])

            if isinstance(argument, ListLiteral) and expected is not None:
                assert signature is not None
                arguments.append(
                    self._check(argument, signature.params[index], expr.paren)
                )
            else:
                arguments.append(self._infer(argument))

        return self._call_type(callee, expr, arguments)

    def _call_signature(self, callee: Ty, expr: Call) -> FnTy | None:
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
                    f"Expected a string or a list, found {display(argument)}.",
                )
                return ERROR

            return INT

        self._error(expr.paren, "Can only call functions and classes.")
        return ERROR

    def _is_len_able(self, ty: Ty) -> bool:
        if ty is ANY or ty is STRING or ty is ERROR or isinstance(ty, ListTy):
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

        for argument, param in zip(arguments, signature.params, strict=False):
            if not self._assignable(param, argument):
                self._error(
                    token,
                    f"Expected {display(param)}, found {display(argument)}.",
                )

    def visit_get_expr(self, expr: Get) -> Ty:
        obj = self._infer(expr.object)
        return self._get_property_type(obj, expr.name, expr.optional)

    def _get_property_type(self, obj: Ty, name: Token, optional: bool) -> Ty:
        if obj is ANY:
            return ANY

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

    def visit_index_expr(self, expr: Index) -> Ty:
        obj = self._infer(expr.object)
        index = self._infer(expr.index)

        if obj is ANY:
            return ANY
        if obj is ERROR:
            return ERROR
        if not isinstance(obj, ListTy):
            self._error(expr.bracket, "Only lists can be indexed.")
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
        if not isinstance(obj, ListTy):
            self._error(expr.bracket, "Only lists can be indexed.")
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
            self._error(expr.operator, "Operand must be an integer.")
            return ERROR
        if right is ANY:
            return ANY
        if right is INT or right is FLOAT:
            return right

        self._error(expr.operator, "Operand must be a number.")
        return ERROR

    def visit_variable_expr(self, expr: Variable) -> Ty:
        return self._lookup(expr.name)
