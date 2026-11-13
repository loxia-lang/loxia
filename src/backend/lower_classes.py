"""Classes, instâncias, campos, métodos, herança e vtable do L5 (ADR-0048)."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _BOOL,
    _CLASS_DESC,
    _CLOSURE,
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    NUMERIC,
    BackendError,
    Binding,
    ClassLayout,
    FieldLayout,
    FnSig,
    FunctionInfo,
    MethodLayout,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.frontend.expr import (
    As,
    Expr,
    Get,
    Grouping,
    Is,
    Literal,
    Set,
    Super,
    This,
    Unary,
)
from src.frontend.stmt import Class, Field, Stmt
from src.frontend.token_type import TokenType
from src.frontend.ty import Ty


class ClassLowering(LoweringBase):
    def _predeclare_classes(self, statements: list[Stmt]) -> None:
        classes = [stmt for stmt in statements if isinstance(stmt, Class)]
        self._class_names = {stmt.name.lexeme for stmt in classes}

        for index, stmt in enumerate(classes, start=1):
            name = stmt.name.lexeme
            if stmt.type_params:
                raise _unsupported("Generic class", stmt.name.line)
            if len(stmt.fields) > 64:
                raise BackendError(
                    "Classes with more than 64 fields are not supported by the "
                    "backend yet.",
                    stmt.name.line,
                )

            super_layout: ClassLayout | None = None
            super_name: str | None = None
            if stmt.superclass is not None:
                super_name = stmt.superclass.name.lexeme
                super_layout = self._classes.get(super_name)
                if super_layout is None:
                    raise _unsupported(
                        f"Inheritance from '{super_name}'",
                        stmt.superclass.name.line,
                    )

            base_fields = 0 if super_layout is None else super_layout.field_count()
            base_methods = 0 if super_layout is None else super_layout.vtable_size

            fields: list[FieldLayout] = []
            for local_index, field in enumerate(stmt.fields):
                desc = self._field_desc(field)
                fields.append(
                    FieldLayout(
                        field.name.lexeme,
                        desc,
                        field.mutable,
                        field.initializer,
                        base_fields + local_index,
                        field.name.line,
                    )
                )

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
                    llvm_name=f"lox.{name}.{method.name.lexeme}",
                    this_class=name,
                    is_init=is_init,
                )
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

            slot = llvm_ir.global_variable(
                self.module, f"g.{name}", _I8_PTR
            )
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

    def _class_declaration(self, stmt: Class) -> None:
        if not (self._function_ir is self.main and len(self._scopes) == 1):
            self._local_class_declaration(stmt)
            return

        layout = self._classes[stmt.name.lexeme]
        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, 64)],
        )
        descriptor = self.builder.bitcast(raw, _CLASS_DESC.as_pointer())

        super_ptr: Any = llvm_ir.null_pointer()
        if layout.super_name is not None:
            super_ptr = self.builder.load(
                self._globals[layout.super_name].storage
            )

        vtable_raw: Any = llvm_ir.null_pointer()
        vtable: Any = llvm_ir.null_pointer()
        if layout.vtable_size:
            vtable_raw = self.builder.call(
                self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
                [llvm_ir.constant(_INT, 8 * layout.vtable_size)],
            )
            vtable = self.builder.bitcast(vtable_raw, _I8_PTR.as_pointer())
            if layout.super_layout is not None:
                base_desc = self.builder.bitcast(
                    super_ptr, _CLASS_DESC.as_pointer()
                )
                base_vtable = self.builder.bitcast(
                    self.builder.load(
                        self.builder.gep(
                            base_desc,
                            [
                                llvm_ir.constant(_I32, 0),
                                llvm_ir.constant(_I32, 3),
                            ],
                        )
                    ),
                    _I8_PTR.as_pointer(),
                )
                for slot_index in range(layout.super_layout.vtable_size):
                    slot = self.builder.gep(
                        vtable, [llvm_ir.constant(_I32, slot_index)]
                    )
                    self.builder.store(
                        self.builder.load(
                            self.builder.gep(
                                base_vtable,
                                [llvm_ir.constant(_I32, slot_index)],
                            )
                        ),
                        slot,
                    )

            for method in layout.methods:
                closure = self._make_raw_closure(
                    method.info.ir,
                    llvm_ir.null_pointer(),
                    f"<fn {method.name}>",
                    method.info.fn_sig,
                )
                slot = self.builder.gep(
                    vtable, [llvm_ir.constant(_I32, method.index)]
                )
                self.builder.store(closure.llvm, slot)

        init_closure: Any = llvm_ir.null_pointer()
        if layout.init is not None:
            init_closure = self._make_raw_closure(
                layout.init.ir,
                llvm_ir.null_pointer(),
                "<fn init>",
                layout.init.fn_sig,
            ).llvm
        elif layout.super_name is not None:
            base_desc = self.builder.bitcast(super_ptr, _CLASS_DESC.as_pointer())
            init_closure = self.builder.load(
                self.builder.gep(
                    base_desc,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 5)],
                )
            )

        effective = layout.effective_init()
        name_value = self._string_literal(layout.name)
        init_min = 0 if effective is None else effective.fn_sig.min_params
        init_max = 0 if effective is None else len(effective.fn_sig.params)
        values = [
            super_ptr,
            llvm_ir.constant(_INT, layout.id),
            name_value.llvm,
            vtable_raw,
            llvm_ir.constant(_INT, layout.field_count()),
            init_closure,
            llvm_ir.constant(_INT, init_min),
            llvm_ir.constant(_INT, init_max),
        ]
        for index, value in enumerate(values):
            slot = self.builder.gep(
                descriptor,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
            )
            self.builder.store(value, slot)

        binding = self._globals[layout.name]
        self.builder.store(raw, binding.storage)

        for method in layout.methods:
            assert method.node is not None
            self._emit_function(method.info, method.node, ())
        if layout.init is not None and layout.init_node is not None:
            self._emit_function(layout.init, layout.init_node, ())

        self._emit_ctor(layout)

    def _local_class_declaration(self, stmt: Class) -> None:
        if stmt.fields or stmt.methods or stmt.superclass is not None:
            raise _unsupported(
                "Local classes with fields, methods or inheritance",
                stmt.name.line,
            )
        if stmt.type_params:
            raise _unsupported("Generic local classes", stmt.name.line)

        self._local_class_counter += 1
        key = f"{stmt.name.lexeme}@{self._local_class_counter}"
        instance_type = llvm_ir.literal_struct([_I8_PTR, _INT])
        layout = ClassLayout(
            stmt.name.lexeme,
            len(self._classes) + 1,
            [],
            [],
            None,
            instance_type=instance_type,
        )
        self._classes[key] = layout

        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, 64)],
        )
        descriptor = self.builder.bitcast(raw, _CLASS_DESC.as_pointer())
        name_value = self._string_literal(layout.name)
        values = [
            llvm_ir.null_pointer(),
            llvm_ir.constant(_INT, layout.id),
            name_value.llvm,
            llvm_ir.null_pointer(),
            llvm_ir.constant(_INT, 0),
            llvm_ir.null_pointer(),
            llvm_ir.constant(_INT, 0),
            llvm_ir.constant(_INT, 0),
        ]
        for index, value in enumerate(values):
            slot = self.builder.gep(
                descriptor,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
            )
            self.builder.store(value, slot)

        slot = self.builder.alloca(_I8_PTR, name=stmt.name.lexeme)
        self.builder.store(raw, slot)
        self._scopes[-1][stmt.name.lexeme] = Binding(
            slot,
            ValueType.CLASS,
            class_name=stmt.name.lexeme,
            layout_key=key,
        )

    def _emit_ctor(self, layout: ClassLayout) -> None:
        ctor = layout.ctor
        assert ctor is not None
        assert layout.instance_type is not None

        saved_builder = self.builder
        saved_function = self._function_ir
        saved_return = self._return_type_desc
        saved_in_init = self._in_init
        saved_method_class = self._method_class
        saved_scopes = self._scopes
        saved_captures = self._captures

        self._function_ir = ctor
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._in_init = True
        self._method_class = None
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(ctor, "entry"))

        size = 16 + 8 * layout.field_count()
        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, size)],
        )
        instance = Value(ValueType.INSTANCE, raw, class_name=layout.name)
        struct_ = self.builder.bitcast(raw, layout.instance_type.as_pointer())
        descriptor = self.builder.load(self._globals[layout.name].storage)
        self.builder.store(
            descriptor,
            self.builder.gep(
                struct_,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            ),
        )
        self.builder.store(
            llvm_ir.constant(_INT, 0),
            self.builder.gep(
                struct_,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            ),
        )

        for field in layout.all_fields():
            if field.initializer is None:
                continue
            value = self._coerce(
                self._expr(field.initializer), field.ty, field.line
            )
            self._store_field(instance, field, value)

        effective = layout.effective_init()
        if effective is not None:
            init_args = [ctor.args[index] for index in range(len(ctor.args))]
            self.builder.call(
                effective.ir,
                [
                    llvm_ir.null_pointer(),
                    raw,
                    *init_args,
                ],
            )

        for field in layout.all_fields():
            bitmap = self.builder.load(self._bitmap_slot(instance, field.line))
            mask = llvm_ir.constant(_INT, 1 << field.index)
            present = self.builder.icmp_signed(
                "!=",
                self.builder.and_(bitmap, mask),
                llvm_ir.constant(_INT, 0),
            )
            ok = llvm_ir.append_block(self._function_ir, "init.ok")
            bad = llvm_ir.append_block(self._function_ir, "init.bad")
            self.builder.cbranch(present, ok, bad)

            self.builder = llvm_ir.builder(bad)
            self._poison(
                field.line, f"Field '{field.name}' must be initialized."
            )
            self.builder = llvm_ir.builder(ok)

        self.builder.ret(raw)
        self._seal_blocks(ctor)

        self.builder = saved_builder
        self._function_ir = saved_function
        self._return_type_desc = saved_return
        self._in_init = saved_in_init
        self._method_class = saved_method_class
        self._scopes = saved_scopes
        self._captures = saved_captures

    def _target_class(self, ty: Ty, line: int) -> str:
        target = self._type_desc(ty, line)
        if target.ty is not ValueType.INSTANCE or target.class_name is None:
            raise _unsupported("'is'/'as' for non-class types", line)
        return target.class_name

    def _class_pointer(self, name: str, line: int) -> Any:
        binding = self._globals.get(name)
        if binding is None:
            raise _unsupported(f"Class '{name}'", line)
        return self._guard_closure(
            self._load_binding(binding), name, line
        )

    def _is_instance(self, value: Value, class_name: str, line: int) -> Value:
        if value.ty is ValueType.NIL:
            return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))
        if value.ty is not ValueType.INSTANCE:
            self._poison(line, f"Can't use 'is' on {value.ty.name}.")
            return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))
        struct_ = self._instance_struct(value, line)
        descriptor = self.builder.load(
            self.builder.gep(
                struct_,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            )
        )
        target = self._class_pointer(class_name, line)
        result = self.builder.call(
            self._function("lox_is_instance", _I32, [_I8_PTR, _I8_PTR]),
            [descriptor, target.llvm],
        )
        return Value(
            ValueType.BOOL,
            self.builder.icmp_signed(
                "!=", result, llvm_ir.constant(_I32, 0)
            ),
        )

    def _is_expr(self, expr: Is) -> Value:
        target = self._target_class(expr.test_type, expr.operator.line)
        return self._is_instance(
            self._expr(expr.left), target, expr.operator.line
        )

    def _as_expr(self, expr: As) -> Value:
        target = self._target_class(expr.target_type, expr.operator.line)
        value = self._expr(expr.left)
        if value.optional:
            value = self._unwrap(
                value,
                expr.operator.line,
                f"Can't cast value to {target}.",
            )
        check = self._is_instance(value, target, expr.operator.line)
        ok = llvm_ir.append_block(self._function_ir, "as.ok")
        bad = llvm_ir.append_block(self._function_ir, "as.bad")
        self.builder.cbranch(check.llvm, ok, bad)

        self.builder = llvm_ir.builder(bad)
        self._poison(expr.operator.line, f"Can't cast value to {target}.")

        self.builder = llvm_ir.builder(ok)
        return Value(
            ValueType.INSTANCE,
            value.llvm,
            class_name=value.class_name or target,
        )

    def _this(self, expr: This) -> Value:
        binding = self._find_binding("this")
        if binding is None:
            raise BackendError("'this' outside a method.", expr.keyword.line)
        return self._load_binding(binding)

    def _layout_for(self, value: Value, line: int) -> ClassLayout:
        layout = self._classes.get(value.class_name or "")
        if layout is None:
            raise _unsupported("Class instance", line)
        return layout

    def _instance_struct(self, value: Value, line: int) -> Any:
        layout = self._layout_for(value, line)
        assert layout.instance_type is not None
        return self.builder.bitcast(value.llvm, layout.instance_type.as_pointer())

    def _field_slot(self, value: Value, field: FieldLayout) -> Any:
        struct_ = self._instance_struct(value, field.line)
        return self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, field.index + 2)],
        )

    def _bitmap_slot(self, value: Value, line: int) -> Any:
        struct_ = self._instance_struct(value, line)
        return self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
        )

    def _check_bitmap(
        self, value: Value, field: FieldLayout, line: int, message: str
    ) -> None:
        bitmap = self.builder.load(self._bitmap_slot(value, line))
        mask = llvm_ir.constant(_INT, 1 << field.index)
        present = self.builder.icmp_signed(
            "!=", self.builder.and_(bitmap, mask), llvm_ir.constant(_INT, 0)
        )
        ok = llvm_ir.append_block(self._function_ir, "field.ok")
        bad = llvm_ir.append_block(self._function_ir, "field.nil")
        self.builder.cbranch(present, ok, bad)

        self.builder = llvm_ir.builder(bad)
        self._poison(line, message)

        self.builder = llvm_ir.builder(ok)

    def _set_bitmap(self, value: Value, field: FieldLayout) -> None:
        slot = self._bitmap_slot(value, field.line)
        bitmap = self.builder.load(slot)
        mask = llvm_ir.constant(_INT, 1 << field.index)
        self.builder.store(self.builder.or_(bitmap, mask), slot)

    def _slot_to_value(self, slot: Any, desc: TypeDesc) -> Value:
        raw = self.builder.load(slot)
        match desc.ty:
            case ValueType.INT:
                return Value(ValueType.INT, raw)
            case ValueType.FLOAT:
                return Value(
                    ValueType.FLOAT, self.builder.bitcast(raw, _FLOAT)
                )
            case ValueType.BOOL:
                return Value(ValueType.BOOL, self.builder.trunc(raw, _BOOL))
            case ValueType.STRING:
                return Value(
                    ValueType.STRING,
                    self.builder.inttoptr(raw, _I8_PTR),
                    optional=desc.optional,
                )
            case ValueType.FUNCTION:
                return Value(
                    ValueType.FUNCTION,
                    self.builder.inttoptr(raw, _I8_PTR),
                    desc.fn,
                    desc.optional,
                )
            case ValueType.CLASS | ValueType.INSTANCE:
                return Value(
                    desc.ty,
                    self.builder.inttoptr(raw, _I8_PTR),
                    optional=desc.optional,
                    class_name=desc.class_name,
                )
            case ValueType.NIL:
                return Value(ValueType.NIL)
        raise _unsupported(f"Field type '{desc.ty.name}'", None)

    def _value_to_slot(self, value: Value) -> Any:
        match value.ty:
            case ValueType.INT:
                return value.llvm
            case ValueType.FLOAT:
                return self.builder.bitcast(value.llvm, _INT)
            case ValueType.BOOL:
                return self.builder.zext(value.llvm, _INT)
            case ValueType.STRING | ValueType.FUNCTION | ValueType.CLASS | ValueType.INSTANCE:
                return self.builder.ptrtoint(value.llvm, _INT)
            case ValueType.NIL:
                return llvm_ir.constant(_INT, 0)
        raise _unsupported(f"Field value '{value.ty.name}'", None)

    def _load_field(
        self, instance: Value, field: FieldLayout, line: int
    ) -> Value:
        self._check_bitmap(
            instance,
            field,
            line,
            f"Undefined property '{field.name}'.",
        )
        return self._slot_to_value(self._field_slot(instance, field), field.ty)

    def _store_field(self, instance: Value, field: FieldLayout, value: Value) -> None:
        self.builder.store(
            self._value_to_slot(value), self._field_slot(instance, field)
        )
        self._set_bitmap(instance, field)

    def _make_raw_closure(
        self,
        fnptr: Any,
        env: Any,
        display: str,
        sig: FnSig,
    ) -> Value:
        raw = self.builder.call(
            self._function("lox_alloc_closure", _I8_PTR, []), []
        )
        closure = self.builder.bitcast(raw, _CLOSURE.as_pointer())
        self.builder.store(
            self.builder.bitcast(fnptr, _I8_PTR),
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            ),
        )
        self.builder.store(
            env,
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            ),
        )
        self.builder.store(
            self._display_pointer(display),
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 2)],
            ),
        )
        return Value(ValueType.FUNCTION, raw, sig)

    def _method_thunk(self, layout: ClassLayout, method: MethodLayout) -> Any:
        if method.thunk is not None:
            return method.thunk

        sig = method.info.fn_sig
        result = (
            _VOID
            if sig.ret.ty is ValueType.NIL
            else self._storage_llvm_type(sig.ret)
        )
        thunk = llvm_ir.declare(
            self.module,
            f"lox.bound.{layout.name}.{method.name}",
            result,
            [_I8_PTR, *[self._storage_llvm_type(param) for param in sig.params]],
        )

        saved_builder = self.builder
        saved_function = self._function_ir
        saved_return = self._return_type_desc
        saved_in_init = self._in_init
        saved_scopes = self._scopes
        saved_captures = self._captures

        self._function_ir = thunk
        self._return_type_desc = sig.ret
        self._in_init = False
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(thunk, "entry"))

        bound_type = llvm_ir.literal_struct([_I8_PTR, _I8_PTR])
        bound = self.builder.bitcast(thunk.args[0], bound_type.as_pointer())
        closure_ptr = self.builder.load(
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            )
        )
        this_ptr = self.builder.load(
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            )
        )
        closure = self.builder.bitcast(closure_ptr, _CLOSURE.as_pointer())
        fnptr = self.builder.load(
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            )
        )
        method_env = self.builder.load(
            self.builder.gep(
                closure,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            )
        )
        function_type = llvm_ir.function_pointer(
            result,
            [
                _I8_PTR,
                _I8_PTR,
                *[self._storage_llvm_type(param) for param in sig.params],
            ],
        )
        args = [thunk.args[index + 1] for index in range(len(sig.params))]
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [method_env, this_ptr, *args],
        )
        if sig.ret.ty is ValueType.NIL:
            self.builder.ret_void()
        else:
            self.builder.ret(call)
        self._seal_blocks(thunk)
        method.thunk = thunk

        self.builder = saved_builder
        self._function_ir = saved_function
        self._return_type_desc = saved_return
        self._in_init = saved_in_init
        self._scopes = saved_scopes
        self._captures = saved_captures
        return thunk

    def _bind_method_closure(
        self,
        instance: Value,
        layout: ClassLayout,
        method: MethodLayout,
        method_closure: Any,
    ) -> Value:
        thunk = self._method_thunk(layout, method)
        raw_env = self.builder.call(
            self._function("lox_alloc_env", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, 2)],
        )
        bound_type = llvm_ir.literal_struct([_I8_PTR, _I8_PTR])
        bound = self.builder.bitcast(raw_env, bound_type.as_pointer())
        self.builder.store(
            method_closure,
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
            ),
        )
        self.builder.store(
            instance.llvm,
            self.builder.gep(
                bound,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
            ),
        )
        return self._make_raw_closure(
            thunk, raw_env, f"<fn {method.name}>", method.info.fn_sig
        )

    def _bound_method(
        self, instance: Value, layout: ClassLayout, method: MethodLayout
    ) -> Value:
        struct_ = self._instance_struct(instance, 0)
        descriptor_slot = self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)],
        )
        descriptor = self.builder.load(descriptor_slot)
        desc_struct = self.builder.bitcast(descriptor, _CLASS_DESC.as_pointer())
        vtable_slot = self.builder.gep(
            desc_struct,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 3)],
        )
        vtable = self.builder.bitcast(
            self.builder.load(vtable_slot), _I8_PTR.as_pointer()
        )
        method_slot = self.builder.gep(
            vtable, [llvm_ir.constant(_I32, method.index)]
        )
        method_closure = self.builder.load(method_slot)
        return self._bind_method_closure(
            instance, layout, method, method_closure
        )

    def _this_value(self, line: int) -> Value:
        binding = self._find_binding("this")
        if binding is None:
            raise BackendError("'this' outside a method.", line)
        return self._load_binding(binding)

    def _super_method(self, expr: Super) -> Value:
        if self._method_class is None:
            raise BackendError("'super' outside a method.", expr.keyword.line)
        layout = self._classes[self._method_class]
        base = layout.super_layout
        if base is None:
            raise BackendError("'super' without a superclass.", expr.keyword.line)

        instance = self._this_value(expr.keyword.line)
        name = expr.method.lexeme
        descriptor = self.builder.load(self._globals[base.name].storage)
        desc_struct = self.builder.bitcast(descriptor, _CLASS_DESC.as_pointer())

        if name == "init":
            method = base.init_method
            if method is None:
                raise BackendError("Superclass has no initializer.", expr.keyword.line)
            closure = self.builder.load(
                self.builder.gep(
                    desc_struct,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 5)],
                )
            )
        else:
            method = base.method(name)
            if method is None:
                raise BackendError(
                    f"Undefined property '{name}'.", expr.method.line
                )
            vtable = self.builder.bitcast(
                self.builder.load(
                    self.builder.gep(
                        desc_struct,
                        [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 3)],
                    )
                ),
                _I8_PTR.as_pointer(),
            )
            closure = self.builder.load(
                self.builder.gep(
                    vtable, [llvm_ir.constant(_I32, method.index)]
                )
            )

        return self._bind_method_closure(instance, base, method, closure)

    def _get(self, expr: Get) -> Value:
        obj = self._expr(expr.object)
        if expr.optional:
            if obj.ty is ValueType.NIL:
                return self._zero_desc(
                    self._expr_type_desc(expr, expr.name.line)
                )
            if obj.optional:
                return self._get_optional(obj, expr)

        return self._get_instance(obj, expr)

    def _get_optional(self, obj: Value, expr: Get) -> Value:
        result = self._expr_type_desc(expr, expr.name.line)
        if not result.optional:
            result = TypeDesc(
                result.ty, result.fn, True, result.class_name
            )

        some = llvm_ir.append_block(self._function_ir, "get.some")
        nothing = llvm_ir.append_block(self._function_ir, "get.nil")
        end = llvm_ir.append_block(self._function_ir, "get.end")
        tag = self._optional_tag(obj)
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(some)
        payload = self._optional_payload(obj)
        value = self._coerce(
            self._get_instance(payload, expr), result, expr.name.line
        )
        self.builder.branch(end)
        some_end = self.builder.block

        self.builder = llvm_ir.builder(nothing)
        zero = self._zero_desc(result)
        self.builder.branch(end)
        nothing_end = self.builder.block

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(
            self._storage_llvm_type(result), "get.value"
        )
        merged.add_incoming(value.llvm, some_end)
        merged.add_incoming(zero.llvm, nothing_end)
        return Value(
            result.ty,
            merged,
            result.fn,
            True,
            result.class_name,
        )

    def _get_instance(self, obj: Value, expr: Get) -> Value:
        if obj.ty is not ValueType.INSTANCE:
            self._poison(expr.name.line, "Only instances have properties.")
            return self._zero(ValueType.INT)

        layout = self._layout_for(obj, expr.name.line)
        field = layout.field(expr.name.lexeme)
        if field is not None:
            return self._load_field(obj, field, expr.name.line)
        method = layout.method(expr.name.lexeme)
        if method is not None:
            return self._bound_method(obj, layout, method)

        self._poison(
            expr.name.line, f"Undefined property '{expr.name.lexeme}'."
        )
        return self._zero(ValueType.INT)

    def _set(self, expr: Set) -> Value:
        obj = self._expr(expr.object)
        value = self._expr(expr.value)
        if obj.ty is not ValueType.INSTANCE:
            self._poison(expr.name.line, "Only instances have fields.")
            return value

        layout = self._layout_for(obj, expr.name.line)
        field = layout.field(expr.name.lexeme)
        if field is None:
            self._poison(expr.name.line, f"Undefined field '{expr.name.lexeme}'.")
            return value

        value = self._coerce(value, field.ty, expr.name.line)

        if not field.mutable:
            if not self._in_init:
                self._poison(
                    expr.name.line,
                    f"Can't assign to immutable field '{field.name}'.",
                )
                return value
            bitmap = self.builder.load(self._bitmap_slot(obj, field.line))
            mask = llvm_ir.constant(_INT, 1 << field.index)
            already = self.builder.icmp_signed(
                "!=",
                self.builder.and_(bitmap, mask),
                llvm_ir.constant(_INT, 0),
            )
            fresh = llvm_ir.append_block(self._function_ir, "val.fresh")
            used = llvm_ir.append_block(self._function_ir, "val.used")
            end = llvm_ir.append_block(self._function_ir, "val.end")
            self.builder.cbranch(already, used, fresh)

            self.builder = llvm_ir.builder(used)
            self._poison(
                expr.name.line,
                f"Can't assign to immutable field '{field.name}'.",
            )
            self.builder = llvm_ir.builder(fresh)
            self._store_field(obj, field, value)
            self.builder.branch(end)

            self.builder = llvm_ir.builder(end)
            return value

        self._store_field(obj, field, value)
        return value
