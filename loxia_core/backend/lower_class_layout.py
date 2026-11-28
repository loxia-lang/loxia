# SPDX-License-Identifier: MIT OR Apache-2.0
"""Planejamento de layout de classe, campos e inicializadores constantes."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
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
    field_words,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.frontend.token_type import TokenType
from loxia_core.thir import (
    TClass,
    TExpr,
    TStmt,
)
from loxia_core.thir import (
    TClassDecl as Class,
)
from loxia_core.thir import (
    TConst as Literal,
)
from loxia_core.thir import (
    TField as Field,
)
from loxia_core.thir import (
    TUnary as Unary,
)


class ClassLayoutLowering(LoweringBase):
    def _predeclare_classes(self, statements: tuple[TStmt, ...]) -> None:
        classes = [stmt.klass for stmt in statements if isinstance(stmt, Class)]
        self._class_names = {klass.name for klass in classes} | set(self._classes)

        for index, klass in enumerate(classes, start=1):
            if klass.type_params:
                continue
            self._validate_class(klass)
            super_name, super_layout = self._class_super(klass)
            self._register_class(klass, index, super_name, super_layout)

    def _validate_class(self, klass: TClass) -> None:
        if len(klass.fields) > 64:
            raise BackendError(
                "Classes with more than 64 fields are not supported by the backend yet.",
                self._class_line(klass),
                code=Code.BACKEND_UNSUPPORTED,
            )

    def _class_line(self, klass: TClass) -> int:
        return self._decl_line(klass.decl)

    def _class_super(self, klass: TClass) -> tuple[str | None, ClassLayout | None]:
        if klass.superclass is None:
            return None, None
        super_name = klass.superclass
        super_layout = self._classes.get(super_name)
        if super_layout is None:
            raise _unsupported(
                f"Inheritance from '{super_name}'",
                self._line(klass.superclass_span),
            )
        return super_name, super_layout

    def _class_fields(self, klass: TClass, base_index: int, base_words: int) -> list[FieldLayout]:
        # Dois contadores diferentes: `index` é o ordinal do campo (bit do bitmap) e
        # continua vindo de `field_count()`; `slot` é a palavra de 8 bytes no struct e
        # vem de `word_count()` (ADR-0145). Confundir as bases é o erro clássico aqui.
        fields: list[FieldLayout] = []
        offset = base_words + 2  # header: descritor da classe + bitmap
        for local_index, field in enumerate(klass.fields):
            desc = self._field_desc(field)
            fields.append(
                FieldLayout(
                    field.name,
                    desc,
                    field.mutable,
                    field.initializer,
                    base_index + local_index,
                    self._line(field.span),
                    self._column(field.span),
                    field.ty,
                    offset,
                )
            )
            offset += 2 if desc.ty is ValueType.ANY else 1
        return fields

    def _class_methods(
        self,
        klass: TClass,
        name: str,
        super_layout: ClassLayout | None,
        base_methods: int,
        *,
        ir_name: str | None = None,
        allow_generic: bool = False,
        type_subst: dict[str, Any] | None = None,
    ) -> tuple[list[MethodLayout], FunctionInfo | None, MethodLayout | None, int]:
        methods: list[MethodLayout] = []
        init: FunctionInfo | None = None
        init_method: MethodLayout | None = None
        new_methods = 0

        for method in klass.methods:
            method_line = self._line(self._decl(method.id).span)
            if method.type_params:
                raise _unsupported("Generic method", method_line)
            is_init = method.is_init
            info = self._function_info(
                method,
                llvm_name=f"lox.{ir_name or name}.{method.name}",
                this_class=name,
                is_init=is_init,
                allow_generic=allow_generic,
            )
            if type_subst is not None:
                info = replace(info, type_subst=type_subst)
            if not is_init and any(param.default is not None for param in method.params):
                raise _unsupported("Default parameters in methods", method_line)
            if is_init:
                init = info
                init_method = MethodLayout("init", info, -1, node=method)
                continue

            inherited = super_layout.method(method.name or "") if super_layout is not None else None
            slot = inherited.index if inherited is not None else base_methods + new_methods
            if inherited is None:
                new_methods += 1
            methods.append(
                MethodLayout(
                    method.name or "",
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
        klass: TClass,
        index: int,
        super_name: str | None,
        super_layout: ClassLayout | None,
    ) -> None:
        name = klass.name
        base_index = 0 if super_layout is None else super_layout.field_count()
        base_words = 0 if super_layout is None else super_layout.word_count()
        base_methods = 0 if super_layout is None else super_layout.vtable_size
        fields = self._class_fields(klass, base_index, base_words)
        methods, init, init_method, new_methods = self._class_methods(
            klass, name, super_layout, base_methods
        )
        effective = init
        if effective is None and super_layout is not None:
            effective = super_layout.effective_init()

        instance_type = llvm_ir.literal_struct(
            [_I8_PTR, _INT, *([_INT] * (base_words + field_words(fields)))]
        )
        layout = ClassLayout(
            name,
            index,
            fields,
            methods,
            init,
            init_node=next(
                (method for method in klass.methods if method.name == "init"),
                None,
            ),
            super_name=super_name,
            super_layout=super_layout,
            init_method=init_method,
            vtable_size=base_methods + new_methods,
            instance_type=instance_type,
            decl_token=self._decl_span(klass.decl),
            display_name=klass.display_name,
            interfaces=klass.interfaces,
        )
        ctor_params = (
            []
            if effective is None
            else [self._param_llvm_type(param) for param in effective.fn_sig.params]
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
        if field.ty is not None:
            annotated = self._type_desc(field.ty, self._line(field.span))

        if field.initializer is not None:
            initial = self._const_desc(field.initializer, self._line(field.span))
            # The annotation is the field type; the initializer only supplies a value
            # (coerced when the constructor runs). Using the initializer's type as the
            # layout would make the slot disagree with the type the checker publishes.
            desc = annotated if annotated is not None else initial
        elif annotated is not None:
            desc = annotated
        else:
            raise BackendError(
                f"Field '{field.name}' needs a type annotation for the backend.",
                self._line(field.span),
                code=Code.BACKEND_UNSUPPORTED,
            )

        if desc.ty is ValueType.NIL:
            raise BackendError(
                "Fields of type Nil are not supported by the backend yet.",
                self._line(field.span),
                code=Code.BACKEND_UNSUPPORTED,
            )
        if desc.optional and desc.ty not in (
            ValueType.STRING,
            ValueType.INSTANCE,
            ValueType.CLASS,
        ):
            raise _unsupported("Optional scalar fields", self._line(field.span))
        return desc

    def _const_desc(self, expr: TExpr, line: int) -> TypeDesc:
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
        if isinstance(expr, Unary) and expr.op is TokenType.MINUS:
            inner = self._const_desc(expr.operand, line)
            if inner.ty in NUMERIC:
                return inner

        raise BackendError(
            "Field initializer must be a constant for the backend.",
            line,
            code=Code.BACKEND_UNSUPPORTED,
        )
