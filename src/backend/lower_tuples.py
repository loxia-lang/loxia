"""Tuplas (L6): runtime boxeado, índice, igualdade, destructuring e len."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _ANY,
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    Binding,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.frontend.expr import Index, TupleLiteral
from src.frontend.stmt import Destructure
from src.frontend.ty import TupleTy


class TupleLowering(LoweringBase):
    def _tuple_types(self, expr: Any, line: int | None) -> tuple[TypeDesc, ...]:
        ty = self.types.get(expr)
        if isinstance(ty, TupleTy):
            return tuple(self._type_desc(self._subst_ty(item), line) for item in ty.items)
        if isinstance(expr, TupleLiteral) and expr.elements:
            result = []
            for element in expr.elements:
                item_ty = self.types.get(element)
                if item_ty is None:
                    raise _unsupported("Tuple element type", line)
                result.append(self._type_desc(item_ty, line))
            return tuple(result)
        raise _unsupported("Tuple element types", line)

    def _tuple_literal(self, expr: TupleLiteral) -> Value:
        descs = self._tuple_types(expr, None)
        raw = self.builder.call(
            self._function("lox_tuple_new", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, len(expr.elements))],
        )
        for index, (element, desc) in enumerate(zip(expr.elements, descs, strict=True)):
            value = self._coerce(self._expr(element), desc, element.line if hasattr(element, "line") else None)
            boxed = self._box_value(value, None)
            self.builder.call(
                self._function("lox_tuple_set", _VOID, [_I8_PTR, _INT, _INT, _INT]),
                [
                    raw,
                    llvm_ir.constant(_INT, index),
                    self.builder.extract_value(boxed.llvm, 0),
                    self.builder.extract_value(boxed.llvm, 1),
                ],
            )
        return Value(ValueType.TUPLE, raw)

    def _tuple_get(self, expr: Index, obj: Value) -> Value:
        index = self._coerce(
            self._expr(expr.index), TypeDesc(ValueType.INT), expr.bracket.line
        )
        raw = self.builder.call(
            self._function("lox_tuple_get", _ANY, [_I8_PTR, _INT, _I32]),
            [obj.llvm, index.llvm, llvm_ir.constant(_I32, expr.bracket.line)],
        )
        desc = self._type_desc(self.types[expr], expr.bracket.line)
        return self._unbox_value(raw, desc, expr.bracket.line)

    def _tuple_len(self, value: Value) -> Value:
        return Value(
            ValueType.INT,
            self.builder.call(
                self._function("lox_tuple_len", _INT, [_I8_PTR]), [value.llvm]
            ),
        )

    def _tuple_equal(self, left: Value, right: Value) -> Value:
        call = self.builder.call(
            self._function("lox_tuple_equal", _I32, [_I8_PTR, _I8_PTR]),
            [left.llvm, right.llvm],
        )
        return Value(
            ValueType.BOOL,
            self.builder.icmp_signed("!=", call, llvm_ir.constant(_I32, 0)),
        )

    def _destructure(self, stmt: Destructure) -> None:
        value = self._expr(stmt.initializer)
        if value.ty is not ValueType.TUPLE:
            raise _unsupported("Destructuring a non-tuple", stmt.names[0].line)
        if isinstance(stmt.type_annotation, TupleTy):
            descs = tuple(
                self._type_desc(self._subst_ty(item), stmt.names[0].line)
                for item in stmt.type_annotation.items
            )
        else:
            descs = self._tuple_types(stmt.initializer, stmt.names[0].line)
        if len(descs) != len(stmt.names):
            raise _unsupported("Destructuring arity", stmt.names[0].line)
        for index, (name, desc) in enumerate(zip(stmt.names, descs, strict=True)):
            raw = self.builder.call(
                self._function("lox_tuple_get", _ANY, [_I8_PTR, _INT, _I32]),
                [
                    value.llvm,
                    llvm_ir.constant(_INT, index),
                    llvm_ir.constant(_I32, name.line),
                ],
            )
            item = self._unbox_value(raw, desc, name.line)
            if self._function_ir is self.main and len(self._scopes) == 1:
                slot = llvm_ir.global_variable(self.module, f"g.{name.lexeme}", self._storage_llvm_type(desc))
            else:
                slot = self.builder.alloca(
                    self._storage_llvm_type(desc), name=name.lexeme
                )
            self.builder.store(item.llvm, slot)
            binding = Binding(
                slot, desc.ty, desc.fn, desc.optional, class_name=desc.class_name
            )
            if self._function_ir is self.main and len(self._scopes) == 1:
                self._globals[name.lexeme] = binding
            else:
                self._scopes[-1][name.lexeme] = binding
