"""Emissão de classes, construtores, vtable, bound methods, `super` e `is`/`as`."""

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
    ANY_TAG_FLOAT,
    ANY_TAG_INT,
    BackendError,
    Binding,
    ClassLayout,
    FnSig,
    MethodLayout,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.diagnostics.codes import Code
from src.frontend.expr import As, Is, Super, This
from src.frontend.stmt import Class
from src.frontend.ty import ANY as TY_ANY
from src.frontend.ty import (
    BOOL as TY_BOOL,
)
from src.frontend.ty import (
    FLOAT as TY_FLOAT,
)
from src.frontend.ty import (
    INT as TY_INT,
)
from src.frontend.ty import (
    NEVER as TY_NEVER,
)
from src.frontend.ty import (
    NIL as TY_NIL,
)
from src.frontend.ty import (
    RANGE as TY_RANGE,
)
from src.frontend.ty import (
    STRING as TY_STRING,
)
from src.frontend.ty import (
    ClassObjectTy,
    ClassTy,
    EnumTy,
    FnTy,
    ListTy,
    MapTy,
    NativeFnTy,
    TupleTy,
    Ty,
    TyVar,
    UnionTy,
    display,
)


class ClassCodegenLowering(LoweringBase):
    def _class_declaration(self, stmt: Class) -> None:
        if not (self._function_ir is self.main and len(self._scopes) == 1):
            self._local_class_declaration(stmt)
            return
        if stmt.type_params:
            for layout in self._generic_class_by_source.get(
                stmt.name.lexeme, []
            ):
                self._emit_top_level_class(layout)
            return
        self._emit_top_level_class(self._classes[stmt.name.lexeme])

    def _emit_top_level_class(self, layout: ClassLayout) -> None:
        raw, descriptor = self._new_class_descriptor()
        super_ptr = self._class_super_pointer(layout)
        vtable_raw = self._class_vtable(layout, super_ptr)
        init_closure = self._class_init_closure(layout, super_ptr)
        self._store_class_descriptor(
            layout,
            descriptor,
            super_ptr,
            vtable_raw,
            init_closure,
        )

        self.builder.store(raw, self._globals[layout.name].storage)
        self._emit_class_methods(layout)
        self._emit_ctor(layout)

    def _new_class_descriptor(self) -> tuple[Any, Any]:
        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, 64)],
        )
        return raw, self.builder.bitcast(raw, _CLASS_DESC.as_pointer())

    def _class_super_pointer(self, layout: ClassLayout) -> Any:
        if layout.super_name is None:
            return llvm_ir.null_pointer()
        return self.builder.load(self._globals[layout.super_name].storage)

    def _class_vtable(self, layout: ClassLayout, super_ptr: Any) -> Any:
        if not layout.vtable_size:
            return llvm_ir.null_pointer()

        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, 8 * layout.vtable_size)],
        )
        vtable = self.builder.bitcast(raw, _I8_PTR.as_pointer())
        if layout.super_layout is not None:
            self._copy_base_vtable(layout.super_layout, super_ptr, vtable)
        for method in layout.methods:
            assert method.node is not None
            closure = self._build_closure(
                method.info,
                self._make_captures(method.node),
                f"<fn {method.name}>",
            )
            slot = self.builder.gep(
                vtable, [llvm_ir.constant(_I32, method.index)]
            )
            self.builder.store(closure.llvm, slot)
        return raw

    def _copy_base_vtable(
        self, super_layout: ClassLayout, super_ptr: Any, vtable: Any
    ) -> None:
        base_desc = self.builder.bitcast(super_ptr, _CLASS_DESC.as_pointer())
        base_vtable = self.builder.bitcast(
            self.builder.load(
                self.builder.gep(
                    base_desc,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 3)],
                )
            ),
            _I8_PTR.as_pointer(),
        )
        for slot_index in range(super_layout.vtable_size):
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

    def _class_init_closure(self, layout: ClassLayout, super_ptr: Any) -> Any:
        if layout.init is not None:
            assert layout.init_node is not None
            return self._build_closure(
                layout.init,
                self._make_captures(layout.init_node),
                "<fn init>",
            ).llvm
        if layout.super_name is None:
            return llvm_ir.null_pointer()
        base_desc = self.builder.bitcast(super_ptr, _CLASS_DESC.as_pointer())
        return self.builder.load(
            self.builder.gep(
                base_desc,
                [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 5)],
            )
        )

    def _store_class_descriptor(
        self,
        layout: ClassLayout,
        descriptor: Any,
        super_ptr: Any,
        vtable_raw: Any,
        init_closure: Any,
    ) -> None:
        effective = layout.effective_init()
        name_value = self._string_literal(layout.display)
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

    def _emit_class_methods(self, layout: ClassLayout) -> None:
        for method in layout.methods:
            assert method.node is not None
            self._emit_function(
                method.info,
                method.node,
                self._make_captures(method.node),
            )
        if layout.init is not None and layout.init_node is not None:
            self._emit_function(
                layout.init,
                layout.init_node,
                self._make_captures(layout.init_node),
            )

    def _local_class_declaration(self, stmt: Class) -> None:
        if stmt.type_params:
            raise _unsupported("Generic local classes", stmt.name.line)
        if stmt.superclass is not None:
            raise _unsupported("Local class inheritance", stmt.name.line)

        name = stmt.name.lexeme
        if (stmt.fields or stmt.methods) and name in self._classes:
            raise _unsupported(
                "A local class shadowing another class with fields or methods",
                stmt.name.line,
            )

        self._local_class_counter += 1
        key = f"{name}@{self._local_class_counter}"
        fields = self._class_fields(stmt, 0)
        methods, init, init_method, new_methods = self._class_methods(
            stmt, name, None, 0, ir_name=key
        )
        instance_type = llvm_ir.literal_struct(
            [_I8_PTR, _INT, *([_INT] * len(fields))]
        )
        layout = ClassLayout(
            name,
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
            local=True,
            ir_name=key,
            init_method=init_method,
            vtable_size=new_methods,
            instance_type=instance_type,
        )
        effective = init
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
            f"lox.ctor.{key}",
            _I8_PTR,
            [_I8_PTR, *ctor_params],
        )
        self._classes[key] = layout
        if name not in self._classes:
            self._classes[name] = layout

        raw, descriptor = self._new_class_descriptor()
        if self._analysis.is_captured(stmt):
            cell = self._alloc_cell()
            self.builder.store(raw, self._cell_pointer(cell, TypeDesc(ValueType.CLASS)))
            self._scopes[-1][name] = Binding(
                cell,
                ValueType.CLASS,
                cell=True,
                class_name=name,
                layout_key=key,
            )
        else:
            slot = self.builder.alloca(_I8_PTR, name=name)
            self.builder.store(raw, slot)
            self._scopes[-1][name] = Binding(
                slot,
                ValueType.CLASS,
                class_name=name,
                layout_key=key,
            )

        vtable = self._class_vtable(layout, llvm_ir.null_pointer())
        init_closure = self._class_init_closure(
            layout, llvm_ir.null_pointer()
        )
        self._store_class_descriptor(
            layout,
            descriptor,
            llvm_ir.null_pointer(),
            vtable,
            init_closure,
        )

        self._emit_class_methods(layout)
        self._emit_ctor(layout)

    def _emit_ctor(self, layout: ClassLayout) -> None:
        ctor = layout.ctor
        assert ctor is not None
        assert layout.instance_type is not None

        saved = (
            self.builder,
            self._function_ir,
            self._return_type_desc,
            self._in_init,
            self._method_class,
            self._scopes,
            self._captures,
        )
        self._function_ir = ctor
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._in_init = True
        self._method_class = None
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(ctor, "entry"))

        self._ctor_body(layout, ctor)
        self._seal_blocks(ctor)

        (
            self.builder,
            self._function_ir,
            self._return_type_desc,
            self._in_init,
            self._method_class,
            self._scopes,
            self._captures,
        ) = saved

    def _ctor_body(self, layout: ClassLayout, ctor: Any) -> None:
        descriptor = ctor.args[0] if layout.local else None
        instance = self._ctor_allocate(layout, descriptor)
        if layout.synthetic_exception:
            field = layout.field("message")
            assert field is not None
            self._store_field(
                instance, field, Value(ValueType.STRING, ctor.args[0])
            )
            self._ctor_require_fields(layout, instance)
            self.builder.ret(instance.llvm)
            return
        self._ctor_run_initializers(layout, instance)
        effective = layout.effective_init()
        if effective is not None:
            offset = 1 if layout.local else 0
            self.builder.call(
                effective.ir,
                [
                    llvm_ir.null_pointer(),
                    instance.llvm,
                    *[
                        ctor.args[index]
                        for index in range(offset, len(ctor.args))
                    ],
                ],
            )
        self._ctor_require_fields(layout, instance)
        self.builder.ret(instance.llvm)

    def _ctor_allocate(
        self, layout: ClassLayout, descriptor: Any = None
    ) -> Value:
        assert layout.instance_type is not None
        size = 16 + 8 * layout.field_count()
        raw = self.builder.call(
            self._function("lox_alloc_bytes", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, size)],
        )
        instance = Value(ValueType.INSTANCE, raw, class_name=layout.name)
        struct_ = self.builder.bitcast(raw, layout.instance_type.as_pointer())
        if descriptor is None:
            descriptor = self.builder.load(
                self._globals[layout.name].storage
            )
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
        return instance

    def _ctor_run_initializers(
        self, layout: ClassLayout, instance: Value
    ) -> None:
        for field in layout.all_fields():
            if field.initializer is None:
                continue
            value = self._coerce(
                self._expr(field.initializer), field.ty, field.line
            )
            self._store_field(instance, field, value)

    def _ctor_require_fields(
        self, layout: ClassLayout, instance: Value
    ) -> None:
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
                field.line,
                f"Field '{field.name}' must be initialized.",
                column=field.column,
                code=Code.FIELD_NOT_INITIALIZED,
            )
            self.builder = llvm_ir.builder(ok)

    def _target_class(self, ty: Ty, line: int) -> str:
        target = self._type_desc(ty, line)
        if target.ty is not ValueType.INSTANCE or target.class_name is None:
            raise _unsupported("'is'/'as' for non-class types", line)
        return target.class_name

    def _class_pointer(self, name: str, line: int, column: int = 0) -> Any:
        binding = self._globals.get(name)
        if binding is None:
            raise _unsupported(f"Class '{name}'", line)
        return self._guard_closure(
            self._load_binding(binding), name, line, column
        )

    def _is_instance(
        self, value: Value, class_name: str, line: int, column: int = 0
    ) -> Value:
        if value.ty is ValueType.NIL:
            return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))
        if value.ty is not ValueType.INSTANCE:
            self._poison(
                line,
                f"Can't use 'is' on {value.ty.name}.",
                column=column,
            )
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
        target_desc = self._type_desc(expr.test_type, expr.operator.line)
        value = self._expr(expr.left)
        if isinstance(expr.test_type, UnionTy):
            if any(member is TY_ANY for member in expr.test_type.members):
                return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 1))
            boxed = self._box_value(value, expr.operator.line)
            result = llvm_ir.constant(_BOOL, 0)
            for member in expr.test_type.members:
                member_desc = self._type_desc(member, expr.operator.line)
                check = self._is_any(
                    boxed, member, member_desc, expr.operator.line
                )
                result = self.builder.or_(result, check.llvm)
            return Value(ValueType.BOOL, result)
        if value.ty is ValueType.ANY:
            return self._is_any(
                value, expr.test_type, target_desc, expr.operator.line
            )
        if isinstance(expr.test_type, (TupleTy, ListTy, MapTy)):
            if value.optional:
                raise _unsupported(
                    "is on an optional container", expr.operator.line
                )
            boxed = self._box_value(value, expr.operator.line)
            return self._is_any(
                boxed, expr.test_type, target_desc, expr.operator.line
            )
        if isinstance(expr.test_type, EnumTy) or (
            isinstance(expr.test_type, ClassTy)
            and expr.test_type.name in self._enum_layouts
        ):
            if value.optional:
                raise _unsupported("is on an optional enum", expr.operator.line)
            boxed = self._box_value(value, expr.operator.line)
            return self._is_any(
                boxed, expr.test_type, target_desc, expr.operator.line
            )
        target = self._target_class(expr.test_type, expr.operator.line)
        return self._is_instance(
            value, target, expr.operator.line, expr.operator.column
        )

    def _is_any(self, value: Value, test_type: Ty, target: TypeDesc, line: int) -> Value:
        """`Any is T` com checagem recursiva (listas, mapas, tuplas, enums).

        O tipo alvo é serializado (`_type_text`) e o matcher C percorre o valor;
        a checagem de tag sozinha deixava `["a"] is List[Int]` passar.
        """
        tag = self.builder.extract_value(value.llvm, 0)
        payload = self.builder.extract_value(value.llvm, 1)
        text = self._type_text(test_type, line)
        result = self.builder.call(
            self._function(
                "lox_type_matches_str", _I32, [_INT, _INT, _I8_PTR]
            ),
            [tag, payload, self._cstring_pointer(text)],
        )
        return Value(
            ValueType.BOOL,
            self.builder.icmp_signed(
                "!=", result, llvm_ir.constant(_I32, 0)
            ),
        )

    def _type_text(self, ty: Ty, line: int) -> str:
        if ty is TY_ANY:
            return "A"
        if ty is TY_NEVER:
            return "X"
        if ty is TY_NIL:
            return "N"
        if ty is TY_BOOL:
            return "B"
        if ty is TY_INT:
            return "I"
        if ty is TY_FLOAT:
            return "F"
        if ty is TY_STRING:
            return "S"
        if ty is TY_RANGE:
            return "R"
        if isinstance(ty, ListTy):
            return f"L<{self._type_text(ty.element, line)}>"
        if isinstance(ty, MapTy):
            return (
                f"M<{self._type_text(ty.key, line)},"
                f"{self._type_text(ty.value, line)}>"
            )
        if isinstance(ty, TupleTy):
            items = ",".join(self._type_text(item, line) for item in ty.items)
            return f"T<{items}>"
        if isinstance(ty, UnionTy):
            members = "|".join(
                self._type_text(member, line) for member in ty.members
            )
            return f"U<{members}>"
        if isinstance(ty, EnumTy):
            layout = self._enum_layouts.get(ty.name)
            if layout is None:
                raise _unsupported(f"Enum '{ty.name}'", line)
            return f"E<{layout.enum_id}>"
        if isinstance(ty, ClassTy):
            if ty.name in self._enum_layouts:
                return f"E<{self._enum_layouts[ty.name].enum_id}>"
            if ty.args:
                raise _unsupported("Class type arguments in is/as", line)
            layout = self._classes.get(ty.name)
            if layout is None:
                raise _unsupported(f"Class '{ty.name}'", line)
            return f"C<{layout.id}>"
        if isinstance(ty, TyVar):
            mapped = self._type_subst.get(ty.name)
            if mapped is None:
                raise _unsupported(
                    f"Unbound type parameter '{ty.name}'", line
                )
            return self._type_text(mapped, line)
        if isinstance(ty, (FnTy, NativeFnTy, ClassObjectTy)):
            return "X"
        raise _unsupported(f"Type '{ty}'", line)

    def _tag_of(self, desc: TypeDesc) -> int:
        from src.backend.lower_model import (
            ANY_TAG_BOOL,
            ANY_TAG_CLASS,
            ANY_TAG_ENUM,
            ANY_TAG_FLOAT,
            ANY_TAG_FUNCTION,
            ANY_TAG_INSTANCE,
            ANY_TAG_INT,
            ANY_TAG_LIST,
            ANY_TAG_MAP,
            ANY_TAG_NIL,
            ANY_TAG_RANGE,
            ANY_TAG_STRING,
            ANY_TAG_TUPLE,
        )

        return {
            ValueType.INT: ANY_TAG_INT,
            ValueType.FLOAT: ANY_TAG_FLOAT,
            ValueType.BOOL: ANY_TAG_BOOL,
            ValueType.STRING: ANY_TAG_STRING,
            ValueType.NIL: ANY_TAG_NIL,
            ValueType.CLASS: ANY_TAG_CLASS,
            ValueType.INSTANCE: ANY_TAG_INSTANCE,
            ValueType.FUNCTION: ANY_TAG_FUNCTION,
            ValueType.RANGE: ANY_TAG_RANGE,
            ValueType.LIST: ANY_TAG_LIST,
            ValueType.MAP: ANY_TAG_MAP,
            ValueType.TUPLE: ANY_TAG_TUPLE,
            ValueType.ENUM: ANY_TAG_ENUM,
        }[desc.ty]

    def _as_any(self, expr: As, value: Value, target_desc: TypeDesc) -> Value:
        """`Any as T`: checa a tag antes de extrair o payload (ADR-0075).

        O tree-walk levanta `R1011` quando o valor não satisfaz `T`; sem a checagem o
        binário reinterpretava o payload e imprimia lixo. `Int`/`Float` aceitam a
        promoção numérica, como no interpretador.
        """
        if target_desc.ty is ValueType.ANY:
            return value
        line = expr.operator.line
        column = expr.operator.column
        if target_desc.ty is ValueType.INT:
            return self._as_any_int(expr, value, line, column)
        if target_desc.ty is ValueType.FLOAT:
            return self._as_any_float(expr, value, line, column)

        matches = self._is_any(value, expr.target_type, target_desc, line)
        ok = llvm_ir.append_block(self._function_ir, "as.ok")
        bad = llvm_ir.append_block(self._function_ir, "as.bad")
        self.builder.cbranch(matches.llvm, ok, bad)
        self.builder = llvm_ir.builder(bad)
        self._poison(
            expr.operator,
            f"Can't cast value to {display(expr.target_type)}.",
            code=Code.RUNTIME_CAST,
        )
        self.builder = llvm_ir.builder(ok)
        return self._unbox_any(value, target_desc, line)

    def _as_any_int(
        self, expr: As, value: Value, line: int, column: int
    ) -> Value:
        tag = self.builder.extract_value(value.llvm, 0)
        payload = self.builder.extract_value(value.llvm, 1)
        is_int = self.builder.icmp_signed(
            "==", tag, llvm_ir.constant(_INT, ANY_TAG_INT)
        )
        is_float = self.builder.icmp_signed(
            "==", tag, llvm_ir.constant(_INT, ANY_TAG_FLOAT)
        )
        int_ok = llvm_ir.append_block(self._function_ir, "as.int")
        float_check = llvm_ir.append_block(self._function_ir, "as.float?")
        float_ok = llvm_ir.append_block(self._function_ir, "as.float")
        bad = llvm_ir.append_block(self._function_ir, "as.bad")
        end = llvm_ir.append_block(self._function_ir, "as.end")

        self.builder.cbranch(is_int, int_ok, float_check)
        self.builder = llvm_ir.builder(float_check)
        self.builder.cbranch(is_float, float_ok, bad)

        self.builder = llvm_ir.builder(int_ok)
        int_value = Value(ValueType.INT, payload)
        self.builder.branch(end)

        self.builder = llvm_ir.builder(float_ok)
        converted = self.builder.call(
            self._function("lox_float_to_int", _INT, [_FLOAT, _I32, _I32]),
            [
                self.builder.bitcast(payload, _FLOAT),
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        self.builder.branch(end)

        self.builder = llvm_ir.builder(bad)
        self._poison(
            expr.operator, "Can't cast value to Int.", code=Code.RUNTIME_CAST
        )

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(_INT, "as.int")
        merged.add_incoming(int_value.llvm, int_ok)
        merged.add_incoming(converted, float_ok)
        return Value(ValueType.INT, merged)

    def _as_any_float(
        self, expr: As, value: Value, line: int, column: int
    ) -> Value:
        tag = self.builder.extract_value(value.llvm, 0)
        payload = self.builder.extract_value(value.llvm, 1)
        is_int = self.builder.icmp_signed(
            "==", tag, llvm_ir.constant(_INT, ANY_TAG_INT)
        )
        is_float = self.builder.icmp_signed(
            "==", tag, llvm_ir.constant(_INT, ANY_TAG_FLOAT)
        )
        int_ok = llvm_ir.append_block(self._function_ir, "as.int")
        float_check = llvm_ir.append_block(self._function_ir, "as.float?")
        float_ok = llvm_ir.append_block(self._function_ir, "as.float")
        bad = llvm_ir.append_block(self._function_ir, "as.bad")
        end = llvm_ir.append_block(self._function_ir, "as.end")

        self.builder.cbranch(is_int, int_ok, float_check)
        self.builder = llvm_ir.builder(float_check)
        self.builder.cbranch(is_float, float_ok, bad)

        self.builder = llvm_ir.builder(int_ok)
        promoted = self.builder.sitofp(payload, _FLOAT)
        self.builder.branch(end)

        self.builder = llvm_ir.builder(float_ok)
        converted = self.builder.bitcast(payload, _FLOAT)
        self.builder.branch(end)

        self.builder = llvm_ir.builder(bad)
        self._poison(
            expr.operator, "Can't cast value to Float.", code=Code.RUNTIME_CAST
        )

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(_FLOAT, "as.float")
        merged.add_incoming(promoted, int_ok)
        merged.add_incoming(converted, float_ok)
        return Value(ValueType.FLOAT, merged)

    def _as_expr(self, expr: As) -> Value:
        target_desc = self._type_desc(expr.target_type, expr.operator.line)
        value = self._expr(expr.left)
        if value.ty is ValueType.ANY:
            return self._as_any(expr, value, target_desc)
        if target_desc.ty in (ValueType.INT, ValueType.FLOAT):
            value = self._expr(expr.left)
            if value.optional:
                value = self._unwrap(
                    value, expr.operator.line, "Can't cast value to Int."
                )
            if target_desc.ty is ValueType.FLOAT:
                if value.ty is ValueType.FLOAT:
                    return value
                if value.ty is ValueType.INT:
                    return Value(
                        ValueType.FLOAT, self.builder.sitofp(value.llvm, _FLOAT)
                    )
                self._poison(
                    expr.operator, "Can't cast value to Float.", code=Code.RUNTIME_CAST
                )
                return Value(ValueType.FLOAT, llvm_ir.float_constant(0.0))
            if value.ty is ValueType.INT:
                return value
            if value.ty is ValueType.FLOAT:
                call = self.builder.call(
                    self._function(
                        "lox_float_to_int", _INT, [_FLOAT, _I32, _I32]
                    ),
                    [
                        value.llvm,
                        llvm_ir.constant(_I32, expr.operator.line),
                        llvm_ir.constant(_I32, expr.operator.column),
                    ],
                )
                return Value(ValueType.INT, call)
            self._poison(
                    expr.operator, "Can't cast value to Int.", code=Code.RUNTIME_CAST
                )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

        if (
            target_desc.ty
            in (
                ValueType.LIST,
                ValueType.MAP,
                ValueType.TUPLE,
                ValueType.ENUM,
            )
            and value.ty is target_desc.ty
            and not value.optional
        ):
            return value

        target = self._target_class(expr.target_type, expr.operator.line)
        if value.optional:
            value = self._unwrap(
                value,
                expr.operator.line,
                f"Can't cast value to {target}.",
            )
        check = self._is_instance(
            value, target, expr.operator.line, expr.operator.column
        )
        ok = llvm_ir.append_block(self._function_ir, "as.ok")
        bad = llvm_ir.append_block(self._function_ir, "as.bad")
        self.builder.cbranch(check.llvm, ok, bad)

        self.builder = llvm_ir.builder(bad)
        self._poison(
            expr.operator, f"Can't cast value to {target}.", code=Code.RUNTIME_CAST
        )

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
            f"lox.bound.{layout.ir_name or layout.name}.{method.name}",
            result,
            [_I8_PTR, *[self._storage_llvm_type(param) for param in sig.params]],
        )

        saved = (
            self.builder,
            self._function_ir,
            self._return_type_desc,
            self._in_init,
            self._scopes,
            self._captures,
        )
        self._function_ir = thunk
        self._return_type_desc = sig.ret
        self._in_init = False
        self._scopes = [{}]
        self._captures = {}
        self.builder = llvm_ir.builder(llvm_ir.block_of(thunk, "entry"))

        self._emit_thunk_call(thunk, sig, result)
        self._seal_blocks(thunk)
        method.thunk = thunk

        (
            self.builder,
            self._function_ir,
            self._return_type_desc,
            self._in_init,
            self._scopes,
            self._captures,
        ) = saved
        return thunk

    def _emit_thunk_call(
        self, thunk: Any, sig: FnSig, result: Any
    ) -> None:
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
