# SPDX-License-Identifier: MIT OR Apache-2.0
"""Acesso a campos, bitmap, leitura/escrita e `get`/`set` de instâncias."""

from __future__ import annotations

from typing import Any, cast

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _ANY,
    _BOOL,
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    ClassLayout,
    FieldLayout,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.frontend.expr import Get, Set, Variable
from loxia_core.frontend.tokens import Token


class InstanceLowering(LoweringBase):
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
        # `slot` é absoluto: já conta o header (`class` + bitmap).
        return self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, field.slot)],
        )

    def _bitmap_slot(self, value: Value, line: int) -> Any:
        struct_ = self._instance_struct(value, line)
        return self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)],
        )

    def _check_bitmap(
        self,
        value: Value,
        field: FieldLayout,
        line: int,
        message: str,
        column: int = 0,
    ) -> None:
        bitmap = self.builder.load(self._bitmap_slot(value, line))
        mask = llvm_ir.constant(_INT, 1 << field.index)
        present = self.builder.icmp_signed(
            "!=", self.builder.and_(bitmap, mask), llvm_ir.constant(_INT, 0)
        )
        ok = self._control.new_block(self._function_ir, "field.ok")
        bad = self._control.new_block(self._function_ir, "field.nil")
        self.builder.cbranch(present, ok, bad)

        self.builder = llvm_ir.builder(bad)
        self._poison(line, message, column=column, code=Code.UNDEFINED_PROPERTY)

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
                return Value(ValueType.FLOAT, self.builder.bitcast(raw, _FLOAT))
            case ValueType.BOOL:
                return Value(ValueType.BOOL, self.builder.trunc(raw, _BOOL))
            case (
                ValueType.STRING
                | ValueType.RANGE
                | ValueType.LIST
                | ValueType.MAP
                | ValueType.TUPLE
                | ValueType.ENUM
                | ValueType.BYTES
            ):
                return Value(
                    desc.ty,
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
                    interface_name=desc.interface_name,
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
            case (
                ValueType.STRING
                | ValueType.RANGE
                | ValueType.LIST
                | ValueType.MAP
                | ValueType.TUPLE
                | ValueType.ENUM
                | ValueType.BYTES
                | ValueType.FUNCTION
                | ValueType.CLASS
                | ValueType.INSTANCE
            ):
                return self.builder.ptrtoint(value.llvm, _INT)
            case ValueType.NIL:
                return llvm_ir.constant(_INT, 0)
        raise _unsupported(f"Field value '{value.ty.name}'", None)

    def _load_field(
        self,
        instance: Value,
        field: FieldLayout,
        line: int,
        column: int = 0,
    ) -> Value:
        self._check_bitmap(
            instance,
            field,
            line,
            f"Undefined property '{field.name}'.",
            column,
        )
        slot = self._field_slot(instance, field)
        if field.ty.ty is ValueType.ANY:
            # ADR-0145: o campo `Any` ocupa `{tag, payload}` inline; o agregado é o
            # mesmo consumido por `is`/`as`/print, sem unbox no ponto de leitura.
            return Value(ValueType.ANY, self.builder.load(self._any_slot(slot)))
        return self._slot_to_value(slot, field.ty)

    def _any_slot(self, slot: Any) -> Any:
        return self.builder.bitcast(slot, _ANY.as_pointer())

    def _store_field(self, instance: Value, field: FieldLayout, value: Value) -> None:
        slot = self._field_slot(instance, field)
        if field.ty.ty is ValueType.ANY:
            # Todos os callers coerce, mas `lower_exceptions` chama `_store_field`
            # direto: um campo dinâmico futuro não pode gravar lixo.
            if value.ty is not ValueType.ANY:
                value = self._box_value(value, field.line)
            self.builder.store(value.llvm, self._any_slot(slot))
        else:
            self.builder.store(self._value_to_slot(value), slot)
        self._set_bitmap(instance, field)

    def _get(self, expr: Get) -> Value:
        if isinstance(expr.object, Variable) and expr.object.name.lexeme in self._enum_layouts:
            return self._enum_get(expr)
        obj = self._narrowed(expr.object, self._expr(expr.object), expr.name.line)
        if obj.ty is ValueType.BYTES:
            return cast("Value", self._bytes_method_value(expr))
        if expr.optional:
            if obj.ty is ValueType.NIL:
                return self._zero_desc(self._expr_type_desc(expr, expr.name.line))
            if obj.optional:
                return self._get_optional(obj, expr)

        return self._get_instance(obj, expr)

    def _get_optional(self, obj: Value, expr: Get) -> Value:
        result = self._expr_type_desc(expr, expr.name.line)
        if result.ty is ValueType.NIL and not result.optional:
            # `c = nil; c?.x`: o checker já sabe que o resultado é nil.
            return Value(ValueType.NIL)
        if not result.optional and result.ty is not ValueType.ANY:
            # `Any` já codifica nil na tag; marcá-lo opcional faria a representação
            # virar ponteiro nulo, mas o slot é o agregado `{tag, payload}`.
            result = TypeDesc(result.ty, result.fn, True, result.class_name)

        some = self._control.new_block(self._function_ir, "get.some")
        nothing = self._control.new_block(self._function_ir, "get.nil")
        end = self._control.new_block(self._function_ir, "get.end")
        tag = self._optional_tag(obj)
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(some)
        payload = self._optional_payload(obj)
        value = self._coerce(self._get_instance(payload, expr), result, expr.name.line)
        self.builder.branch(end)
        some_end = self.builder.block

        self.builder = llvm_ir.builder(nothing)
        zero = self._zero_desc(result)
        self.builder.branch(end)
        nothing_end = self.builder.block

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(self._storage_llvm_type(result), "get.value")
        merged.add_incoming(value.llvm, some_end)
        merged.add_incoming(zero.llvm, nothing_end)
        return Value(
            result.ty,
            merged,
            result.fn,
            result.optional,
            result.class_name,
        )

    def _exception_text(self, value: Value, line: int = 0) -> Value | None:
        """`Tipo: mensagem` para instância de `Exception` (paridade com o tree-walk)."""
        name = value.class_name
        if name is None:
            return None
        layout = self._classes.get(name)
        if layout is None:
            return None
        cursor: ClassLayout | None = layout
        while cursor is not None:
            if cursor.name == "Exception":
                break
            cursor = cursor.super_layout
        if cursor is None:
            return None
        field = layout.field("message")
        if field is None:
            return None
        message = self._load_field(value, field, line, 0)
        prefix = self._string_literal(f"{layout.display}: ")
        return cast(Value, self._concat(prefix, message))

    def _get_instance(self, obj: Value, expr: Get) -> Value:
        return self._get_instance_name(obj, expr.name)

    def _get_instance_name(self, obj: Value, name: Token) -> Value:
        if obj.ty is not ValueType.INSTANCE:
            self._poison(name, "Only instances have properties.", code=Code.INVALID_VALUE)
            return self._zero(ValueType.INT)

        if obj.interface_name is not None and obj.class_name is None:
            return self._interface_bound_method(obj, obj.interface_name, name)

        layout = self._layout_for(obj, name.line)
        field = layout.field(name.lexeme)
        if field is not None:
            return self._load_field(obj, field, name.line, name.column)
        method = layout.method(name.lexeme)
        if method is not None:
            return self._bound_method(obj, layout, method)

        for interface in layout.effective_interfaces():
            if self._interface_has_method(interface, name.lexeme):
                return self._interface_bound_method(obj, interface, name)

        self._poison(name, f"Undefined property '{name.lexeme}'.")
        return self._zero(ValueType.INT)

    def _set(self, expr: Set) -> Value:
        obj = self._narrowed(expr.object, self._expr(expr.object), expr.name.line)
        field: FieldLayout | None = None
        if obj.ty is ValueType.INSTANCE:
            layout = self._layout_for(obj, expr.name.line)
            field = layout.field(expr.name.lexeme)
        # Resolve the field first so a `[]` initializer can inherit its element type;
        # the value is still lowered exactly once, before either poison path.
        value = self._expr_with_expected(expr.value, None if field is None else field.annotation)
        if obj.ty is not ValueType.INSTANCE:
            self._poison(expr.name, "Only instances have fields.", code=Code.INVALID_VALUE)
            return value
        if field is None:
            self._poison(
                expr.name, f"Undefined field '{expr.name.lexeme}'.", code=Code.UNDEFINED_PROPERTY
            )
            return value

        value = self._coerce(value, field.ty, expr.name.line)

        if not field.mutable:
            if not self._in_init:
                self._poison(
                    expr.name,
                    f"Can't assign to immutable field '{field.name}'.",
                    code=Code.RUNTIME_IMMUTABLE,
                )
                return value
            bitmap = self.builder.load(self._bitmap_slot(obj, field.line))
            mask = llvm_ir.constant(_INT, 1 << field.index)
            already = self.builder.icmp_signed(
                "!=",
                self.builder.and_(bitmap, mask),
                llvm_ir.constant(_INT, 0),
            )
            fresh = self._control.new_block(self._function_ir, "val.fresh")
            used = self._control.new_block(self._function_ir, "val.used")
            end = self._control.new_block(self._function_ir, "val.end")
            self.builder.cbranch(already, used, fresh)

            self.builder = llvm_ir.builder(used)
            self._poison(
                expr.name,
                f"Can't assign to immutable field '{field.name}'.",
                code=Code.RUNTIME_IMMUTABLE,
            )
            self.builder = llvm_ir.builder(fresh)
            self._store_field(obj, field, value)
            self.builder.branch(end)

            self.builder = llvm_ir.builder(end)
            return value

        self._store_field(obj, field, value)
        return value
