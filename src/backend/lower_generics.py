"""Monomorfização de funções genéricas (T7).

O checker publica, por nó `Call`, a instanciação concreta que inferiu. O lowering usa
essa instanciação para gerar uma função LLVM por combinação de tipos — sem re-inferir
tipos e sem boxing. Classes genéricas entram no mesmo registro, mas em um módulo próprio
para manter o escopo do T7 explícito.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
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
from src.diagnostics.codes import Code
from src.frontend.expr import Call
from src.frontend.stmt import Class, Function
from src.frontend.ty import ClassTy, FnTy, Ty, TyVar, display


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

        instance_type = llvm_ir.literal_struct(
            [_I8_PTR, _INT, *([_INT] * len(fields))]
        )
        layout = ClassLayout(
            key,
            len(self._classes) + 1,
            fields,
            methods,
            init,
            init_node=next(
                (
                    method
                    for method in stmt.methods
                    if method.name.lexeme == "init"
                ),
                None,
            ),
            ir_name=key,
            display_name=class_ty.name,
            generic=True,
            init_method=init_method,
            vtable_size=new_methods,
            instance_type=instance_type,
        )
        layout.ctor = llvm_ir.declare(
            self.module,
            f"lox.ctor.{key}",
            _I8_PTR,
            [
                self._storage_llvm_type(param)
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

    def _instantiate_class(
        self, name: str, args: tuple[Ty, ...], line: int | None
    ) -> TypeDesc:
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
            return ClassTy(
                ty.name, tuple(self._subst_ty(arg) for arg in ty.args)
            )
        if isinstance(ty, FnTy):
            return FnTy(
                tuple(self._subst_ty(param) for param in ty.params),
                self._subst_ty(ty.ret),
                ty.min_params,
            )
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
        if isinstance(ty, ClassTy):
            layout = self._build_generic_class(ty)
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
                for argument, expected in zip(
                    arguments, init.fn_sig.params, strict=True
                )
            ]
        _ = class_ptr
        call = self.builder.call(
            layout.ctor, [argument.llvm for argument in arguments]
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

    def _generic_subst(
        self, stmt: Function, type_args: tuple[Ty, ...]
    ) -> dict[str, Ty]:
        names = [param.lexeme for param in stmt.type_params]
        if len(names) != len(type_args):
            raise BackendError(
                f"Generic function '{stmt.name.lexeme}' expected "
                f"{len(names)} type argument(s).",
                stmt.name.line,
            )
        return dict(zip(names, type_args, strict=True))

    def _generic_function(
        self, stmt: Function, type_args: tuple[Ty, ...]
    ) -> FunctionInfo:
        name = stmt.name.lexeme
        key = (
            name,
            tuple(display(arg) for arg in type_args),
        )
        info = self._generic_fn_cache.get(key)
        if info is not None:
            return info

        subst = self._generic_subst(stmt, type_args)
        saved = self._type_subst
        self._type_subst = subst
        try:
            info = self._function_info(
                stmt,
                llvm_name=f"lox.{name}${'$'.join(display(arg) for arg in type_args)}",
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

        type_args = tuple(
            self._subst_ty(arg) for arg in instance.type_args
        )
        if any(self._has_type_var(arg) for arg in type_args):
            raise _unsupported(
                "A generic call inside another generic body",
                expr.paren.line,
            )

        info = self._generic_function(stmt, type_args)
        arguments = [self._expr(argument) for argument in expr.arguments]
        minimum = info.fn_sig.min_params
        maximum = len(info.fn_sig.params)
        count = len(arguments)
        if not minimum <= count <= maximum:
            self._poison(
                expr.paren,
                self._arity_message(minimum, maximum, count),
                code=Code.RUNTIME_ARITY,
            )
            return self._zero_desc(info.fn_sig.ret)

        for index in range(count, maximum):
            default = info.params[index].default
            assert default is not None
            arguments.append(self._expr(default))
        arguments = [
            self._coerce(argument, expected, expr.paren.line)
            for argument, expected in zip(
                arguments, info.fn_sig.params, strict=True
            )
        ]
        call = self.builder.call(
            info.ir,
            [llvm_ir.null_pointer(), *[argument.llvm for argument in arguments]],
        )
        return Value(
            info.fn_sig.ret.ty,
            call,
            info.fn_sig.ret.fn,
            info.fn_sig.ret.optional,
            info.fn_sig.ret.class_name,
        )

    def _has_type_var(self, ty: Ty) -> bool:
        if isinstance(ty, TyVar):
            return True
        if isinstance(ty, (list, tuple)):
            return any(self._has_type_var(item) for item in ty)
        return False
