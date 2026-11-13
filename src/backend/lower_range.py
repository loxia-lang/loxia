"""Range e `for-in` (L6): Range é ponteiro de runtime; iteração é lowering direto."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _I8_PTR,
    _I32,
    _INT,
    Binding,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.frontend.expr import Range
from src.frontend.stmt import ForIn


class RangeLowering(LoweringBase):
    def _range_expr(self, expr: Range) -> Value:
        start = self._coerce(self._expr(expr.start), self._int_desc(), expr.operator.line)
        end = self._coerce(self._expr(expr.end), self._int_desc(), expr.operator.line)
        raw = self.builder.call(
            self._function("lox_range_new", _I8_PTR, [_INT, _INT, _INT]),
            [start.llvm, end.llvm, llvm_ir.constant(_INT, 1)],
        )
        return Value(ValueType.RANGE, raw)

    def _range_call(self, expr: Any) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 3:
            self._poison(
                expr.paren.line,
                f"Expected 3 arguments but got {len(arguments)}.",
            )
            return Value(ValueType.RANGE, llvm_ir.null_pointer())
        coerced = [
            self._coerce(argument, self._int_desc(), expr.paren.line)
            for argument in arguments
        ]
        raw = self.builder.call(
            self._function("lox_range_new", _I8_PTR, [_INT, _INT, _INT]),
            [value.llvm for value in coerced],
        )
        return Value(ValueType.RANGE, raw)

    def _int_desc(self) -> Any:
        from src.backend.lower_model import TypeDesc

        return TypeDesc(ValueType.INT)

    def _for_in(self, stmt: ForIn) -> None:
        iterable = self._expr(stmt.iterable)
        if iterable.ty is ValueType.RANGE:
            self._for_range(stmt, iterable)
            return
        if iterable.ty is ValueType.STRING:
            self._for_string(stmt, iterable)
            return
        if iterable.ty is ValueType.LIST:
            self._for_list(stmt, iterable)
            return
        if iterable.ty is ValueType.MAP:
            self._for_map(stmt, iterable)
            return
        if iterable.ty is ValueType.TUPLE:
            self._for_tuple(stmt, iterable)
            return
        raise _unsupported(
            "for-in over this value (List/Map/tuple are later in L6)",
            stmt.name.line,
        )

    def _for_tuple(self, stmt: ForIn, iterable: Value) -> None:
        index = self.builder.alloca(_INT, name="for.tuple")
        self.builder.store(llvm_ir.constant(_INT, 0), index)
        length = self.builder.call(
            self._function("lox_tuple_len", _INT, [_I8_PTR]), [iterable.llvm]
        )

        def condition() -> Any:
            return self.builder.icmp_signed("<", self.builder.load(index), length)

        def load() -> Any:
            return self.builder.call(
                self._function("lox_tuple_get", self._any_type(), [_I8_PTR, _INT, _I32]),
                [
                    iterable.llvm,
                    self.builder.load(index),
                    llvm_ir.constant(_I32, stmt.name.line),
                ],
            )

        def advance() -> None:
            self.builder.store(
                self.builder.add(self.builder.load(index), llvm_ir.constant(_INT, 1)),
                index,
            )

        self._for_loop(stmt, TypeDesc(ValueType.ANY), condition, load, advance)

    def _for_map(self, stmt: ForIn, iterable: Value) -> None:
        index = self.builder.alloca(_INT, name="for.map")
        self.builder.store(llvm_ir.constant(_INT, 0), index)
        length = self.builder.call(
            self._function("lox_map_len", _INT, [_I8_PTR]), [iterable.llvm]
        )
        key_desc, _ = self._map_types(stmt.iterable, stmt.name.line)

        def condition() -> Any:
            return self.builder.icmp_signed(
                "<", self.builder.load(index), length
            )

        def load() -> Any:
            raw = self.builder.call(
                self._function("lox_map_key_at", self._any_type(), [_I8_PTR, _INT]),
                [iterable.llvm, self.builder.load(index)],
            )
            return self._unbox_value(raw, key_desc, stmt.name.line).llvm

        def advance() -> None:
            self.builder.store(
                self.builder.add(
                    self.builder.load(index), llvm_ir.constant(_INT, 1)
                ),
                index,
            )

        self._for_loop(stmt, key_desc, condition, load, advance)

    def _for_list(self, stmt: ForIn, iterable: Value) -> None:
        index = self.builder.alloca(_INT, name="for.list")
        self.builder.store(llvm_ir.constant(_INT, 0), index)
        length = self.builder.call(
            self._function("lox_list_len", _INT, [_I8_PTR]), [iterable.llvm]
        )
        element = self._element_desc(stmt.iterable, stmt.name.line)

        def condition() -> Any:
            return self.builder.icmp_signed(
                "<", self.builder.load(index), length
            )

        def load() -> Any:
            raw = self.builder.call(
                self._function("lox_list_get", self._any_type(), [_I8_PTR, _INT, _I32]),
                [
                    iterable.llvm,
                    self.builder.load(index),
                    llvm_ir.constant(_I32, stmt.name.line),
                ],
            )
            return self._unbox_value(raw, element, stmt.name.line).llvm

        def advance() -> None:
            self.builder.store(
                self.builder.add(
                    self.builder.load(index), llvm_ir.constant(_INT, 1)
                ),
                index,
            )

        self._for_loop(stmt, element, condition, load, advance)

    def _any_type(self) -> Any:
        from src.backend.lower_model import _ANY

        return _ANY

    def _for_range(self, stmt: ForIn, iterable: Value) -> None:
        start = self.builder.call(
            self._function("lox_range_start", _INT, [_I8_PTR]), [iterable.llvm]
        )
        end = self.builder.call(
            self._function("lox_range_end", _INT, [_I8_PTR]), [iterable.llvm]
        )
        step = self.builder.call(
            self._function("lox_range_step", _INT, [_I8_PTR]), [iterable.llvm]
        )
        index = self.builder.alloca(_INT, name="for.range")
        self.builder.store(start, index)
        negative = self.builder.icmp_signed(
            "<", step, llvm_ir.constant(_INT, 0)
        )
        self._for_loop(
            stmt,
            TypeDesc(ValueType.INT),
            condition=lambda: self._range_condition(index, end, step, negative),
            load=lambda: self.builder.load(index),
            advance=lambda: self.builder.store(
                self.builder.add(self.builder.load(index), step), index
            ),
        )

    def _range_condition(self, index: Any, end: Any, step: Any, negative: Any) -> Any:
        below = self.builder.icmp_signed("<", self.builder.load(index), end)
        above = self.builder.icmp_signed(">", self.builder.load(index), end)
        return self.builder.select(negative, above, below)

    def _for_string(self, stmt: ForIn, iterable: Value) -> None:
        index = self.builder.alloca(_INT, name="for.str")
        self.builder.store(llvm_ir.constant(_INT, 0), index)
        length = self.builder.call(
            self._function("lox_str_len", _INT, [_I8_PTR]), [iterable.llvm]
        )

        def condition() -> Any:
            return self.builder.icmp_signed(
                "<", self.builder.load(index), length
            )

        def load() -> Any:
            return self.builder.call(
                self._function("lox_str_char_at", _I8_PTR, [_I8_PTR, _INT]),
                [iterable.llvm, self.builder.load(index)],
            )

        def advance() -> None:
            self.builder.store(
                self.builder.add(
                    self.builder.load(index), llvm_ir.constant(_INT, 1)
                ),
                index,
            )

        self._for_loop(stmt, TypeDesc(ValueType.STRING), condition, load, advance)

    def _for_loop(
        self,
        stmt: ForIn,
        value_type: Any,
        condition: Any,
        load: Any,
        advance: Any,
    ) -> None:
        header = llvm_ir.append_block(self._function_ir, "for.cond")
        body = llvm_ir.append_block(self._function_ir, "for.body")
        end = llvm_ir.append_block(self._function_ir, "for.end")
        self.builder.branch(header)

        self.builder = llvm_ir.builder(header)
        self.builder.cbranch(condition(), body, end)

        self.builder = llvm_ir.builder(body)
        self._scopes.append({})
        try:
            desc = value_type if isinstance(value_type, TypeDesc) else TypeDesc(value_type)
            slot = self.builder.alloca(
                self._storage_llvm_type(desc), name=stmt.name.lexeme
            )
            self.builder.store(load(), slot)
            self._scopes[-1][stmt.name.lexeme] = Binding(
                slot,
                desc.ty,
                optional=desc.optional,
                class_name=desc.class_name,
            )
            self._stmt(stmt.body)
            if not self.builder.block.is_terminated:
                advance()
                self.builder.branch(header)
        finally:
            self._scopes.pop()

        self.builder = llvm_ir.builder(end)
