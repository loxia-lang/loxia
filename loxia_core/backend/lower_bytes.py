# SPDX-License-Identifier: MIT OR Apache-2.0
"""`Bytes`: chamadas de método, namespace estático e `for-in` (ADR-0125)."""

from __future__ import annotations

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _I8_PTR,
    _I32,
    _INT,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.execution.bytes_api import BYTES_METHODS, BYTES_STATICS
from loxia_core.frontend.expr import Call, Get, Variable


class BytesLowering(LoweringBase):
    """Lowering das operações de valor de `Bytes` (tag 13)."""

    def _bytes_static(self, expr: Call) -> Value | None:
        callee = expr.callee
        if not (
            isinstance(callee, Get)
            and isinstance(callee.object, Variable)
            and callee.object.name.lexeme == "Bytes"
            and self.depths.get(callee.object) is None
        ):
            return None
        name = callee.name.lexeme
        signature = BYTES_STATICS.get(name)
        if signature is None:
            raise _unsupported(f"Bytes member '{name}'", callee.name.line)
        line = callee.name.line
        if len(expr.arguments) != len(signature.params):
            self._poison(
                expr.paren,
                self._arity_message(
                    len(signature.params), len(signature.params), len(expr.arguments)
                ),
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.BYTES)

        match name:
            case "empty":
                call = self.builder.call(
                    self._function("lox_bytes_new", _I8_PTR, [_INT]),
                    [llvm_ir.constant(_INT, 0)],
                )
                return Value(ValueType.BYTES, call)
            case "fromList":
                value = self._expr(expr.arguments[0])
                if value.ty is not ValueType.LIST:
                    raise _unsupported("Bytes.fromList argument", line)
                call = self.builder.call(
                    self._function(
                        "lox_bytes_from_list",
                        _I8_PTR,
                        [_I8_PTR, _I32, _I32],
                    ),
                    [
                        value.llvm,
                        llvm_ir.constant(_I32, expr.paren.line),
                        llvm_ir.constant(_I32, expr.paren.column),
                    ],
                )
                return Value(ValueType.BYTES, call)
            case "fromText":
                value = self._coerce(
                    self._expr(expr.arguments[0]),
                    TypeDesc(ValueType.STRING),
                    line,
                )
                call = self.builder.call(
                    self._function("lox_bytes_from_text", _I8_PTR, [_I8_PTR]),
                    [value.llvm],
                )
                return Value(ValueType.BYTES, call)
            case "fromHex" | "fromBase64":
                value = self._coerce(
                    self._expr(expr.arguments[0]),
                    TypeDesc(ValueType.STRING),
                    line,
                )
                function = "lox_bytes_from_hex" if name == "fromHex" else "lox_bytes_from_base64"
                call = self.builder.call(self._function(function, _I8_PTR, [_I8_PTR]), [value.llvm])
                return Value(ValueType.ENUM, call)
            case _:  # pragma: no cover - a tabela e o match são fechados
                raise _unsupported(f"Bytes member '{name}'", line)

    def _call_bytes_method(self, expr: Call, obj: Value) -> Value:
        callee = expr.callee
        assert isinstance(callee, Get)
        name = callee.name.lexeme
        line = callee.name.line
        column = callee.name.column
        signature = BYTES_METHODS.get(name)
        if signature is None:
            raise _unsupported(f"Bytes method '{name}'", line)
        if len(expr.arguments) != len(signature.params):
            self._poison(
                expr.paren,
                self._arity_message(
                    len(signature.params), len(signature.params), len(expr.arguments)
                ),
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.BYTES)

        match name:
            case "slice":
                start = self._coerce(self._expr(expr.arguments[0]), TypeDesc(ValueType.INT), line)
                end = self._coerce(self._expr(expr.arguments[1]), TypeDesc(ValueType.INT), line)
                call = self.builder.call(
                    self._function(
                        "lox_bytes_slice",
                        _I8_PTR,
                        [_I8_PTR, _INT, _INT, _I32, _I32],
                    ),
                    [
                        obj.llvm,
                        start.llvm,
                        end.llvm,
                        llvm_ir.constant(_I32, line),
                        llvm_ir.constant(_I32, column),
                    ],
                )
                return Value(ValueType.BYTES, call)
            case "concat":
                other = self._coerce(
                    self._expr(expr.arguments[0]),
                    TypeDesc(ValueType.BYTES),
                    line,
                )
                call = self.builder.call(
                    self._function("lox_bytes_concat", _I8_PTR, [_I8_PTR, _I8_PTR]),
                    [obj.llvm, other.llvm],
                )
                return Value(ValueType.BYTES, call)
            case "toList":
                call = self.builder.call(
                    self._function("lox_bytes_to_list", _I8_PTR, [_I8_PTR]),
                    [obj.llvm],
                )
                return Value(ValueType.LIST, call)
            case "toText":
                call = self.builder.call(
                    self._function("lox_bytes_to_text", _I8_PTR, [_I8_PTR]),
                    [obj.llvm],
                )
                return Value(ValueType.ENUM, call)
            case "toHex":
                call = self.builder.call(
                    self._function("lox_bytes_to_hex", _I8_PTR, [_I8_PTR]),
                    [obj.llvm],
                )
                return Value(ValueType.STRING, call)
            case "toBase64":
                call = self.builder.call(
                    self._function("lox_bytes_to_base64", _I8_PTR, [_I8_PTR]),
                    [obj.llvm],
                )
                return Value(ValueType.STRING, call)
            case _:  # pragma: no cover - a tabela e o match são fechados
                raise _unsupported(f"Bytes method '{name}'", line)

    def _call_optional_bytes_method(self, expr: Call, receiver: Value) -> Value:
        result_desc = self._expr_type_desc(expr, expr.paren.line)
        some = llvm_ir.append_block(self._function_ir, "bytes.opt.some")
        nothing = llvm_ir.append_block(self._function_ir, "bytes.opt.nil")
        end = llvm_ir.append_block(self._function_ir, "bytes.opt.end")
        self.builder.cbranch(self._optional_tag(receiver), some, nothing)

        self.builder = llvm_ir.builder(nothing)
        zero = self._zero_desc(result_desc)
        self.builder.branch(end)
        nothing_end = self.builder.block

        self.builder = llvm_ir.builder(some)
        inner = self._optional_payload(receiver)
        value = self._call_bytes_method(expr, inner)
        self.builder.branch(end)
        some_end = self.builder.block

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(self._storage_llvm_type(result_desc), "bytes.opt")
        merged.add_incoming(zero.llvm, nothing_end)
        merged.add_incoming(value.llvm, some_end)
        return Value(
            result_desc.ty,
            merged,
            result_desc.fn,
            result_desc.optional,
            result_desc.class_name,
            interface_name=result_desc.interface_name,
        )

    def _bytes_method_value(self, expr: Get) -> Value:
        raise _unsupported("Bytes method value", expr.name.line)
