"""Listas (L6): runtime boxeado, literais, índice, métodos, `len` e igualdade."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _ANY,
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.frontend.expr import Call, Expr, Get, Index, IndexSet, ListLiteral
from src.frontend.ty import ListTy


class ContainerLowering(LoweringBase):
    def _element_desc(self, expr: Expr, line: int | None) -> TypeDesc:
        ty = self.types.get(expr)
        if isinstance(ty, ListTy):
            return self._type_desc(self._subst_ty(ty.element), line)
        if self._list_expected_element is not None:
            return self._type_desc(
                self._subst_ty(self._list_expected_element), line
            )
        raise _unsupported("List element type", line)

    def _list_literal(self, expr: ListLiteral) -> Value:
        if not expr.elements and self.types.get(expr) is None:
            # `len([])` não tem elemento; a lista vazia não carrega nenhum.
            element = TypeDesc(ValueType.INT)
        elif self.types.get(expr) is None and expr.elements:
            first = self.types.get(expr.elements[0])
            element = (
                self._type_desc(self._subst_ty(first), None)
                if first is not None
                else self._element_desc(expr, None)
            )
        else:
            element = self._element_desc(expr, None)
        _ = element
        raw = self.builder.call(
            self._function("lox_list_new", _I8_PTR, []), []
        )
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

    def _list_get(self, expr: Index) -> Value:
        obj = self._expr(expr.object)
        if obj.ty is not ValueType.LIST:
            raise _unsupported("Indexing this value", expr.bracket.line)
        index = self._coerce(self._expr(expr.index), TypeDesc(ValueType.INT), expr.bracket.line)
        raw = self.builder.call(
            self._function("lox_list_get", _ANY, [_I8_PTR, _INT, _I32]),
            [obj.llvm, index.llvm, llvm_ir.constant(_I32, expr.bracket.line)],
        )
        return self._unbox_value(raw, self._element_desc(expr.object, expr.bracket.line), expr.bracket.line)

    def _list_set(self, expr: IndexSet) -> Value:
        obj = self._expr(expr.object)
        if obj.ty is not ValueType.LIST:
            raise _unsupported("Indexed assignment", expr.bracket.line)
        index = self._coerce(self._expr(expr.index), TypeDesc(ValueType.INT), expr.bracket.line)
        element = self._element_desc(expr.object, expr.bracket.line)
        value = self._coerce(self._expr(expr.value), element, expr.bracket.line)
        boxed = self._box_value(value, None)
        self.builder.call(
            self._function("lox_list_set", _VOID, [_I8_PTR, _INT, _INT, _INT, _I32]),
            [
                obj.llvm,
                index.llvm,
                self.builder.extract_value(boxed.llvm, 0),
                self.builder.extract_value(boxed.llvm, 1),
                llvm_ir.constant(_I32, expr.bracket.line),
            ],
        )
        return value

    def _call_list_method(self, expr: Call, obj: Value) -> Value:
        assert isinstance(expr.callee, Get)
        name = expr.callee.name.lexeme
        line = expr.callee.name.line
        list_ty = self.types.get(expr.callee.object)
        if not isinstance(list_ty, ListTy):
            raise _unsupported("List method receiver", line)
        element = self._type_desc(self._subst_ty(list_ty.element), line)
        if name == "push":
            if len(expr.arguments) != 1:
                self._poison(expr.paren.line, "Expected 1 arguments but got 0.")
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
                self._function("lox_list_pop", _ANY, [_I8_PTR, _I32]),
                [obj.llvm, llvm_ir.constant(_I32, line)],
            )
            return self._unbox_value(raw, element, line)
        raise _unsupported(f"List method '{name}'", line)

    def _list_len(self, value: Value) -> Value:
        call = self.builder.call(
            self._function("lox_list_len", _INT, [_I8_PTR]), [value.llvm]
        )
        return Value(ValueType.INT, call)

    def _list_equal(self, left: Value, right: Value) -> Value:
        call = self.builder.call(
            self._function("lox_list_equal", _I32, [_I8_PTR, _I8_PTR]),
            [left.llvm, right.llvm],
        )
        result = self.builder.icmp_signed(
            "!=", call, llvm_ir.constant(_I32, 0)
        )
        return Value(ValueType.BOOL, result)

    def _unbox_value(self, raw: Any, desc: TypeDesc, line: int | None) -> Value:
        tag = self.builder.extract_value(raw, 0)
        payload = self.builder.extract_value(raw, 1)

        def convert(inner: TypeDesc) -> Value:
            match inner.ty:
                case ValueType.INT:
                    return Value(ValueType.INT, payload)
                case ValueType.FLOAT:
                    return Value(
                        ValueType.FLOAT, self.builder.bitcast(payload, _FLOAT)
                    )
                case ValueType.BOOL:
                    return Value(
                        ValueType.BOOL, self.builder.icmp_signed(
                            "!=", payload, llvm_ir.constant(_INT, 0)
                        )
                    )
                case ValueType.STRING:
                    return Value(
                        ValueType.STRING,
                        self.builder.inttoptr(payload, _I8_PTR),
                    )
                case ValueType.LIST | ValueType.MAP | ValueType.RANGE:
                    return Value(
                        inner.ty, self.builder.inttoptr(payload, _I8_PTR)
                    )
                case ValueType.CLASS | ValueType.INSTANCE:
                    return Value(
                        inner.ty,
                        self.builder.inttoptr(payload, _I8_PTR),
                        class_name=inner.class_name,
                    )
                case ValueType.FUNCTION:
                    return Value(
                        ValueType.FUNCTION,
                        self.builder.inttoptr(payload, _I8_PTR),
                        inner.fn,
                    )
                case ValueType.NIL:
                    return Value(ValueType.NIL)
                case _:
                    raise _unsupported(f"List element type '{inner.ty.name}'", line)

        if desc.optional:
            some = llvm_ir.append_block(self._function_ir, "list.some")
            nothing = llvm_ir.append_block(self._function_ir, "list.nil")
            end = llvm_ir.append_block(self._function_ir, "list.end")
            present = self.builder.icmp_signed(
                "!=", tag, llvm_ir.constant(_INT, 0)
            )
            self.builder.cbranch(present, some, nothing)
            self.builder = llvm_ir.builder(nothing)
            zero = self._zero_desc(desc)
            self.builder.branch(end)
            none_end = self.builder.block
            self.builder = llvm_ir.builder(some)
            inner = convert(TypeDesc(desc.ty, desc.fn, False, desc.class_name))
            value = self._some(desc, inner)
            self.builder.branch(end)
            some_end = self.builder.block
            self.builder = llvm_ir.builder(end)
            merged = self.builder.phi(
                self._storage_llvm_type(desc), "list.optional"
            )
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
