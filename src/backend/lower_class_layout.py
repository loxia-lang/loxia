"""Planejamento de layout de classe, campos e inicializadores constantes."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _I8_PTR,
    _INT,
    NUMERIC,
    BackendError,
    Binding,
    ClassLayout,
    FieldLayout,
    FunctionInfo,
    MethodLayout,
    TypeDesc,
    ValueType,
    _unsupported,
)
from src.frontend.expr import Expr, Grouping, Literal, Unary
from src.frontend.stmt import Class, Field, Stmt
from src.frontend.token_type import TokenType


class ClassLayoutLowering(LoweringBase):
    def _predeclare_classes(self, statements: list[Stmt]) -> None:
        classes = [stmt for stmt in statements if isinstance(stmt, Class)]
        self._class_names = {stmt.name.lexeme for stmt in classes} | set(self._classes)

        for index, stmt in enumerate(classes, start=1):
            if stmt.type_params:
                continue
            self._validate_class(stmt)
            super_name, super_layout = self._class_super(stmt)
            self._register_class(stmt, index, super_name, super_layout)

    def _validate_class(self, stmt: Class) -> None:
        if len(stmt.fields) > 64:
            raise BackendError(
                "Classes with more than 64 fields are not supported by the "
                "backend yet.",
                stmt.name.line,
            )

    def _class_super(
        self, stmt: Class
    ) -> tuple[str | None, ClassLayout | None]:
        if stmt.superclass is None:
            return None, None
        super_name = stmt.superclass.name.lexeme
        super_layout = self._classes.get(super_name)
        if super_layout is None:
            raise _unsupported(
                f"Inheritance from '{super_name}'",
                stmt.superclass.name.line,
            )
        return super_name, super_layout

    def _class_fields(
        self, stmt: Class, base_fields: int
    ) -> list[FieldLayout]:
        fields: list[FieldLayout] = []
        for local_index, field in enumerate(stmt.fields):
            fields.append(
                FieldLayout(
                    field.name.lexeme,
                    self._field_desc(field),
                    field.mutable,
                    field.initializer,
                    base_fields + local_index,
                    field.name.line,
                )
            )
        return fields

    def _class_methods(
        self,
        stmt: Class,
        name: str,
        super_layout: ClassLayout | None,
        base_methods: int,
        *,
        ir_name: str | None = None,
        allow_generic: bool = False,
        type_subst: dict[str, Any] | None = None,
    ) -> tuple[
        list[MethodLayout], FunctionInfo | None, MethodLayout | None, int
    ]:
        methods: list[MethodLayout] = []
        init: FunctionInfo | None = None
        init_method: MethodLayout | None = None
        new_methods = 0

        for method in stmt.methods:
            if method.type_params:
                raise _unsupported("Generic method", method.name.line)
            is_init = method.name.lexeme == "init"
            info = self._function_info(
                method,
                llvm_name=f"lox.{ir_name or name}.{method.name.lexeme}",
                this_class=name,
                is_init=is_init,
                allow_generic=allow_generic,
            )
            if type_subst is not None:
                info = replace(info, type_subst=type_subst)
            if not is_init and any(
                param.default is not None for param in method.params
            ):
                raise _unsupported(
                    "Default parameters in methods", method.name.line
                )
            if is_init:
                init = info
                init_method = MethodLayout("init", info, -1, node=method)
                continue

            inherited = (
                super_layout.method(method.name.lexeme)
                if super_layout is not None
                else None
            )
            slot = (
                inherited.index
                if inherited is not None
                else base_methods + new_methods
            )
            if inherited is None:
                new_methods += 1
            methods.append(
                MethodLayout(
                    method.name.lexeme,
                    info,
                    slot,
                    node=method,
                )
            )

        if init_method is None and super_layout is not None:
            init_method = super_layout.init_method
        return methods, init, init_method, new_methods

    def _register_class(
        self,
        stmt: Class,
        index: int,
        super_name: str | None,
        super_layout: ClassLayout | None,
    ) -> None:
        name = stmt.name.lexeme
        base_fields = 0 if super_layout is None else super_layout.field_count()
        base_methods = 0 if super_layout is None else super_layout.vtable_size
        fields = self._class_fields(stmt, base_fields)
        methods, init, init_method, new_methods = self._class_methods(
            stmt, name, super_layout, base_methods
        )
        effective = init
        if effective is None and super_layout is not None:
            effective = super_layout.effective_init()

        instance_type = llvm_ir.literal_struct(
            [_I8_PTR, _INT, *([_INT] * (base_fields + len(fields)))]
        )
        layout = ClassLayout(
            name,
            index,
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
            super_name=super_name,
            super_layout=super_layout,
            init_method=init_method,
            vtable_size=base_methods + new_methods,
            instance_type=instance_type,
        )
        ctor_params = (
            []
            if effective is None
            else [
                self._storage_llvm_type(param)
                for param in effective.fn_sig.params
            ]
        )
        layout.ctor = llvm_ir.declare(
            self.module,
            f"lox.ctor.{name}",
            _I8_PTR,
            ctor_params,
        )
        self._classes[name] = layout

        slot = llvm_ir.global_variable(self.module, f"g.{name}", _I8_PTR)
        self._globals[name] = Binding(
            slot,
            ValueType.CLASS,
            class_name=name,
        )

    def _field_desc(self, field: Field) -> TypeDesc:
        annotated: TypeDesc | None = None
        if field.type_annotation is not None:
            annotated = self._type_desc(field.type_annotation, field.name.line)

        if field.initializer is not None:
            initial = self._const_desc(field.initializer, field.name.line)
            desc = (
                annotated
                if annotated is not None and annotated.optional
                else initial
            )
        elif annotated is not None:
            desc = annotated
        else:
            raise BackendError(
                f"Field '{field.name.lexeme}' needs a type annotation "
                "for the backend.",
                field.name.line,
            )

        if desc.ty is ValueType.NIL:
            raise BackendError(
                "Fields of type Nil are not supported by the backend yet.",
                field.name.line,
            )
        if desc.optional and desc.ty not in (
            ValueType.STRING,
            ValueType.INSTANCE,
            ValueType.CLASS,
        ):
            raise _unsupported("Optional scalar fields", field.name.line)
        return desc

    def _const_desc(self, expr: Expr, line: int) -> TypeDesc:
        if isinstance(expr, Literal):
            value = expr.value
            if value is None:
                return TypeDesc(ValueType.NIL)
            if isinstance(value, bool):
                return TypeDesc(ValueType.BOOL)
            if isinstance(value, int):
                return TypeDesc(ValueType.INT)
            if isinstance(value, float):
                return TypeDesc(ValueType.FLOAT)
            if isinstance(value, str):
                return TypeDesc(ValueType.STRING)
        if isinstance(expr, Grouping):
            return self._const_desc(expr.expression, line)
        if isinstance(expr, Unary) and expr.operator.type is TokenType.MINUS:
            inner = self._const_desc(expr.right, line)
            if inner.ty in NUMERIC:
                return inner

        raise BackendError(
            "Field initializer must be a constant for the backend.", line
        )
