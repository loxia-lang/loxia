"""Acesso a campos, bitmap, leitura/escrita e `get`/`set` de instâncias."""

from __future__ import annotations

from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
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
        ok = llvm_ir.append_block(self._function_ir, "field.ok")
        bad = llvm_ir.append_block(self._function_ir, "field.nil")
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
        return self._slot_to_value(self._field_slot(instance, field), field.ty)

    def _store_field(self, instance: Value, field: FieldLayout, value: Value) -> None:
        self.builder.store(self._value_to_slot(value), self._field_slot(instance, field))
        self._set_bitmap(instance, field)

    def _get(self, expr: Get) -> Value:
        if isinstance(expr.object, Variable) and expr.object.name.lexeme in self._enum_layouts:
            return self._enum_get(expr)
        obj = self._expr(expr.object)
        if expr.optional:
            if obj.ty is ValueType.NIL:
                return self._zero_desc(self._expr_type_desc(expr, expr.name.line))
            if obj.optional:
                return self._get_optional(obj, expr)

        return self._get_instance(obj, expr)

    def _get_optional(self, obj: Value, expr: Get) -> Value:
        result = self._expr_type_desc(expr, expr.name.line)
        if not result.optional:
            result = TypeDesc(result.ty, result.fn, True, result.class_name)

        some = llvm_ir.append_block(self._function_ir, "get.some")
        nothing = llvm_ir.append_block(self._function_ir, "get.nil")
        end = llvm_ir.append_block(self._function_ir, "get.end")
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
            True,
            result.class_name,
        )

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
        obj = self._expr(expr.object)
        value = self._expr(expr.value)
        if obj.ty is not ValueType.INSTANCE:
            self._poison(expr.name, "Only instances have fields.", code=Code.INVALID_VALUE)
            return value

        layout = self._layout_for(obj, expr.name.line)
        field = layout.field(expr.name.lexeme)
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
            fresh = llvm_ir.append_block(self._function_ir, "val.fresh")
            used = llvm_ir.append_block(self._function_ir, "val.used")
            end = llvm_ir.append_block(self._function_ir, "val.end")
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
