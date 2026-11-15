"""Strings, interpolação, `str`/`repr`/`len` e display de valores."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    Value,
    ValueType,
    _unsupported,
)
from src.diagnostics.codes import Code
from src.frontend.expr import Call, InterpolatedString


class StringLowering(LoweringBase):
    def _display_pointer(self, display: str) -> Any:
        global_ = self._displays.get(display)
        if global_ is None:
            global_ = llvm_ir.cstring(
                self.module, display, f"display.{len(self._displays)}"
            )
            self._displays[display] = global_

        return llvm_ir.cstring_pointer(self.builder, global_)

    def _string_literal(self, value: str) -> Value:
        global_ = llvm_ir.string_literal(self.module, value, self._string_count)
        self._string_count += 1
        return Value(ValueType.STRING, self.builder.bitcast(global_, _I8_PTR))

    def _interpolated(self, expr: InterpolatedString) -> Value:
        pieces: list[Value] = []
        for part in expr.parts:
            if isinstance(part, str):
                if part:
                    pieces.append(self._string_literal(part))
            else:
                pieces.append(self._to_string(self._expr(part)))

        if not pieces:
            return self._string_literal("")

        result = pieces[0]
        for piece in pieces[1:]:
            result = self._concat(result, piece)

        return result

    def _to_string(self, value: Value) -> Value:
        if value.optional:
            return self._to_string_optional(value)

        match value.ty:
            case ValueType.STRING:
                return value
            case ValueType.INT:
                function = self._function("lox_str_from_int", _I8_PTR, [_INT])
                return Value(
                    ValueType.STRING, self.builder.call(function, [value.llvm])
                )
            case ValueType.FLOAT:
                function = self._function("lox_str_from_double", _I8_PTR, [_FLOAT])
                return Value(
                    ValueType.STRING, self.builder.call(function, [value.llvm])
                )
            case ValueType.BOOL:
                function = self._function("lox_str_from_bool", _I8_PTR, [_I32])
                widened = self.builder.zext(value.llvm, _I32)
                return Value(
                    ValueType.STRING, self.builder.call(function, [widened])
                )
            case ValueType.FUNCTION:
                function = self._function(
                    "lox_str_from_function", _I8_PTR, [_I8_PTR]
                )
                return Value(
                    ValueType.STRING, self.builder.call(function, [value.llvm])
                )
            case ValueType.CLASS | ValueType.INSTANCE:
                display = self._class_display(value.class_name or "?")
                text = (
                    display
                    if value.ty is ValueType.CLASS
                    else f"{display} instance"
                )
                return self._string_literal(text)
            case ValueType.ANY:
                tag = self.builder.extract_value(value.llvm, 0)
                payload = self.builder.extract_value(value.llvm, 1)
                function = self._function(
                    "lox_str_from_any", _I8_PTR, [_INT, _INT]
                )
                return Value(
                    ValueType.STRING,
                    self.builder.call(function, [tag, payload]),
                )
            case ValueType.RANGE:
                function = self._function(
                    "lox_str_from_range", _I8_PTR, [_I8_PTR]
                )
                return Value(
                    ValueType.STRING,
                    self.builder.call(function, [value.llvm]),
                )
            case ValueType.LIST:
                function = self._function(
                    "lox_str_from_list", _I8_PTR, [_I8_PTR]
                )
                return Value(
                    ValueType.STRING,
                    self.builder.call(function, [value.llvm]),
                )
            case ValueType.MAP:
                function = self._function(
                    "lox_str_from_map", _I8_PTR, [_I8_PTR]
                )
                return Value(
                    ValueType.STRING,
                    self.builder.call(function, [value.llvm]),
                )
            case ValueType.ENUM:
                function = self._function(
                    "lox_str_from_enum", _I8_PTR, [_I8_PTR]
                )
                return Value(
                    ValueType.STRING,
                    self.builder.call(function, [value.llvm]),
                )
            case ValueType.TUPLE:
                function = self._function(
                    "lox_str_from_tuple", _I8_PTR, [_I8_PTR]
                )
                return Value(
                    ValueType.STRING,
                    self.builder.call(function, [value.llvm]),
                )
            case ValueType.NIL:
                function = self._function("lox_str_nil", _I8_PTR, [])
                return Value(ValueType.STRING, self.builder.call(function, []))
            case _:
                raise _unsupported(f"String conversion for {value.ty.name}", None)

    def _to_string_optional(self, value: Value) -> Value:
        tag = self._optional_tag(value)
        some = llvm_ir.append_block(self._function_ir, "opt.str.some")
        nothing = llvm_ir.append_block(self._function_ir, "opt.str.nil")
        end = llvm_ir.append_block(self._function_ir, "opt.str.end")
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(nothing)
        nothing_value = self.builder.call(
            self._function("lox_str_nil", _I8_PTR, []), []
        )
        nothing_end = self.builder.block
        self.builder.branch(end)

        self.builder = llvm_ir.builder(some)
        some_value = self._to_string(self._optional_payload(value)).llvm
        some_end = self.builder.block
        self.builder.branch(end)

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(_I8_PTR, "opt.str")
        merged.add_incoming(nothing_value, nothing_end)
        merged.add_incoming(some_value, some_end)
        return Value(ValueType.STRING, merged)

    def _concat(self, left: Value, right: Value) -> Value:
        function = self._function("lox_str_concat", _I8_PTR, [_I8_PTR, _I8_PTR])
        return Value(
            ValueType.STRING, self.builder.call(function, [left.llvm, right.llvm])
        )

    def _repr(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1:
            self._poison(
                expr.paren,
                f"Expected 1 arguments but got {len(arguments)}.",
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.STRING)

        argument = arguments[0]
        if argument.ty is not ValueType.STRING:
            return self._to_string(argument)

        function = self._function("lox_str_quote", _I8_PTR, [_I8_PTR])
        return Value(ValueType.STRING, self.builder.call(function, [argument.llvm]))

    def _str(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1:
            self._poison(
                expr.paren,
                f"Expected 1 arguments but got {len(arguments)}.",
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.STRING)

        return self._to_string(arguments[0])

    def _len(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1:
            self._poison(
                expr.paren,
                f"Expected 1 arguments but got {len(arguments)}.",
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.INT)

        argument = arguments[0]
        if argument.ty is ValueType.LIST:
            return self._list_len(argument)
        if argument.ty is ValueType.MAP:
            return self._map_len(argument)
        if argument.ty is ValueType.TUPLE:
            return self._tuple_len(argument)
        if argument.ty is ValueType.ENUM:
            raise _unsupported("len of Enum", expr.paren.line)
        if argument.ty is not ValueType.STRING:
            raise _unsupported("len of non-String", expr.paren.line)

        function = self._function("lox_str_len", _INT, [_I8_PTR])
        return Value(ValueType.INT, self.builder.call(function, [argument.llvm]))
