# SPDX-License-Identifier: MIT OR Apache-2.0
"""Monomorfização de funções genéricas (T7).

O checker publica, por nó `Call`, a instanciação concreta que inferiu. O lowering usa
essa instanciação para gerar uma função LLVM por combinação de tipos — sem re-inferir
tipos e sem boxing. Classes genéricas entram no mesmo registro, mas em um módulo próprio
para manter o escopo do T7 explícito.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _I8_PTR,
    _INT,
    BackendError,
    Binding,
    ClassLayout,
    FunctionInfo,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.frontend.expr import Call
from loxia_core.frontend.stmt import Class, Function
from loxia_core.frontend.ty import (
    ClassTy,
    FnTy,
    ListTy,
    MapTy,
    TupleTy,
    Ty,
    TyVar,
    UnionTy,
    display,
)

MAX_GENERIC_FUNCTIONS = 256
MAX_GENERIC_CLASSES = 256
MAX_GENERIC_TYPE_DEPTH = 8
MAX_MANGLED_BYTES = 1024


def _type_depth(ty: Ty) -> int:
    """Profundidade de construtores de tipo (ADR-0063: teto 8)."""
    if isinstance(ty, ClassTy):
        return 1 + max((_type_depth(arg) for arg in ty.args), default=0)
    if isinstance(ty, ListTy):
        return 1 + _type_depth(ty.element)
    if isinstance(ty, MapTy):
        return 1 + max(_type_depth(ty.key), _type_depth(ty.value))
    if isinstance(ty, TupleTy):
        return 1 + max((_type_depth(item) for item in ty.items), default=0)
    if isinstance(ty, UnionTy):
        return max((_type_depth(member) for member in ty.members), default=0)
    if isinstance(ty, FnTy):
        nested = [_type_depth(param) for param in ty.params]
        nested.append(_type_depth(ty.ret))
        return 1 + max(nested, default=0)
    return 0


class MonomorphizationBudget:
    """Teto determinístico de monomorfização (ADR-0063), por compilação."""

    def __init__(
        self,
        *,
        max_functions: int = MAX_GENERIC_FUNCTIONS,
        max_classes: int = MAX_GENERIC_CLASSES,
        max_depth: int = MAX_GENERIC_TYPE_DEPTH,
        max_mangled_bytes: int = MAX_MANGLED_BYTES,
    ) -> None:
        self.max_functions = max_functions
        self.max_classes = max_classes
        self.max_depth = max_depth
        self.max_mangled_bytes = max_mangled_bytes
        self.functions = 0
        self.classes = 0

    def spend_function(
        self,
        type_args: tuple[Ty, ...],
        llvm_name: str,
        line: int | None,
    ) -> None:
        self.functions += 1
        if self.functions > self.max_functions:
            raise _budget_error(
                "Too many generic instantiations "
                f"(limit {self.max_functions}); simplify type arguments.",
                line,
            )
        self._check(type_args, llvm_name, line)

    def spend_class(self, type_args: tuple[Ty, ...], name: str, line: int | None) -> None:
        self.classes += 1
        if self.classes > self.max_classes:
            raise _budget_error(
                "Too many generic class instantiations "
                f"(limit {self.max_classes}); simplify type arguments.",
                line,
            )
        self._check(type_args, name, line)

    def _check(self, type_args: tuple[Ty, ...], name: str, line: int | None) -> None:
        for arg in type_args:
            depth = _type_depth(arg)
            if depth > self.max_depth:
                raise _budget_error(
                    "Generic type nesting is too deep "
                    f"(limit {self.max_depth}); simplify type arguments.",
                    line,
                )
        if len(name.encode("utf-8")) > self.max_mangled_bytes:
            raise _budget_error(
                "Mangled generic name is too long "
                f"(limit {self.max_mangled_bytes} bytes); simplify type arguments.",
                line,
            )


def _budget_error(message: str, line: int | None) -> BackendError:
    return BackendError(message, line, code=Code.BACKEND_BUDGET)


class GenericLowering(LoweringBase):
    def _prepare_generics(self, statements: list[Any]) -> None:
        self._generic_fns = {
            stmt.name.lexeme: stmt
            for stmt in statements
            if isinstance(stmt, Function) and stmt.type_params
        }

    def _prepare_generic_classes(self, statements: list[Any]) -> None:
        self._generic_class_nodes = {
            stmt.name.lexeme: stmt
            for stmt in statements
            if isinstance(stmt, Class) and stmt.type_params
        }
        by_source: dict[str, list[ClassLayout]] = {}
        classes = sorted(
            self.generic_classes,
            key=lambda ty: (ty.name, tuple(display(arg) for arg in ty.args)),
        )
        for class_ty in classes:
            if not class_ty.args or not self._concrete_class_type(class_ty):
                continue
            layout = self._build_generic_class(class_ty)
            by_source.setdefault(class_ty.name, []).append(layout)
        self._generic_class_by_source = by_source

    def _concrete_class_type(self, ty: ClassTy) -> bool:
        for arg in ty.args:
            if isinstance(arg, TyVar):
                return False
            if isinstance(arg, ClassTy):
                if arg.name in self._generic_class_nodes:
                    if not arg.args or not self._concrete_class_type(arg):
                        return False
                elif arg.name not in self._class_names:
                    return False
            if isinstance(arg, FnTy):
                return False
        return True

    def _build_generic_class(self, class_ty: ClassTy) -> ClassLayout:
        key = self._mangled(class_ty.name, class_ty.args)
        existing = self._generic_class_layouts.get(key)
        if existing is not None:
            return existing

        stmt = self._generic_class_nodes.get(class_ty.name)
        if stmt is None:
            raise _unsupported(f"Generic class '{class_ty.name}'", None)

        self.budget.spend_class(class_ty.args, key, stmt.name.line)
        names = [param.lexeme for param in stmt.type_params]
        if len(names) != len(class_ty.args):
            raise BackendError(
                f"Generic class '{class_ty.name}' has the wrong arity.",
                stmt.name.line,
            )
        subst = dict(zip(names, class_ty.args, strict=True))
        saved = self._type_subst
        self._type_subst = subst
        try:
            fields = self._class_fields(stmt, 0)
            methods, init, init_method, new_methods = self._class_methods(
                stmt,
                key,
                None,
                0,
                ir_name=key,
                allow_generic=True,
                type_subst=subst,
            )
        finally:
            self._type_subst = saved

        instance_type = llvm_ir.literal_struct([_I8_PTR, _INT, *([_INT] * len(fields))])
        layout = ClassLayout(
            key,
            len(self._classes) + 1,
            fields,
            methods,
            init,
            init_node=next(
                (method for method in stmt.methods if method.name.lexeme == "init"),
                None,
            ),
            ir_name=key,
            display_name=stmt.display_name or class_ty.name,
            generic=True,
            init_method=init_method,
            vtable_size=new_methods,
            instance_type=instance_type,
            decl_token=stmt.name,
            interfaces=tuple(token.lexeme for token in stmt.implements),
        )
        layout.ctor = llvm_ir.declare(
            self.module,
            f"lox.ctor.{key}",
            _I8_PTR,
            [
                self._param_llvm_type(param)
                for param in (init.fn_sig.params if init is not None else ())
            ],
        )
        self._generic_class_layouts[key] = layout
        self._classes[key] = layout
        self._globals[key] = Binding(
            llvm_ir.global_variable(self.module, f"g.{key}", _I8_PTR),
            ValueType.CLASS,
            class_name=key,
        )
        return layout

    def _class_display(self, class_name: str) -> str:
        layout = self._classes.get(class_name)
        return layout.display if layout is not None else class_name

    def _instantiate_class(self, name: str, args: tuple[Ty, ...], line: int | None) -> TypeDesc:
        return TypeDesc(
            ValueType.INSTANCE,
            class_name=self._mangled(name, args),
        )

    def _subst_ty(self, ty: Ty) -> Ty:
        if isinstance(ty, TyVar):
            return self._type_subst.get(ty.name, ty)
        if isinstance(ty, ClassTy):
            if ty.name in self._type_subst:
                return self._type_subst[ty.name]
            return ClassTy(ty.name, tuple(self._subst_ty(arg) for arg in ty.args))
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self._subst_ty(param) for param in ty.params),
                self._subst_ty(ty.ret),
                ty.min_params,
                ty.variadic,
            )
        if isinstance(ty, ListTy):
            return ListTy(self._subst_ty(ty.element))
        if isinstance(ty, MapTy):
            return MapTy(self._subst_ty(ty.key), self._subst_ty(ty.value))
        if isinstance(ty, TupleTy):
            return TupleTy(tuple(self._subst_ty(item) for item in ty.items))
        if isinstance(ty, UnionTy):
            return UnionTy(tuple(self._subst_ty(member) for member in ty.members))
        return ty

    def _call_generic_lambda(self, callee: Value, expr: Call) -> Value:
        generic = callee.generic
        node = callee.generic_node
        assert generic is not None and node is not None
        mapping: dict[str, Ty] = {}
        for index, parameter in enumerate(generic.fn.params):
            if index >= len(expr.arguments):
                break
            actual = self.types.get(expr.arguments[index])
            if actual is None:
                raise _unsupported("Generic lambda argument type", expr.paren.line)
            if isinstance(parameter, TyVar):
                mapping[parameter.name] = actual
        if any(variable.name not in mapping for variable in generic.type_params):
            raise _unsupported("Generic lambda without type arguments", expr.paren.line)
        saved = self._type_subst
        self._type_subst = {**saved, **mapping}
        try:
            fn_ty = FnTy(
                tuple(self._subst_ty(item) for item in generic.fn.params),
                self._subst_ty(generic.fn.ret),
                generic.fn.min_params,
            )
            key = (id(node), tuple(mapping.values()))
            info = self._generic_fn_cache.get(key)  # type: ignore[arg-type]
            if info is None:
                info = self._lambda_info(node, fn_ty)
                info = replace(info, type_subst=dict(mapping))
                self._generic_fn_cache[key] = info  # type: ignore[index]
                captures = self._make_captures(node)
                self._emit_function(info, node, captures)
                closure = self._build_closure(info, captures, "<lambda>")
                return closure
        finally:
            self._type_subst = saved
        return self._build_closure(info, self._make_captures(node), "<lambda>")

    def _call_generic_class(self, name: str, expr: Call) -> Value:
        layout = None
        ty = self.types.get(expr) or self.generic_class_sites.get(expr)
        if ty is not None:
            ty = self._subst_ty(ty)
        if isinstance(ty, ClassTy) and self._concrete_class_type(ty):
            layout = self._build_generic_class(ty)
            if layout.name not in self._emitted_generic_classes:
                if self._function_ir is self.main:
                    self._emitted_generic_classes.add(layout.name)
                    self._emit_top_level_class(layout)
                else:
                    self._pending_generic_classes.append(layout)
        elif len(self._generic_class_by_source.get(name, [])) == 1:
            layout = self._generic_class_by_source[name][0]
        if layout is None:
            raise _unsupported("Generic class construction", expr.paren.line)

        binding = self._globals[layout.name]
        class_ptr = self._guard_closure(
            self._load_binding(binding),
            layout.display,
            expr.paren.line,
            expr.paren.column,
        )
        arguments = [self._expr(argument) for argument in expr.arguments]
        init = layout.effective_init()
        minimum = 0 if init is None else init.fn_sig.min_params
        maximum = 0 if init is None else len(init.fn_sig.params)
        count = len(arguments)
        if not minimum <= count <= maximum:
            self._poison(
                expr.paren,
                self._arity_message(minimum, maximum, count),
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.INSTANCE)
        if init is not None:
            for index in range(count, maximum):
                default = init.params[index].default
                assert default is not None
                arguments.append(self._expr(default))
            arguments = [
                self._coerce(argument, expected, expr.paren.line)
                for argument, expected in zip(arguments, init.fn_sig.params, strict=True)
            ]
        _ = class_ptr
        self._set_call_site(expr.paren)
        call = self.builder.call(
            layout.ctor,
            [
                self._arg_llvm(argument, param)
                for argument, param in zip(
                    arguments,
                    [] if init is None else init.fn_sig.params,
                    strict=True,
                )
            ],
        )
        return Value(ValueType.INSTANCE, call, class_name=layout.name)

    def _mangled(self, name: str, type_args: tuple[Ty, ...]) -> str:
        parts = []
        for arg in type_args:
            text = display(arg)
            for char in "[](), .":
                text = text.replace(char, "_")
            parts.append(text.strip("_"))
        return name + "$" + "$".join(parts)

    def _generic_subst(self, stmt: Function, type_args: tuple[Ty, ...]) -> dict[str, Ty]:
        names = [param.lexeme for param in stmt.type_params]
        if len(names) != len(type_args):
            raise BackendError(
                f"Generic function '{stmt.name.lexeme}' expected {len(names)} type argument(s).",
                stmt.name.line,
            )
        return dict(zip(names, type_args, strict=True))

    def _generic_function(
        self,
        stmt: Function,
        type_args: tuple[Ty, ...],
        *,
        line: int | None = None,
    ) -> FunctionInfo:
        name = stmt.name.lexeme
        key = (
            name,
            tuple(display(arg) for arg in type_args),
        )
        info = self._generic_fn_cache.get(key)
        if info is not None:
            return info

        llvm_name = f"lox.{name}${'$'.join(display(arg) for arg in type_args)}"
        self.budget.spend_function(
            type_args,
            llvm_name,
            line if line is not None else stmt.name.line,
        )
        subst = self._generic_subst(stmt, type_args)
        saved = self._type_subst
        self._type_subst = subst
        try:
            info = self._function_info(
                stmt,
                llvm_name=llvm_name,
                allow_generic=True,
            )
            info = replace(info, type_subst=subst)
        finally:
            self._type_subst = saved

        # Registra antes de emitir para recursão direta.
        self._generic_fn_cache[key] = info
        self._emit_function(info, stmt, ())
        return info

    def _call_generic(self, stmt: Function, expr: Call) -> Value:
        instance = self.generic_instances.get(expr)
        if instance is None:
            raise _unsupported(
                "A generic call without a checker instantiation",
                expr.paren.line,
            )

        type_args = tuple(self._subst_ty(arg) for arg in instance.type_args)
        if any(self._has_type_var(arg) for arg in type_args):
            raise _unsupported(
                "A generic call inside another generic body",
                expr.paren.line,
            )

        info = self._generic_function(stmt, type_args, line=expr.paren.line)
        arguments = [self._expr(argument) for argument in expr.arguments]
        prepared = self._prepare_call_arguments(
            info.fn_sig, info, arguments, expr.spread, expr.paren
        )
        if prepared is None:
            return self._zero_desc(info.fn_sig.ret)
        arguments = prepared
        self._set_call_site(expr.paren)
        call = self.builder.call(
            info.ir,
            [
                llvm_ir.null_pointer(),
                *[
                    self._arg_llvm(argument, param)
                    for argument, param in zip(arguments, info.fn_sig.params, strict=True)
                ],
            ],
        )
        return Value(
            info.fn_sig.ret.ty,
            call,
            info.fn_sig.ret.fn,
            info.fn_sig.ret.optional,
            info.fn_sig.ret.class_name,
            interface_name=info.fn_sig.ret.interface_name,
        )

    def _has_type_var(self, ty: Ty) -> bool:
        if isinstance(ty, TyVar):
            return True
        if isinstance(ty, (list, tuple)):
            return any(self._has_type_var(item) for item in ty)
        if isinstance(ty, ClassTy):
            return any(self._has_type_var(arg) for arg in ty.args)
        if isinstance(ty, ListTy):
            return self._has_type_var(ty.element)
        if isinstance(ty, MapTy):
            return self._has_type_var(ty.key) or self._has_type_var(ty.value)
        if isinstance(ty, TupleTy):
            return any(self._has_type_var(item) for item in ty.items)
        if isinstance(ty, UnionTy):
            return any(self._has_type_var(member) for member in ty.members)
        if isinstance(ty, FnTy):
            return any(self._has_type_var(param) for param in ty.params) or self._has_type_var(
                ty.ret
            )
        return False
