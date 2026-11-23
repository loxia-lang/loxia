# SPDX-License-Identifier: MIT OR Apache-2.0
"""Listas (L6): runtime boxeado, literais, índice, métodos, `len` e igualdade."""

from __future__ import annotations

from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _ANY,
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    BackendError,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.frontend.expr import Call, Expr, Get, Index, IndexSet, ListLiteral, MapLiteral
from loxia_core.frontend.ty import ListTy, MapTy


class ContainerLowering(LoweringBase):
    def _element_desc(self, expr: Expr, line: int | None) -> TypeDesc:
        ty = self.types.get(expr)
        if isinstance(ty, ListTy):
            return self._type_desc(self._subst_ty(ty.element), line)
        if self._list_expected_element is not None:
            return self._type_desc(self._subst_ty(self._list_expected_element), line)
        raise _unsupported("List element type", line)

    def _list_storage_kind(self, expr: ListLiteral, line: int | None) -> int:
        """Typed storage for a literal whose element type is a scalar.

        Optional, union, class and function elements stay boxed (`Any` -> 0); the
        runtime promotes a typed list on the first mismatching push, so the
        choice is an optimization, never a semantic one.
        """
        try:
            desc = self._element_desc(expr, line)
        except BackendError:
            return 0
        if (
            desc.optional
            or desc.fn is not None
            or desc.class_name is not None
            or desc.interface_name is not None
        ):
            return 0
        if desc.ty is ValueType.INT:
            return 1
        if desc.ty is ValueType.FLOAT:
            return 2
        if desc.ty is ValueType.BOOL:
            return 3
        if desc.ty is ValueType.STRING:
            return 4
        return 0

    def _list_literal(self, expr: ListLiteral) -> Value:
        kind = self._list_storage_kind(expr, expr.bracket.line)
        if kind != 0:
            raw = self.builder.call(
                self._function("lox_list_new_typed", _I8_PTR, [_I32]),
                [llvm_ir.constant(_I32, kind)],
            )
        else:
            raw = self.builder.call(self._function("lox_list_new", _I8_PTR, []), [])
        for item in expr.elements:
            value = self._expr(item)
            boxed = self._box_value(value, None)
            self.builder.call(
                self._function("lox_list_push", _I8_PTR, [_I8_PTR, _INT, _INT]),
                [
                    raw,
                    self.builder.extract_value(boxed.llvm, 0),
                    self.builder.extract_value(boxed.llvm, 1),
                ],
            )
        return Value(ValueType.LIST, raw)

    def _map_types(self, expr: Expr, line: int | None) -> tuple[TypeDesc, TypeDesc]:
        ty = self.types.get(expr)
        if isinstance(ty, MapTy):
            return (
                self._type_desc(self._subst_ty(ty.key), line),
                self._type_desc(self._subst_ty(ty.value), line),
            )
        if self._map_expected_key is not None and self._map_expected_value is not None:
            return (
                self._type_desc(self._subst_ty(self._map_expected_key), line),
                self._type_desc(self._subst_ty(self._map_expected_value), line),
            )
        if isinstance(expr, MapLiteral) and not expr.entries:
            return TypeDesc(ValueType.ANY), TypeDesc(ValueType.ANY)
        if isinstance(expr, MapLiteral) and expr.entries:
            key_ty = self.types.get(expr.entries[0][0])
            value_ty = self.types.get(expr.entries[0][1])
            key_desc = (
                self._type_desc(key_ty, line)
                if key_ty is not None
                else self._literal_desc(expr.entries[0][0])
            )
            value_desc = (
                self._type_desc(value_ty, line)
                if value_ty is not None
                else self._literal_desc(expr.entries[0][1])
            )
            return key_desc, value_desc
        raise _unsupported("Map key/value type", line)

    def _literal_desc(self, expr: Expr) -> TypeDesc:
        from loxia_core.frontend.expr import Literal

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
        if isinstance(expr, ListLiteral):
            return TypeDesc(ValueType.LIST)
        if isinstance(expr, MapLiteral):
            return TypeDesc(ValueType.MAP)
        return TypeDesc(ValueType.ANY)

    def _map_literal(self, expr: MapLiteral) -> Value:
        raw = self.builder.call(self._function("lox_map_new", _I8_PTR, []), [])
        for key_expr, value_expr in expr.entries:
            key = self._box_value(self._expr(key_expr), None)
            value = self._box_value(self._expr(value_expr), None)
            self.builder.call(
                self._function(
                    "lox_map_set_literal",
                    _VOID,
                    [_I8_PTR, _INT, _INT, _INT, _INT, _I32, _I32],
                ),
                [
                    raw,
                    self.builder.extract_value(key.llvm, 0),
                    self.builder.extract_value(key.llvm, 1),
                    self.builder.extract_value(value.llvm, 0),
                    self.builder.extract_value(value.llvm, 1),
                    llvm_ir.constant(_I32, expr.brace.line),
                    llvm_ir.constant(_I32, expr.brace.column),
                ],
            )
        return Value(ValueType.MAP, raw)

    def _list_get(self, expr: Index) -> Value:
        obj = self._expr(expr.object)
        if obj.ty is ValueType.ANY:
            tag = self.builder.extract_value(obj.llvm, 0)
            payload = self.builder.extract_value(obj.llvm, 1)
            tuple_block = llvm_ir.append_block(self._function_ir, "idx.tuple")
            bad_block = llvm_ir.append_block(self._function_ir, "idx.bad")
            end_block = llvm_ir.append_block(self._function_ir, "idx.end")
            is_tuple = self.builder.icmp_signed("==", tag, llvm_ir.constant(_INT, 11))
            self.builder.cbranch(is_tuple, tuple_block, bad_block)
            self.builder = llvm_ir.builder(tuple_block)
            tuple_value = Value(
                ValueType.TUPLE,
                self.builder.inttoptr(payload, _I8_PTR),
            )
            result = self._tuple_get(expr, tuple_value)
            self.builder.branch(end_block)
            tuple_end = self.builder.block
            self.builder = llvm_ir.builder(bad_block)
            self._poison(expr.bracket, "Indexing this value is not supported.")
            zero = self._zero_desc(self._type_desc(self.types[expr], expr.bracket.line))
            self.builder.branch(end_block)
            bad_end = self.builder.block
            self.builder = llvm_ir.builder(end_block)
            merged = self.builder.phi(
                self._storage_llvm_type(self._type_desc(self.types[expr], expr.bracket.line)),
                "idx.value",
            )
            merged.add_incoming(result.llvm, tuple_end)
            merged.add_incoming(zero.llvm, bad_end)
            return Value(result.ty, merged, result.sig, result.optional, result.class_name)
        if obj.ty is ValueType.TUPLE:
            return self._tuple_get(expr, obj)
        if obj.ty is ValueType.BYTES:
            index = self._coerce(self._expr(expr.index), TypeDesc(ValueType.INT), expr.bracket.line)
            call = self.builder.call(
                self._function(
                    "lox_bytes_at",
                    _INT,
                    [_I8_PTR, _INT, _I32, _I32],
                ),
                [
                    obj.llvm,
                    index.llvm,
                    llvm_ir.constant(_I32, expr.bracket.line),
                    llvm_ir.constant(_I32, expr.bracket.column),
                ],
            )
            return Value(ValueType.INT, call)
        if obj.ty is ValueType.MAP:
            _key_desc, value_desc = self._map_types(expr.object, expr.bracket.line)
            key = self._box_value(self._expr(expr.index), None)
            raw = self.builder.call(
                self._function(
                    "lox_map_get_checked",
                    _ANY,
                    [_I8_PTR, _INT, _INT, _I32, _I32],
                ),
                [
                    obj.llvm,
                    self.builder.extract_value(key.llvm, 0),
                    self.builder.extract_value(key.llvm, 1),
                    llvm_ir.constant(_I32, expr.bracket.line),
                    llvm_ir.constant(_I32, expr.bracket.column),
                ],
            )
            return self._unbox_value(raw, value_desc, expr.bracket.line)
        if obj.ty is not ValueType.LIST:
            raise _unsupported("Indexing this value", expr.bracket.line)
        index = self._coerce(self._expr(expr.index), TypeDesc(ValueType.INT), expr.bracket.line)
        raw = self.builder.call(
            self._function("lox_list_get", _ANY, [_I8_PTR, _INT, _I32, _I32]),
            [
                obj.llvm,
                index.llvm,
                llvm_ir.constant(_I32, expr.bracket.line),
                llvm_ir.constant(_I32, expr.bracket.column),
            ],
        )
        return self._unbox_value(
            raw, self._element_desc(expr.object, expr.bracket.line), expr.bracket.line
        )

    def _list_set(self, expr: IndexSet) -> Value:
        obj = self._expr(expr.object)
        if obj.ty is ValueType.MAP:
            _key_desc, value_desc = self._map_types(expr.object, expr.bracket.line)
            key = self._box_value(self._expr(expr.index), None)
            value = self._coerce(self._expr(expr.value), value_desc, expr.bracket.line)
            boxed = self._box_value(value, None)
            self.builder.call(
                self._function(
                    "lox_map_set",
                    _VOID,
                    [_I8_PTR, _INT, _INT, _INT, _INT, _I32, _I32],
                ),
                [
                    obj.llvm,
                    self.builder.extract_value(key.llvm, 0),
                    self.builder.extract_value(key.llvm, 1),
                    self.builder.extract_value(boxed.llvm, 0),
                    self.builder.extract_value(boxed.llvm, 1),
                    llvm_ir.constant(_I32, expr.bracket.line),
                    llvm_ir.constant(_I32, expr.bracket.column),
                ],
            )
            return value
        if obj.ty is not ValueType.LIST:
            raise _unsupported("Indexed assignment", expr.bracket.line)
        index = self._coerce(self._expr(expr.index), TypeDesc(ValueType.INT), expr.bracket.line)
        element = self._element_desc(expr.object, expr.bracket.line)
        value = self._coerce(self._expr(expr.value), element, expr.bracket.line)
        boxed = self._box_value(value, None)
        self.builder.call(
            self._function("lox_list_set", _VOID, [_I8_PTR, _INT, _INT, _INT, _I32, _I32]),
            [
                obj.llvm,
                index.llvm,
                self.builder.extract_value(boxed.llvm, 0),
                self.builder.extract_value(boxed.llvm, 1),
                llvm_ir.constant(_I32, expr.bracket.line),
                llvm_ir.constant(_I32, expr.bracket.column),
            ],
        )
        return value

    def _call_list_method(self, expr: Call, obj: Value) -> Value:
        assert isinstance(expr.callee, Get)
        name = expr.callee.name.lexeme
        line = expr.callee.name.line
        column = expr.callee.name.column
        list_ty = self.types.get(expr.callee.object)
        if not isinstance(list_ty, ListTy):
            raise _unsupported("List method receiver", line)
        element = self._type_desc(self._subst_ty(list_ty.element), line)
        if name == "push":
            if len(expr.arguments) != 1:
                self._poison(
                    expr.paren,
                    "Expected 1 arguments but got 0.",
                    code=Code.RUNTIME_ARITY,
                )
                return Value(ValueType.NIL)
            value = self._expr(expr.arguments[0])
            boxed = self._box_value(value, None)
            self.builder.call(
                self._function("lox_list_push", _VOID, [_I8_PTR, _INT, _INT]),
                [
                    obj.llvm,
                    self.builder.extract_value(boxed.llvm, 0),
                    self.builder.extract_value(boxed.llvm, 1),
                ],
            )
            return Value(ValueType.NIL)
        if name == "pop":
            raw = self.builder.call(
                self._function("lox_list_pop", _ANY, [_I8_PTR, _I32, _I32]),
                [
                    obj.llvm,
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return self._unbox_value(raw, element, line)
        raise _unsupported(f"List method '{name}'", line)

    def _call_map_method(self, expr: Call, obj: Value) -> Value:
        assert isinstance(expr.callee, Get)
        name = expr.callee.name.lexeme
        line = expr.callee.name.line
        column = expr.callee.name.column
        _key_desc, value_desc = self._map_types(expr.callee.object, line)
        if name in {"get", "has", "remove"}:
            if len(expr.arguments) != 1:
                self._poison(
                    expr.paren,
                    "Expected 1 arguments but got 0.",
                    code=Code.RUNTIME_ARITY,
                )
                return Value(ValueType.NIL)
            key = self._box_value(self._expr(expr.arguments[0]), None)
            tag = self.builder.extract_value(key.llvm, 0)
            payload = self.builder.extract_value(key.llvm, 1)
            if name == "has":
                call = self.builder.call(
                    self._function("lox_map_has", _I32, [_I8_PTR, _INT, _INT, _I32, _I32]),
                    [
                        obj.llvm,
                        tag,
                        payload,
                        llvm_ir.constant(_I32, line),
                        llvm_ir.constant(_I32, column),
                    ],
                )
                return Value(
                    ValueType.BOOL,
                    self.builder.icmp_signed("!=", call, llvm_ir.constant(_I32, 0)),
                )
            if name == "remove":
                raw = self.builder.call(
                    self._function("lox_map_remove", _ANY, [_I8_PTR, _INT, _INT, _I32, _I32]),
                    [
                        obj.llvm,
                        tag,
                        payload,
                        llvm_ir.constant(_I32, line),
                        llvm_ir.constant(_I32, column),
                    ],
                )
                return self._unbox_value(raw, value_desc, line)
            optional = TypeDesc(value_desc.ty, value_desc.fn, True, value_desc.class_name)
            raw = self.builder.call(
                self._function("lox_map_get", _ANY, [_I8_PTR, _INT, _INT, _I32, _I32]),
                [
                    obj.llvm,
                    tag,
                    payload,
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return self._unbox_value(raw, optional, line)
        if name in {"keys", "values"}:
            function = "lox_map_keys" if name == "keys" else "lox_map_values"
            raw = self.builder.call(self._function(function, _I8_PTR, [_I8_PTR]), [obj.llvm])
            return Value(ValueType.LIST, raw)
        raise _unsupported(f"Map method '{name}'", line)

    def _map_len(self, value: Value) -> Value:
        return Value(
            ValueType.INT,
            self.builder.call(self._function("lox_map_len", _INT, [_I8_PTR]), [value.llvm]),
        )

    def _map_equal(self, left: Value, right: Value) -> Value:
        call = self.builder.call(
            self._function("lox_map_equal", _I32, [_I8_PTR, _I8_PTR]),
            [left.llvm, right.llvm],
        )
        return Value(
            ValueType.BOOL,
            self.builder.icmp_signed("!=", call, llvm_ir.constant(_I32, 0)),
        )

    def _chars(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1 or arguments[0].ty is not ValueType.STRING:
            self._poison(expr.paren, "chars() expects a string.")
            return Value(ValueType.LIST, llvm_ir.null_pointer())
        return Value(
            ValueType.LIST,
            self.builder.call(
                self._function("lox_chars", _I8_PTR, [_I8_PTR]),
                [arguments[0].llvm],
            ),
        )

    def _list_len(self, value: Value) -> Value:
        call = self.builder.call(self._function("lox_list_len", _INT, [_I8_PTR]), [value.llvm])
        return Value(ValueType.INT, call)

    def _list_equal(self, left: Value, right: Value) -> Value:
        call = self.builder.call(
            self._function("lox_list_equal", _I32, [_I8_PTR, _I8_PTR]),
            [left.llvm, right.llvm],
        )
        result = self.builder.icmp_signed("!=", call, llvm_ir.constant(_I32, 0))
        return Value(ValueType.BOOL, result)

    def _unbox_any(self, value: Value, desc: TypeDesc, line: int | None) -> Value:
        return self._unbox_value(value.llvm, desc, line)

    def _unbox_value(self, raw: Any, desc: TypeDesc, line: int | None) -> Value:
        tag = self.builder.extract_value(raw, 0)
        payload = self.builder.extract_value(raw, 1)

        def convert(inner: TypeDesc) -> Value:
            match inner.ty:
                case ValueType.INT:
                    return Value(ValueType.INT, payload)
                case ValueType.FLOAT:
                    return Value(ValueType.FLOAT, self.builder.bitcast(payload, _FLOAT))
                case ValueType.BOOL:
                    return Value(
                        ValueType.BOOL,
                        self.builder.icmp_signed("!=", payload, llvm_ir.constant(_INT, 0)),
                    )
                case ValueType.STRING:
                    return Value(
                        ValueType.STRING,
                        self.builder.inttoptr(payload, _I8_PTR),
                    )
                case (
                    ValueType.LIST
                    | ValueType.MAP
                    | ValueType.RANGE
                    | ValueType.TUPLE
                    | ValueType.BYTES
                ):
                    return Value(inner.ty, self.builder.inttoptr(payload, _I8_PTR))
                case ValueType.CLASS | ValueType.INSTANCE:
                    return Value(
                        inner.ty,
                        self.builder.inttoptr(payload, _I8_PTR),
                        class_name=inner.class_name,
                        interface_name=inner.interface_name,
                    )
                case ValueType.ENUM:
                    return Value(
                        ValueType.ENUM,
                        self.builder.inttoptr(payload, _I8_PTR),
                    )
                case ValueType.FUNCTION:
                    return Value(
                        ValueType.FUNCTION,
                        self.builder.inttoptr(payload, _I8_PTR),
                        inner.fn,
                    )
                case ValueType.ANY:
                    return Value(ValueType.ANY, raw)
                case ValueType.NIL:
                    return Value(ValueType.NIL)
                case _:
                    raise _unsupported(f"List element type '{inner.ty.name}'", line)

        if desc.ty is ValueType.NIL:
            return Value(ValueType.NIL)

        if desc.optional:
            some = llvm_ir.append_block(self._function_ir, "list.some")
            nothing = llvm_ir.append_block(self._function_ir, "list.nil")
            end = llvm_ir.append_block(self._function_ir, "list.end")
            present = self.builder.icmp_signed("!=", tag, llvm_ir.constant(_INT, 0))
            self.builder.cbranch(present, some, nothing)
            self.builder = llvm_ir.builder(nothing)
            zero = self._zero_desc(desc)
            self.builder.branch(end)
            none_end = self.builder.block
            self.builder = llvm_ir.builder(some)
            inner = convert(
                TypeDesc(
                    desc.ty,
                    desc.fn,
                    False,
                    desc.class_name,
                    desc.interface_name,
                )
            )
            value = self._some(desc, inner)
            self.builder.branch(end)
            some_end = self.builder.block
            self.builder = llvm_ir.builder(end)
            merged = self.builder.phi(self._storage_llvm_type(desc), "list.optional")
            merged.add_incoming(zero.llvm, none_end)
            merged.add_incoming(value.llvm, some_end)
            return Value(
                desc.ty,
                merged,
                desc.fn,
                True,
                desc.class_name,
            )

        return convert(desc)
