# SPDX-License-Identifier: MIT OR Apache-2.0
"""`math.*`, `Int.parse` e `Float.parse` (L6)."""

from __future__ import annotations

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _ANY,
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.thir import TCall as Call


class MathLowering(LoweringBase):
    def _math_call(self, expr: Call) -> Value:
        assert hasattr(expr.callee, "name")
        name = expr.callee.name
        args: list[Value] = [
            self._unwrap_operand(
                self._expr(argument),
                self._line(expr.paren_span),
                "Operand must be a number.",
                column=self._column(expr.paren_span),
                code=Code.RUNTIME_OPERANDS,
            )
            for argument in expr.arguments
        ]
        if any(argument.ty is ValueType.ANY for argument in args):
            raise _unsupported("math.* with dynamic Any", self._line(expr.paren_span))
        result = expr.storage_ty
        if result is None:
            raise _unsupported("math result type", self._line(expr.paren_span))
        desc = self._type_desc(result, self._line(expr.paren_span))
        if name == "abs":
            argument = args[0]
            if argument.ty is ValueType.INT:
                if self.debug:
                    return Value(
                        ValueType.INT,
                        self.builder.call(
                            self._function("lox_math_abs_int_checked", _INT, [_INT, _I32, _I32]),
                            [
                                argument.llvm,
                                llvm_ir.constant(_I32, self._line(expr.paren_span)),
                                llvm_ir.constant(_I32, self._column(expr.paren_span)),
                            ],
                        ),
                    )
                return Value(
                    ValueType.INT,
                    self.builder.call(
                        self._function("lox_math_abs_int", _INT, [_INT]),
                        [argument.llvm],
                    ),
                )
            return Value(
                ValueType.FLOAT,
                self.builder.call(
                    self._function("lox_math_abs_float", _FLOAT, [_FLOAT]),
                    [self._to_float(argument)],
                ),
            )
        if name in {"floor", "ceil", "round", "trunc"}:
            argument = args[0]
            if argument.ty is ValueType.INT:
                return argument
            return Value(
                ValueType.INT,
                self.builder.call(
                    self._function(f"lox_math_{name}", _INT, [_FLOAT, _I32, _I32]),
                    [
                        self._to_float(argument),
                        llvm_ir.constant(_I32, self._line(expr.paren_span)),
                        llvm_ir.constant(_I32, self._column(expr.paren_span)),
                    ],
                ),
            )
        if name == "sqrt":
            return Value(
                ValueType.FLOAT,
                self.builder.call(
                    self._function("lox_math_sqrt", _FLOAT, [_FLOAT]),
                    [self._to_float(args[0])],
                ),
            )
        if name in {"min", "max", "clamp"}:
            return self._math_select(expr, name, args, desc)
        raise _unsupported(f"math.{name}", self._line(expr.paren_span))

    def _math_select(self, expr: Call, name: str, args: list[Value], desc: TypeDesc) -> Value:
        use_float = any(arg.ty is ValueType.FLOAT for arg in args) or desc.ty is ValueType.FLOAT
        values = [self._to_float(arg) if use_float else arg.llvm for arg in args]
        if use_float:
            if name == "min":
                call = self.builder.call(
                    self._function("lox_math_min", _FLOAT, [_FLOAT, _FLOAT]),
                    values,
                )
                return Value(ValueType.FLOAT, call)
            if name == "max":
                call = self.builder.call(
                    self._function("lox_math_max", _FLOAT, [_FLOAT, _FLOAT]),
                    values,
                )
                return Value(ValueType.FLOAT, call)
            call = self.builder.call(
                self._function(
                    "lox_math_clamp",
                    _FLOAT,
                    [_FLOAT, _FLOAT, _FLOAT, _I32, _I32],
                ),
                [
                    *values,
                    llvm_ir.constant(_I32, self._line(expr.paren_span)),
                    llvm_ir.constant(_I32, self._column(expr.paren_span)),
                ],
            )
            return Value(ValueType.FLOAT, call)

        if name == "min":
            condition = self.builder.icmp_signed("<", values[0], values[1])
            return Value(desc.ty, self.builder.select(condition, values[0], values[1]))
        if name == "max":
            condition = self.builder.icmp_signed(">", values[0], values[1])
            return Value(desc.ty, self.builder.select(condition, values[0], values[1]))
        low_high = self.builder.icmp_signed(">", values[1], values[2])
        ok = self._control.new_block(self._function_ir, "clamp.ok")
        bad = self._control.new_block(self._function_ir, "clamp.bad")
        self.builder.cbranch(low_high, bad, ok)
        self.builder = llvm_ir.builder(bad)
        self._poison(expr.paren_span, "math.clamp() requires low <= high.")
        self.builder = llvm_ir.builder(ok)
        lower = self.builder.select(
            self.builder.icmp_signed("<", values[0], values[1]),
            values[1],
            values[0],
        )
        upper = self.builder.select(
            self.builder.icmp_signed(">", lower, values[2]),
            values[2],
            lower,
        )
        return Value(desc.ty, upper)

    def _parse_call(self, expr: Call, desc: TypeDesc) -> Value:
        args = [self._expr(argument) for argument in expr.arguments]
        if len(args) != 1 or args[0].ty is not ValueType.STRING:
            name = "Int.parse()" if desc.ty is ValueType.INT else "Float.parse()"
            self._poison(expr.paren_span, f"{name} expects a string.")
            return self._zero_desc(desc)
        function = "lox_parse_int" if desc.ty is ValueType.INT else "lox_parse_float"
        raw = self.builder.call(self._function(function, _ANY, [_I8_PTR]), [args[0].llvm])
        tag = self.builder.extract_value(raw, 0)
        payload = self.builder.extract_value(raw, 1)
        storage = self._storage_llvm_type(desc)
        result = llvm_ir.zero_value(storage)
        present = self.builder.icmp_signed("!=", tag, llvm_ir.constant(_INT, 0))
        result = self.builder.insert_value(result, present, 0)
        if desc.ty is ValueType.FLOAT:
            payload = self.builder.bitcast(payload, _FLOAT)
        result = self.builder.insert_value(result, payload, 1)
        return Value(desc.ty, result, optional=True)
