# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tuplas (L6): runtime boxeado, índice, igualdade, destructuring e len."""

from __future__ import annotations

from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
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
from loxia_core.frontend.ty import TupleTy, Ty
from loxia_core.thir import (
    TDestructurePattern,
    TNamePattern,
    TTuplePattern,
)
from loxia_core.thir import (
    TDestructureStmt as Destructure,
)
from loxia_core.thir import (
    TIndex as Index,
)
from loxia_core.thir import (
    TTuple as TupleLiteral,
)


class TupleLowering(LoweringBase):
    def _tuple_types(self, expr: Any, line: int | None) -> tuple[TypeDesc, ...]:
        ty = expr.storage_ty
        if isinstance(ty, TupleTy):
            return tuple(self._type_desc(self._subst_ty(item), line) for item in ty.items)
        if isinstance(expr, TupleLiteral) and expr.items:
            result = []
            for element in expr.items:
                item_ty = element.storage_ty
                if item_ty is None:
                    raise _unsupported("Tuple element type", line)
                result.append(self._type_desc(item_ty, line))
            return tuple(result)
        raise _unsupported("Tuple element types", line)

    def _tuple_literal(self, expr: TupleLiteral) -> Value:
        descs = self._tuple_types(expr, None)
        raw = self.builder.call(
            self._function("lox_tuple_new", _I8_PTR, [_INT]),
            [llvm_ir.constant(_INT, len(expr.items))],
        )
        for index, (element, desc) in enumerate(zip(expr.items, descs, strict=True)):
            value = self._coerce(self._expr(element), desc, self._line(element.span))
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
            self._expr(expr.index), TypeDesc(ValueType.INT), self._line(expr.bracket_span)
        )
        raw = self.builder.call(
            self._function("lox_tuple_get", _ANY, [_I8_PTR, _INT, _I32, _I32]),
            [
                obj.llvm,
                index.llvm,
                llvm_ir.constant(_I32, self._line(expr.bracket_span)),
                llvm_ir.constant(_I32, self._column(expr.bracket_span)),
            ],
        )
        if expr.storage_ty is None:
            raise _unsupported("Tuple element type", self._line(expr.bracket_span))
        desc = self._type_desc(expr.storage_ty, self._line(expr.bracket_span))
        return self._unbox_value(raw, desc, self._line(expr.bracket_span))

    def _tuple_len(self, value: Value) -> Value:
        return Value(
            ValueType.INT,
            self.builder.call(self._function("lox_tuple_len", _INT, [_I8_PTR]), [value.llvm]),
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
        span = stmt.pattern.span or stmt.span
        line = self._line(span)
        ty = self._pattern_type(stmt.pattern)
        if ty is None:
            ty = stmt.initializer.storage_ty or stmt.initializer.ty
        if ty is None:
            raise _unsupported("Destructuring initializer type", line)
        self._bind_pattern(stmt.pattern, value, ty)

    def _pattern_type(self, pattern: TDestructurePattern) -> Ty | None:
        """Tipo declarado do padrão, reconstruído dos `Decl` das folhas."""
        if isinstance(pattern, TNamePattern):
            return self._decl(pattern.decl).ty
        if isinstance(pattern, TTuplePattern):
            items: list[Ty] = []
            for element in pattern.elements:
                item = self._pattern_type(element)
                if item is None:
                    return None
                items.append(item)
            return TupleTy(tuple(items))
        return None

    def _bind_pattern(self, pattern: TDestructurePattern, value: Value, ty: Ty | None) -> None:
        line = self._line(pattern.span)

        if isinstance(pattern, TNamePattern):
            if ty is None:
                raise _unsupported("Destructured binding type", line)
            desc = self._type_desc(self._subst_ty(ty), line)
            self._bind_destructured_name(pattern.decl, value, desc)
            return

        if value.ty is not ValueType.TUPLE or not isinstance(ty, TupleTy):
            raise _unsupported("Destructuring a non-tuple", line)
        if not isinstance(pattern, TTuplePattern):
            raise _unsupported("Destructuring pattern", line)
        if len(ty.items) != len(pattern.elements):
            raise _unsupported("Destructuring arity", line)

        for index, (element, item_ty) in enumerate(zip(pattern.elements, ty.items, strict=True)):
            raw = self.builder.call(
                self._function("lox_tuple_get", _ANY, [_I8_PTR, _INT, _I32, _I32]),
                [
                    value.llvm,
                    llvm_ir.constant(_INT, index),
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, 0),
                ],
            )
            item = self._unbox_value(raw, self._type_desc(self._subst_ty(item_ty), line), line)
            self._bind_pattern(element, item, item_ty)

    def _bind_destructured_name(self, decl: int, value: Value, desc: TypeDesc) -> None:
        name = self._decl(decl).name
        if self._function_ir is self.main and len(self._scopes) == 1:
            slot = llvm_ir.global_variable(self.module, f"g.{name}", self._storage_llvm_type(desc))
            self.builder.store(value.llvm, slot)
            self._globals[name] = Binding(
                slot,
                desc.ty,
                desc.fn,
                desc.optional,
                class_name=desc.class_name,
                interface_name=desc.interface_name,
            )
            return

        if self._decl(decl).cell:
            cell = self._alloc_cell()
            self.builder.store(value.llvm, self._cell_pointer(cell, desc))
            self._scopes[-1][name] = Binding(
                cell,
                desc.ty,
                desc.fn,
                desc.optional,
                cell=True,
                class_name=desc.class_name,
                interface_name=desc.interface_name,
            )
            return

        slot = self.builder.alloca(self._storage_llvm_type(desc), name=name)
        self.builder.store(value.llvm, slot)
        self._scopes[-1][name] = Binding(
            slot,
            desc.ty,
            desc.fn,
            desc.optional,
            class_name=desc.class_name,
            interface_name=desc.interface_name,
        )
