# SPDX-License-Identifier: MIT OR Apache-2.0
"""Álgebra de tipos do checker: atribuição, unificação e substituição.

Parte do split `TypeOps`/`DeclTable` do ADR-0141. As operações aqui são puras
(sem fluxo); o `Checker` injeta a tabela de declarações, o reporter de erro e a
assinatura das natives, e delega.
"""

from __future__ import annotations

from collections.abc import Callable

from loxia_core.diagnostics.codes import Code
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import (
    ANY,
    ERROR,
    FLOAT,
    INT,
    NEVER,
    NIL,
    STRING,
    ClassObjectTy,
    ClassTy,
    EnumTy,
    FnTy,
    InterfaceTy,
    ListTy,
    MapTy,
    NativeFnTy,
    TupleTy,
    Ty,
    TyVar,
    UnionTy,
    union,
)
from loxia_core.semantics.decl_table import DeclTable

ErrorCallback = Callable[..., None]
NativeSignature = Callable[[str], FnTy | None]

ORD_TYPES: tuple[Ty, ...] = (INT, FLOAT, STRING)
NUM_TYPES: tuple[Ty, ...] = (INT, FLOAT)


class TypeOps:
    """Operações de tipo compartilhadas; não guarda estado de fluxo."""

    def __init__(
        self,
        decls: DeclTable,
        *,
        gradual: bool,
        error: ErrorCallback,
        native_signature: NativeSignature,
    ) -> None:
        self._decls = decls
        self._gradual = gradual
        self._error = error
        self._native_signature = native_signature

    def assignable(self, expected: Ty, actual: Ty) -> bool:
        # `Any` é top type: qualquer `T` é atribuível a `Any`. O contrário exige
        # conversão explícita (`as`), porque os tipos são apagados no runtime —
        # deixar `Any -> T` passar aqui fazia o backend reinterpretar o payload
        # (ponteiro vazado/segfault) e quebrava I1/I2/I3.
        if expected is ANY or expected is ERROR or actual is ERROR:
            return True
        if actual is NEVER:
            return True
        # No modo gradual o `Any` é consistente com qualquer tipo (o programa roda no
        # tree-walk, sem lowering); o `as` continua obrigatório no `--check` estrito.
        if self._gradual and actual is ANY:
            return True
        if expected == actual:
            return True
        # Rebinding de classe é dinâmico por ADR-0044: `Base = OtherBase as Any`
        # continua válido (a suíte oficial reatribui uma superclasse); o backend
        # representa classe como ponteiro. Um `Any` que não guarda classe é erro
        # do usuário: a divergência entre os motores está registrada em
        # `docs/adr/0150-objeto-de-classe-nao-e-valor-de-funcao.md`.
        if isinstance(expected, ClassObjectTy) and actual is ANY:
            return True
        # Destructuring com anotação de tupla é o formulário explícito previsto
        # em ADR-0069 para um valor vindo de `Any`; o backend desemboxa a tupla.
        if isinstance(expected, TupleTy) and actual is ANY:
            return True
        if isinstance(actual, UnionTy):
            return all(self.assignable(expected, member) for member in actual.members)
        if isinstance(expected, UnionTy):
            return any(self.assignable(member, actual) for member in expected.members)
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
                self.assignable(expected_item, actual_item)
                for expected_item, actual_item in zip(expected.items, actual.items, strict=True)
            )
        if isinstance(expected, FnTy):
            if isinstance(actual, FnTy):
                return self.assignable_fn(expected, actual)
            if isinstance(actual, NativeFnTy):
                native_signature = self._native_signature(actual.name)
                return native_signature is not None and self.assignable_fn(
                    expected, native_signature
                )
        if isinstance(expected, ClassTy) and isinstance(actual, ClassTy):
            if expected.args or actual.args:
                return expected.name == actual.name and expected.args == actual.args
            return self._decls.is_subclass(actual.name, expected.name)
        if isinstance(expected, InterfaceTy):
            if isinstance(actual, InterfaceTy):
                return expected.name == actual.name
            if isinstance(actual, ClassTy):
                return expected.name == actual.name or self._decls.implements_interface(
                    actual.name, expected.name
                )
            return False
        if isinstance(expected, ClassTy) and isinstance(actual, InterfaceTy):
            return expected.name == actual.name
        if isinstance(expected, EnumTy) and isinstance(actual, EnumTy):
            return expected.name == actual.name and expected.args == actual.args

        return False

    def assignable_fn(self, expected: FnTy, actual: FnTy) -> bool:
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
            if not self.assignable(actual_param, expected_param):
                return False

        return self.assignable(expected.ret, actual.ret)

    def unify(
        self,
        expected: Ty,
        actual: Ty,
        bindings: dict[TyVar, Ty],
        token: Token,
    ) -> bool:
        expected = self.substitute(expected, bindings)
        actual = self.substitute(actual, bindings)

        if expected is ERROR or actual is ERROR:
            return True
        if expected is ANY:
            return True
        if isinstance(expected, TyVar):
            if isinstance(actual, TyVar) and actual == expected:
                return True
            if actual is ANY:
                if self._gradual:
                    # Sem anotação, o argumento é `Any`: instancia com `Any` e segue.
                    bindings[expected] = ANY
                    return True
                self._error(
                    token,
                    f"Can't infer type argument '{expected.name}' from Any.",
                    code=Code.GENERIC_INFERENCE,
                )
                return False
            if self.occurs(expected, actual, bindings):
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
                return self.assignable(expected, actual)
            return all(
                self.unify(expected_arg, actual_arg, bindings, token)
                for expected_arg, actual_arg in zip(expected.args, actual.args, strict=True)
            )
        if isinstance(expected, EnumTy) and isinstance(actual, EnumTy):
            if expected.name != actual.name or len(expected.args) != len(actual.args):
                return False
            return all(
                self.unify(expected_arg, actual_arg, bindings, token)
                for expected_arg, actual_arg in zip(expected.args, actual.args, strict=True)
            )

        if not self.has_any_type_var(expected) and not self.has_any_type_var(actual):
            return self.assignable(expected, actual)

        if isinstance(expected, ListTy) and isinstance(actual, ListTy):
            return self.unify(expected.element, actual.element, bindings, token)
        if isinstance(expected, MapTy) and isinstance(actual, MapTy):
            return self.unify(expected.key, actual.key, bindings, token) and self.unify(
                expected.value, actual.value, bindings, token
            )
        if isinstance(expected, TupleTy) and isinstance(actual, TupleTy):
            return len(expected.items) == len(actual.items) and all(
                self.unify(expected_item, actual_item, bindings, token)
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
                if not self.unify(expected_param, actual_param, bindings, token):
                    return False
            return self.unify(expected.ret, actual.ret, bindings, token)
        if isinstance(expected, UnionTy):
            # `T?` unifica com `Int?` como T=Int, não T=Int? (opcional aninhado).
            if isinstance(actual, UnionTy):
                expected_non_nil = [member for member in expected.members if member is not NIL]
                actual_non_nil = [member for member in actual.members if member is not NIL]
                if len(expected_non_nil) == 1 and len(actual_non_nil) == 1:
                    return self.unify(
                        expected_non_nil[0],
                        actual_non_nil[0],
                        bindings,
                        token,
                    )
            for member in expected.members:
                trial = dict(bindings)
                if self.unify(member, actual, trial, token):
                    bindings.clear()
                    bindings.update(trial)
                    return True
            return False

        return False

    def substitute(self, ty: Ty, bindings: dict[TyVar, Ty]) -> Ty:
        if isinstance(ty, TyVar):
            replacement = bindings.get(ty)
            if replacement is None or replacement == ty:
                return ty
            return self.substitute(replacement, bindings)
        if isinstance(ty, ClassTy):
            return ClassTy(
                ty.name,
                tuple(self.substitute(arg, bindings) for arg in ty.args),
            )
        if isinstance(ty, EnumTy):
            return EnumTy(
                ty.name,
                tuple(self.substitute(arg, bindings) for arg in ty.args),
            )
        if isinstance(ty, ListTy):
            return ListTy(self.substitute(ty.element, bindings))
        if isinstance(ty, MapTy):
            return MapTy(
                self.substitute(ty.key, bindings),
                self.substitute(ty.value, bindings),
            )
        if isinstance(ty, TupleTy):
            return TupleTy(tuple(self.substitute(item, bindings) for item in ty.items))
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self.substitute(param, bindings) for param in ty.params),
                self.substitute(ty.ret, bindings),
                ty.min_params,
                ty.variadic,
            )
        if isinstance(ty, UnionTy):
            return union(*(self.substitute(member, bindings) for member in ty.members))

        return ty

    def has_any_type_var(self, ty: Ty) -> bool:
        if isinstance(ty, TyVar):
            return True
        if isinstance(ty, ClassTy):
            return any(self.has_any_type_var(arg) for arg in ty.args)
        if isinstance(ty, EnumTy):
            return any(self.has_any_type_var(arg) for arg in ty.args)
        if isinstance(ty, ListTy):
            return self.has_any_type_var(ty.element)
        if isinstance(ty, MapTy):
            return self.has_any_type_var(ty.key) or self.has_any_type_var(ty.value)
        if isinstance(ty, TupleTy):
            return any(self.has_any_type_var(item) for item in ty.items)
        if isinstance(ty, FnTy):
            return any(self.has_any_type_var(param) for param in ty.params) or (
                self.has_any_type_var(ty.ret)
            )
        if isinstance(ty, UnionTy):
            return any(self.has_any_type_var(member) for member in ty.members)

        return False

    def occurs(self, variable: TyVar, ty: Ty, bindings: dict[TyVar, Ty]) -> bool:
        ty = self.substitute(ty, bindings)
        if isinstance(ty, TyVar):
            return ty == variable
        if isinstance(ty, ClassTy):
            return any(self.occurs(variable, arg, bindings) for arg in ty.args)
        if isinstance(ty, EnumTy):
            return any(self.occurs(variable, arg, bindings) for arg in ty.args)
        if isinstance(ty, ListTy):
            return self.occurs(variable, ty.element, bindings)
        if isinstance(ty, MapTy):
            return self.occurs(variable, ty.key, bindings) or self.occurs(
                variable, ty.value, bindings
            )
        if isinstance(ty, TupleTy):
            return any(self.occurs(variable, item, bindings) for item in ty.items)
        if isinstance(ty, FnTy):
            return any(self.occurs(variable, param, bindings) for param in ty.params) or (
                self.occurs(variable, ty.ret, bindings)
            )
        if isinstance(ty, UnionTy):
            return any(self.occurs(variable, member, bindings) for member in ty.members)

        return False

    def unbound_type_vars(self, ty: Ty, variables: tuple[TyVar, ...]) -> list[TyVar]:
        if isinstance(ty, TyVar):
            return [ty] if ty in variables else []
        if isinstance(ty, ClassTy):
            class_vars: list[TyVar] = []
            for arg in ty.args:
                class_vars.extend(self.unbound_type_vars(arg, variables))
            return class_vars
        if isinstance(ty, EnumTy):
            enum_vars: list[TyVar] = []
            for arg in ty.args:
                enum_vars.extend(self.unbound_type_vars(arg, variables))
            return enum_vars
        if isinstance(ty, ListTy):
            return self.unbound_type_vars(ty.element, variables)
        if isinstance(ty, MapTy):
            return self.unbound_type_vars(ty.key, variables) + self.unbound_type_vars(
                ty.value, variables
            )
        if isinstance(ty, TupleTy):
            tuple_vars: list[TyVar] = []
            for item in ty.items:
                tuple_vars.extend(self.unbound_type_vars(item, variables))
            return tuple_vars
        if isinstance(ty, FnTy):
            found: list[TyVar] = []
            for param in ty.params:
                found.extend(self.unbound_type_vars(param, variables))
            found.extend(self.unbound_type_vars(ty.ret, variables))
            return found
        if isinstance(ty, UnionTy):
            found_union: list[TyVar] = []
            for member in ty.members:
                found_union.extend(self.unbound_type_vars(member, variables))
            return found_union

        return []

    def contains_type_var(self, ty: Ty) -> bool:
        if isinstance(ty, TyVar):
            return True
        if isinstance(ty, ClassTy):
            return any(self.contains_type_var(arg) for arg in ty.args)
        if isinstance(ty, FnTy):
            return any(self.contains_type_var(param) for param in ty.params) or (
                self.contains_type_var(ty.ret)
            )
        return False

    def contains_any_type_var(self, ty: Ty, variables: tuple[TyVar, ...]) -> bool:
        if isinstance(ty, TyVar):
            return ty in variables
        if isinstance(ty, ClassTy):
            return any(self.contains_any_type_var(arg, variables) for arg in ty.args)
        if isinstance(ty, EnumTy):
            return any(self.contains_any_type_var(arg, variables) for arg in ty.args)
        if isinstance(ty, ListTy):
            return self.contains_any_type_var(ty.element, variables)
        if isinstance(ty, MapTy):
            return self.contains_any_type_var(ty.key, variables) or self.contains_any_type_var(
                ty.value, variables
            )
        if isinstance(ty, TupleTy):
            return any(self.contains_any_type_var(item, variables) for item in ty.items)
        if isinstance(ty, FnTy):
            return any(self.contains_any_type_var(param, variables) for param in ty.params) or (
                self.contains_any_type_var(ty.ret, variables)
            )
        if isinstance(ty, UnionTy):
            return any(self.contains_any_type_var(member, variables) for member in ty.members)

        return False

    def satisfies_bound(self, actual: Ty, bound: str) -> bool:
        if self._gradual and actual is ANY:
            # `Any` é consistente com qualquer constraint no modo gradual.
            return True
        if isinstance(actual, TyVar):
            return bound in actual.bounds
        if isinstance(actual, InterfaceTy):
            return actual.name == bound
        if bound == "Ord":
            return any(actual is candidate for candidate in ORD_TYPES)
        if bound == "Num":
            return any(actual is candidate for candidate in NUM_TYPES)
        if isinstance(actual, ClassTy):
            return self._decls.implements_interface(actual.name, bound)
        return False

    def is_test_subtype(self, actual: Ty, expected: Ty) -> bool:
        """Subtipo para teste de runtime, **sem** promoção `Int → Float`.

        `assignable` é a relação de atribuição (aceita `Int` onde se espera `Float`); para
        `is`, `1` não é `Float`, então a relação precisa ser mais estrita.
        """
        if expected is ANY:
            return True
        if actual is NEVER:
            return True
        if actual == expected:
            return True
        if isinstance(expected, UnionTy):
            return any(self.is_test_subtype(actual, member) for member in expected.members)
        if isinstance(actual, UnionTy):
            return all(self.is_test_subtype(member, expected) for member in actual.members)
        if isinstance(actual, FnTy) and isinstance(expected, FnTy):
            return self.assignable_fn(expected, actual)
        if isinstance(actual, ClassTy) and isinstance(expected, ClassTy):
            if expected.args or actual.args:
                return actual.name == expected.name and actual.args == expected.args
            return self._decls.is_subclass(actual.name, expected.name)
        if isinstance(actual, EnumTy) and isinstance(expected, EnumTy):
            return actual.name == expected.name and (
                not expected.args or actual.args == expected.args
            )
        if isinstance(actual, ListTy) and isinstance(expected, ListTy):
            return expected.element is ANY or self.is_test_subtype(actual.element, expected.element)
        if isinstance(actual, MapTy) and isinstance(expected, MapTy):
            key_ok = expected.key is ANY or self.is_test_subtype(actual.key, expected.key)
            value_ok = expected.value is ANY or self.is_test_subtype(actual.value, expected.value)
            return key_ok and value_ok
        if isinstance(actual, TupleTy) and isinstance(expected, TupleTy):
            return len(actual.items) == len(expected.items) and all(
                self.is_test_subtype(actual_item, expected_item)
                for actual_item, expected_item in zip(actual.items, expected.items, strict=True)
            )

        return False

    def intersect_types(self, left: Ty, right: Ty) -> Ty:
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
            return union(*(self.intersect_types(member, right) for member in left.members))
        if isinstance(right, UnionTy):
            return union(*(self.intersect_types(left, member) for member in right.members))
        if self.is_test_subtype(left, right):
            return left
        if self.is_test_subtype(right, left):
            return right

        return NEVER
