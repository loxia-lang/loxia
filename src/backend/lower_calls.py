"""Chamadas, métodos, classes chamáveis e curto-circuito de `?.`."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _CLOSURE,
    _I8_PTR,
    _I32,
    _VOID,
    Binding,
    FunctionInfo,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.frontend.expr import Call, Get, Variable


class CallLowering(LoweringBase):
    def _call(self, expr: Call) -> Value:
        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme in {"Int", "Float"}
            and expr.callee.name.lexeme == "parse"
        ):
            return self._parse_call(
                expr, self._expr_type_desc(expr, expr.paren.line)
            )
        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme == "math"
        ):
            return self._math_call(expr)
        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme in {"Int", "Float", "math"}
        ):
            raise _unsupported("Native modules in the backend", expr.paren.line)

        if isinstance(expr.callee, Variable):
            generic = self._generic_fns.get(expr.callee.name.lexeme)
            if generic is not None:
                return self._call_generic(generic, expr)
            if expr.callee.name.lexeme in self._generic_class_by_source:
                return self._call_generic_class(
                    expr.callee.name.lexeme, expr
                )

        if isinstance(expr.callee, Get):
            receiver = self._expr(expr.callee.object)
            if receiver.ty is ValueType.LIST:
                return self._call_list_method(expr, receiver)
            if receiver.ty is ValueType.MAP:
                return self._call_map_method(expr, receiver)

        if isinstance(expr.callee, Variable):
            name = expr.callee.name.lexeme
            if name == "len":
                return self._len(expr)
            if name == "str":
                return self._str(expr)
            if name == "repr":
                return self._repr(expr)
            if name == "range":
                return self._range_call(expr)
            if name == "chars":
                return self._chars(expr)

        if isinstance(expr.callee, Variable):
            depth = self.depths.get(expr.callee)
            if depth is not None or expr.callee.name.lexeme in self._globals:
                early = self._lookup(
                    expr.callee, expr.callee.name.lexeme, expr.callee.name.line
                )
                if early.ty is ValueType.CLASS:
                    return self._call_class(early, expr)

        info: FunctionInfo | None = None
        binding: Binding | None = None
        if isinstance(expr.callee, Variable):
            depth = self.depths.get(expr.callee)
            if depth is not None or expr.callee.name.lexeme in self._globals:
                binding = self._lookup(
                    expr.callee, expr.callee.name.lexeme, expr.callee.name.line
                )
                if binding.function is not None:
                    info = binding.function

        if info is not None:
            assert binding is not None
            assert isinstance(expr.callee, Variable)
            callee = self._load_binding(binding)
            callee = self._guard_closure(
                callee, expr.callee.name.lexeme, expr.callee.name.line
            )
        else:
            callee = self._expr(expr.callee)

        if callee.ty is ValueType.NIL:
            # `nil?.m(args)` é nil e não avalia os argumentos.
            return Value(ValueType.NIL)

        if callee.ty is not ValueType.FUNCTION or callee.sig is None:
            self._poison(expr.paren.line, "Can only call functions and classes.")
            return self._zero(ValueType.INT)

        if callee.optional:
            return self._call_optional(callee, expr)

        arguments = [self._expr(argument) for argument in expr.arguments]
        sig = info.fn_sig if info is not None else callee.sig
        count = len(arguments)

        minimum = sig.min_params
        maximum = len(sig.params)
        if not minimum <= count <= maximum:
            self._poison(expr.paren.line, self._arity_message(minimum, maximum, count))
            return self._zero_desc(sig.ret)

        if info is not None:
            for index in range(count, maximum):
                default = info.params[index].default
                assert default is not None
                arguments.append(self._expr(default))

        arguments = [
            self._coerce(argument, expected, expr.paren.line)
            for argument, expected in zip(arguments, sig.params, strict=True)
        ]

        fnptr = self._closure_field(callee, 0)
        env = self._closure_field(callee, 1)
        function_type = llvm_ir.function_pointer(
            _VOID
            if sig.ret.ty is ValueType.NIL
            else self._storage_llvm_type(sig.ret),
            [_I8_PTR, *[self._storage_llvm_type(param) for param in sig.params]],
        )
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [env, *[argument.llvm for argument in arguments]],
        )
        if sig.ret.ty is ValueType.NIL:
            return Value(ValueType.NIL)
        return Value(
            sig.ret.ty,
            call,
            sig.ret.fn,
            sig.ret.optional,
            sig.ret.class_name,
        )

    def _call_optional(self, callee: Value, expr: Call) -> Value:
        sig = callee.sig
        assert sig is not None
        count = len(expr.arguments)
        if sig.min_params != len(sig.params):
            raise _unsupported(
                "Default parameters in optional function calls",
                expr.paren.line,
            )
        if count != len(sig.params):
            self._poison(
                expr.paren.line,
                self._arity_message(len(sig.params), len(sig.params), count),
            )
            return self._zero_desc(sig.ret)

        result = self._expr_type_desc(expr, expr.paren.line)
        if not result.optional and result.ty is not ValueType.NIL:
            result = TypeDesc(
                result.ty, result.fn, True, result.class_name
            )

        some = llvm_ir.append_block(self._function_ir, "call.some")
        nothing = llvm_ir.append_block(self._function_ir, "call.nil")
        end = llvm_ir.append_block(self._function_ir, "call.end")
        tag = self._optional_tag(callee)
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(some)
        payload = self._optional_payload(callee)
        arguments = [
            self._coerce(
                self._expr(argument), expected, expr.paren.line
            )
            for argument, expected in zip(
                expr.arguments, sig.params, strict=True
            )
        ]
        fnptr = self._closure_field(payload, 0)
        env = self._closure_field(payload, 1)
        function_type = llvm_ir.function_pointer(
            _VOID
            if sig.ret.ty is ValueType.NIL
            else self._storage_llvm_type(sig.ret),
            [_I8_PTR, *[self._storage_llvm_type(param) for param in sig.params]],
        )
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [env, *[argument.llvm for argument in arguments]],
        )
        if sig.ret.ty is ValueType.NIL:
            self.builder.branch(end)
        else:
            value = self._coerce(
                Value(
                    sig.ret.ty,
                    call,
                    sig.ret.fn,
                    sig.ret.optional,
                    sig.ret.class_name,
                ),
                result,
                expr.paren.line,
            )
            self.builder.branch(end)
        some_end = self.builder.block

        self.builder = llvm_ir.builder(nothing)
        zero = self._zero_desc(result)
        self.builder.branch(end)
        nothing_end = self.builder.block

        self.builder = llvm_ir.builder(end)
        if sig.ret.ty is ValueType.NIL:
            return Value(ValueType.NIL)

        merged = self.builder.phi(
            self._storage_llvm_type(result), "call.value"
        )
        merged.add_incoming(value.llvm, some_end)
        merged.add_incoming(zero.llvm, nothing_end)
        return Value(
            result.ty,
            merged,
            result.fn,
            True,
            result.class_name,
        )

    def _call_class(self, binding: Binding, expr: Call) -> Value:
        name = binding.class_name or ""
        layout = self._classes.get(binding.layout_key or name)
        if layout is None:
            raise _unsupported("Class construction", expr.paren.line)

        class_ptr = self._load_binding(binding)
        class_ptr = self._guard_closure(class_ptr, name, expr.paren.line)

        arguments = [self._expr(argument) for argument in expr.arguments]
        init = layout.effective_init()
        minimum = 0 if init is None else init.fn_sig.min_params
        maximum = 0 if init is None else len(init.fn_sig.params)
        count = len(arguments)
        if not minimum <= count <= maximum:
            self._poison(
                expr.paren.line, self._arity_message(minimum, maximum, count)
            )
            return self._zero(ValueType.INSTANCE)

        if init is not None:
            for index in range(count, maximum):
                default = init.params[index].default
                assert default is not None
                arguments.append(self._expr(default))
            arguments = [
                self._coerce(argument, expected, expr.paren.line)
                for argument, expected in zip(
                    arguments, init.fn_sig.params, strict=True
                )
            ]

        call_args = [argument.llvm for argument in arguments]
        if binding.layout_key is not None:
            call_args.insert(0, class_ptr.llvm)
        call = self.builder.call(layout.ctor, call_args)
        return Value(ValueType.INSTANCE, call, class_name=name)

    def _closure_field(self, closure: Value, index: int) -> Any:
        struct_ = self.builder.bitcast(closure.llvm, _CLOSURE.as_pointer())
        field = self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
        )
        return self.builder.load(field)

    def _arity_message(self, minimum: int, maximum: int, count: int) -> str:
        if minimum == maximum:
            return f"Expected {minimum} arguments but got {count}."
        if count < minimum:
            return f"Expected at least {minimum} arguments but got {count}."
        return f"Expected {minimum} to {maximum} arguments but got {count}."
