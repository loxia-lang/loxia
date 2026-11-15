"""`math.*`, `Int.parse` e `Float.parse` (L6)."""

from __future__ import annotations

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
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
from src.diagnostics.codes import Code
from src.frontend.expr import Call


class MathLowering(LoweringBase):
    def _math_call(self, expr: Call) -> Value:
        assert hasattr(expr.callee, "name")
        name = expr.callee.name.lexeme
        args: list[Value] = [
            self._unwrap_operand(
                self._expr(argument),
                expr.paren.line,
                "Operand must be a number.",
                column=expr.paren.column,
                code=Code.RUNTIME_OPERANDS,
            )
            for argument in expr.arguments
        ]
        result = self.types.get(expr)
        if result is None:
            raise _unsupported("math result type", expr.paren.line)
        desc = self._type_desc(result, expr.paren.line)
        if name == "abs":
            argument = args[0]
            if argument.ty is ValueType.INT:
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
                    self._function(
                        f"lox_math_{name}", _INT, [_FLOAT, _I32, _I32]
                    ),
                    [
                        self._to_float(argument),
                        llvm_ir.constant(_I32, expr.paren.line),
                        llvm_ir.constant(_I32, expr.paren.column),
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
        raise _unsupported(f"math.{name}", expr.paren.line)

    def _math_select(
        self, expr: Call, name: str, args: list[Value], desc: TypeDesc
    ) -> Value:
        use_float = any(arg.ty is ValueType.FLOAT for arg in args) or desc.ty is ValueType.FLOAT
        values = [self._to_float(arg) if use_float else arg.llvm for arg in args]
        if name == "min":
            condition = (
                self.builder.fcmp_ordered("<", values[0], values[1])
                if use_float
                else self.builder.icmp_signed("<", values[0], values[1])
            )
            return Value(desc.ty, self.builder.select(condition, values[0], values[1]))
        if name == "max":
            condition = self.builder.fcmp_ordered(">", values[0], values[1]) if use_float else self.builder.icmp_signed(">", values[0], values[1])
            return Value(desc.ty, self.builder.select(condition, values[0], values[1]))
        low_high = self.builder.fcmp_ordered(">", values[1], values[2]) if use_float else self.builder.icmp_signed(">", values[1], values[2])
        ok = llvm_ir.append_block(self._function_ir, "clamp.ok")
        bad = llvm_ir.append_block(self._function_ir, "clamp.bad")
        self.builder.cbranch(low_high, bad, ok)
        self.builder = llvm_ir.builder(bad)
        self._poison(expr.paren, "math.clamp() requires low <= high.")
        self.builder = llvm_ir.builder(ok)
        lower = self.builder.select(
            self.builder.fcmp_ordered("<", values[0], values[1]) if use_float else self.builder.icmp_signed("<", values[0], values[1]),
            values[1],
            values[0],
        )
        upper = self.builder.select(
            self.builder.fcmp_ordered(">", lower, values[2]) if use_float else self.builder.icmp_signed(">", lower, values[2]),
            values[2],
            lower,
        )
        return Value(desc.ty, upper)

    def _parse_call(self, expr: Call, desc: TypeDesc) -> Value:
        args = [self._expr(argument) for argument in expr.arguments]
        if len(args) != 1 or args[0].ty is not ValueType.STRING:
            self._poison(expr.paren, "parse() expects a string.")
            return self._zero_desc(desc)
        function = "lox_parse_int" if desc.ty is ValueType.INT else "lox_parse_float"
        raw = self.builder.call(
            self._function(function, _ANY, [_I8_PTR]), [args[0].llvm]
        )
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
