# SPDX-License-Identifier: MIT OR Apache-2.0
"""Chamadas, métodos, classes chamáveis e curto-circuito de `?.`."""

from __future__ import annotations

from typing import Any, cast

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _CLOSURE,
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    Binding,
    FnSig,
    FunctionInfo,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.execution.primitives import PRIMITIVE_BY_LOX
from loxia_core.frontend.expr import Call, Expr, Get, Variable
from loxia_core.frontend.tokens import Token


class CallLowering(LoweringBase):
    def _primitive_call(self, primitive: Any, expr: Call) -> Value:
        params = [self._type_desc(param, expr.paren.line) for param in primitive.params]
        if len(expr.arguments) != len(params):
            self._poison(
                expr.paren.line,
                f"Expected {len(params)} arguments but got {len(expr.arguments)}.",
            )
            return Value(ValueType.NIL)

        arguments = [
            self._coerce(self._expr(argument), desc, expr.paren.line)
            for argument, desc in zip(expr.arguments, params, strict=True)
        ]
        result = self._type_desc(primitive.result, expr.paren.line)
        param_types = [self._param_llvm_type(desc) for desc in params]
        call_arguments = [
            self._arg_llvm(argument, desc) for argument, desc in zip(arguments, params, strict=True)
        ]
        if primitive.site:
            # Primitivas que podem falhar recebem o call site para o panic.
            param_types.extend([_I32, _I32])
            call_arguments.extend(
                [
                    llvm_ir.constant(_I32, expr.paren.line),
                    llvm_ir.constant(_I32, expr.paren.column),
                ]
            )
        function = self._function(
            primitive.c_symbol,
            _VOID if result.ty is ValueType.NIL else self._storage_llvm_type(result),
            param_types,
        )
        call = self.builder.call(function, call_arguments)
        return Value(
            result.ty,
            call,
            result.fn,
            result.optional,
            result.class_name,
            interface_name=result.interface_name,
        )

    def _call(self, expr: Call) -> Value:
        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and self.depths.get(expr.callee.object) is None
        ):
            primitive = PRIMITIVE_BY_LOX.get(
                f"{expr.callee.object.name.lexeme}.{expr.callee.name.lexeme}"
            )
            if primitive is not None:
                return self._primitive_call(primitive, expr)

        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme in {"Int", "Float"}
            and expr.callee.name.lexeme == "parse"
            and self.depths.get(expr.callee.object) is None
        ):
            return self._parse_call(expr, self._expr_type_desc(expr, expr.paren.line))
        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme == "math"
            and self.depths.get(expr.callee.object) is None
        ):
            return self._math_call(expr)
        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme == "Bytes"
            and self.depths.get(expr.callee.object) is None
        ):
            result = self._bytes_static(expr)
            if result is not None:
                return cast("Value", result)
        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme in {"Int", "Float", "math"}
            and self.depths.get(expr.callee.object) is None
        ):
            raise _unsupported("Native modules in the backend", expr.paren.line)

        if isinstance(expr.callee, Variable):
            generic = self._generic_fns.get(expr.callee.name.lexeme)
            if generic is not None:
                return self._call_generic(generic, expr)
            if expr.callee.name.lexeme in self._generic_class_nodes:
                return self._call_generic_class(expr.callee.name.lexeme, expr)

        if (
            isinstance(expr.callee, Get)
            and isinstance(expr.callee.object, Variable)
            and expr.callee.object.name.lexeme in self._enum_layouts
            and self.depths.get(expr.callee.object) is None
        ):
            return self._enum_construct(expr)

        precomputed: Value | None = None
        if isinstance(expr.callee, Get) and not expr.callee.optional:
            # Avalia o receptor uma vez só: cadeias como `a.m().m()` não podem
            # executar `a.m()` de novo no despacho de lista/mapa.
            precomputed = self._narrowed(
                expr.callee.object,
                self._expr(expr.callee.object),
                expr.callee.name.line,
            )
            if precomputed.ty is ValueType.LIST:
                return self._call_list_method(expr, precomputed)
            if precomputed.ty is ValueType.MAP:
                return self._call_map_method(expr, precomputed)
            if precomputed.ty is ValueType.BYTES:
                return cast("Value", self._call_bytes_method(expr, precomputed))
        elif isinstance(expr.callee, Get):
            receiver = self._expr(expr.callee.object)
            if receiver.ty is ValueType.LIST:
                return self._call_list_method(expr, receiver)
            if receiver.ty is ValueType.MAP:
                return self._call_map_method(expr, receiver)
            if receiver.ty is ValueType.BYTES:
                if receiver.optional:
                    return cast("Value", self._call_optional_bytes_method(expr, receiver))
                return cast("Value", self._call_bytes_method(expr, receiver))

        if isinstance(expr.callee, Variable):
            name = expr.callee.name.lexeme
            if name == "print":
                return self._print_call(expr)
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
            primitive = PRIMITIVE_BY_LOX.get(name)
            if primitive is not None:
                return self._primitive_call(primitive, expr)
        if isinstance(expr.callee, Variable):
            depth = self.depths.get(expr.callee)
            if depth is not None or expr.callee.name.lexeme in self._globals:
                early = self._lookup(expr.callee, expr.callee.name.lexeme, expr.callee.name.line)
                if early.ty is ValueType.CLASS:
                    return self._call_class(early, expr)

        info: FunctionInfo | None = None
        binding: Binding | None = None
        if isinstance(expr.callee, Variable):
            depth = self.depths.get(expr.callee)
            if depth is not None or expr.callee.name.lexeme in self._globals:
                binding = self._lookup(expr.callee, expr.callee.name.lexeme, expr.callee.name.line)
                if binding.function is not None:
                    info = binding.function

        if info is not None:
            assert binding is not None
            assert isinstance(expr.callee, Variable)
            callee = self._load_binding(binding)
            if not callee.optional:
                callee = self._guard_closure(
                    callee,
                    expr.callee.name.lexeme,
                    expr.callee.name.line,
                    expr.callee.name.column,
                )
        elif isinstance(expr.callee, Get) and precomputed is not None:
            callee = self._get_instance(precomputed, expr.callee)
        else:
            callee = self._narrowed(expr.callee, self._expr(expr.callee), expr.paren.line)

        if callee.generic is not None:
            callee = self._call_generic_lambda(callee, expr)

        if callee.ty is ValueType.NIL:
            # `nil?.m(args)` é nil e não avalia os argumentos.
            return Value(ValueType.NIL)

        if callee.ty is not ValueType.FUNCTION or callee.sig is None:
            self._poison(
                expr.paren,
                "Can only call functions and classes.",
                code=Code.RUNTIME_NOT_CALLABLE,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0), error=True)

        if callee.optional:
            return self._call_optional(callee, expr)

        if callee.function is None:
            # Slot de função sem inicializador é a sentinela do runtime: chamar
            # antes de atribuir é R1001, como `nil(...)` no tree-walk.
            callee = self._guard_uninitialized_function(callee, expr.paren)

        arguments = [self._expr(argument) for argument in expr.arguments]
        effective = info if info is not None else callee.function
        sig = effective.fn_sig if effective is not None else callee.sig
        assert sig is not None
        prepared = self._prepare_call_arguments(
            sig,
            effective,
            arguments,
            expr.spread,
            expr.paren,
            sources=list(expr.arguments),
        )
        if prepared is None:
            return self._zero_desc(sig.ret)
        arguments = prepared

        fnptr = self._closure_field(callee, 0)
        env = self._closure_field(callee, 1)
        function_type = llvm_ir.function_pointer(
            _VOID if sig.ret.ty is ValueType.NIL else self._storage_llvm_type(sig.ret),
            [_I8_PTR, *[self._param_llvm_type(param) for param in sig.params]],
        )
        self._set_call_site(expr.paren)
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [
                env,
                *[
                    self._arg_llvm(argument, param)
                    for argument, param in zip(arguments, sig.params, strict=True)
                ],
            ],
        )
        if sig.ret.ty is ValueType.NIL:
            return Value(ValueType.NIL)
        return Value(
            sig.ret.ty,
            call,
            sig.ret.fn,
            sig.ret.optional,
            sig.ret.class_name,
            interface_name=sig.ret.interface_name,
        )

    def _prepare_call_arguments(
        self,
        sig: FnSig,
        info: FunctionInfo | None,
        values: list[Value],
        spread: bool,
        token: Token,
        sources: list[Expr] | None = None,
    ) -> list[Value] | None:
        fixed = len(sig.params) - 1 if sig.variadic else len(sig.params)
        count = len(values)
        # `sources` acompanha `values` (expressão de cada argumento) para que a
        # coerção consiga reconhecer um argumento `<error>` adiado — o panic site
        # já foi emitido e o valor é um zero de recheio (I1, ver `_coerce`).
        args = list(sources) if sources is not None else None

        def coerce(index: int, value: Value, expected: TypeDesc) -> Value:
            source = args[index] if args is not None and index < len(args) else None
            return self._coerce(value, expected, token.line, source=source)

        if spread:
            if not sig.variadic:
                self._poison(
                    token,
                    "Spread arguments are only supported for variadic functions.",
                    code=Code.RUNTIME_ARITY,
                )
                return None
            if count != fixed + 1:
                self._poison(
                    token,
                    "Spread arguments only fill the variadic parameter; "
                    "pass the fixed parameters explicitly.",
                    code=Code.RUNTIME_ARITY,
                )
                return None
            rest = values[-1]
            if rest.optional:
                rest = self._unwrap(rest, token.line, "Spread argument can't be nil.")
            if rest.ty is not ValueType.LIST:
                self._poison(
                    token,
                    "Spread argument must be a list.",
                    code=Code.RUNTIME_OPERANDS,
                )
                return None
            fixed_values = [
                coerce(index, value, sig.params[index])
                for index, value in enumerate(values[:fixed])
            ]
            return [*fixed_values, rest]

        if not sig.variadic:
            if not sig.min_params <= count <= len(sig.params):
                self._poison(
                    token,
                    self._arity_message(sig.min_params, len(sig.params), count),
                    code=Code.RUNTIME_ARITY,
                )
                return None
            if info is not None:
                for index in range(count, len(sig.params)):
                    default = info.params[index].default
                    assert default is not None
                    values.append(self._expr(default))
                    if args is not None:
                        args.append(default)
            elif count < len(sig.params):
                # Sem `FunctionInfo` não há como rebaixar a expressão do default:
                # recusa declarada (nunca `zip` desencontrado/lowering silencioso).
                raise _unsupported("Default parameters in indirect function calls", token.line)
            return [coerce(index, value, sig.params[index]) for index, value in enumerate(values)]

        if count < sig.min_params:
            self._poison(
                token,
                f"Expected at least {sig.min_params} arguments but got {count}.",
                code=Code.RUNTIME_ARITY,
            )
            return None

        fixed_values = values[:fixed]
        if len(fixed_values) < fixed and info is not None:
            for index in range(len(fixed_values), fixed):
                default = info.params[index].default
                assert default is not None
                fixed_values.append(self._expr(default))
                if args is not None:
                    args.append(default)
        if len(fixed_values) < fixed and info is None:
            raise _unsupported("Default parameters in indirect function calls", token.line)
        if len(fixed_values) != fixed:
            self._poison(
                token,
                self._arity_message(sig.min_params, fixed, count),
                code=Code.RUNTIME_ARITY,
            )
            return None

        fixed_values = [
            coerce(index, value, sig.params[index]) for index, value in enumerate(fixed_values)
        ]
        element = sig.vararg_element
        assert element is not None
        raw = self.builder.call(self._function("lox_list_new", _I8_PTR, []), [])
        for offset, value in enumerate(values[fixed:]):
            coerced = coerce(fixed + offset, value, element)
            boxed = self._box_value(coerced, token.line)
            self.builder.call(
                self._function("lox_list_push", _I8_PTR, [_I8_PTR, _INT, _INT]),
                [
                    raw,
                    self.builder.extract_value(boxed.llvm, 0),
                    self.builder.extract_value(boxed.llvm, 1),
                ],
            )
        return [*fixed_values, Value(ValueType.LIST, raw)]

    def _guard_uninitialized_function(self, callee: Value, token: Token) -> Value:
        """Rejeita a sentinela de função não inicializada no site da chamada."""
        is_nil = self.builder.call(
            self._function("lox_function_is_nil", _I32, [_I8_PTR]),
            [callee.llvm],
        )
        uninitialized = self.builder.icmp_signed("!=", is_nil, llvm_ir.constant(_I32, 0))
        bad = self._control.new_block(self._function_ir, "fn.uninitialized")
        ok = self._control.new_block(self._function_ir, "fn.initialized")
        self.builder.cbranch(uninitialized, bad, ok)

        self.builder = llvm_ir.builder(bad)
        self._poison(
            token,
            "Can only call functions and classes.",
            code=Code.RUNTIME_NOT_CALLABLE,
        )

        self.builder = llvm_ir.builder(ok)
        return callee

    def _call_optional(self, callee: Value, expr: Call) -> Value:
        sig = callee.sig
        assert sig is not None
        count = len(expr.arguments)
        if not sig.variadic:
            if sig.min_params != len(sig.params):
                raise _unsupported(
                    "Default parameters in optional function calls",
                    expr.paren.line,
                )
            if count != len(sig.params):
                self._poison(
                    expr.paren,
                    self._arity_message(len(sig.params), len(sig.params), count),
                    code=Code.RUNTIME_ARITY,
                )
                return self._zero_desc(sig.ret)

        result = self._expr_type_desc(expr, expr.paren.line)
        if not result.optional and result.ty is not ValueType.NIL:
            result = TypeDesc(result.ty, result.fn, True, result.class_name)

        some = self._control.new_block(self._function_ir, "call.some")
        nothing = self._control.new_block(self._function_ir, "call.nil")
        end = self._control.new_block(self._function_ir, "call.end")
        tag = self._optional_tag(callee)
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(some)
        payload = self._optional_payload(callee)
        if sig.variadic:
            values = [self._expr(argument) for argument in expr.arguments]
            prepared = self._prepare_call_arguments(
                sig,
                callee.function,
                values,
                expr.spread,
                expr.paren,
                sources=list(expr.arguments),
            )
            if prepared is None:
                raise _unsupported(
                    "Variadic optional call with invalid arguments",
                    expr.paren.line,
                )
            arguments = prepared
        else:
            arguments = [
                self._coerce(
                    self._expr(argument),
                    expected,
                    expr.paren.line,
                    source=argument,
                )
                for argument, expected in zip(expr.arguments, sig.params, strict=True)
            ]
        fnptr = self._closure_field(payload, 0)
        env = self._closure_field(payload, 1)
        function_type = llvm_ir.function_pointer(
            _VOID if sig.ret.ty is ValueType.NIL else self._storage_llvm_type(sig.ret),
            [_I8_PTR, *[self._param_llvm_type(param) for param in sig.params]],
        )
        self._set_call_site(expr.paren)
        call = self.builder.call(
            self.builder.bitcast(fnptr, function_type),
            [
                env,
                *[
                    self._arg_llvm(argument, param)
                    for argument, param in zip(arguments, sig.params, strict=True)
                ],
            ],
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
                    interface_name=sig.ret.interface_name,
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

        merged = self.builder.phi(self._storage_llvm_type(result), "call.value")
        merged.add_incoming(value.llvm, some_end)
        merged.add_incoming(zero.llvm, nothing_end)
        return Value(
            result.ty,
            merged,
            result.fn,
            True,
            result.class_name,
            interface_name=result.interface_name,
        )

    def _call_class(self, binding: Binding, expr: Call) -> Value:
        name = binding.class_name or ""
        layout = self._classes.get(binding.layout_key or name)
        if layout is None:
            raise _unsupported("Class construction", expr.paren.line)

        class_ptr = self._load_binding(binding)
        class_ptr = self._guard_closure(class_ptr, name, expr.paren.line, expr.paren.column)

        arguments = [self._expr(argument) for argument in expr.arguments]
        if layout.synthetic_exception:
            if len(arguments) != 1:
                self._poison(
                    expr.paren,
                    self._arity_message(1, 1, len(arguments)),
                    code=Code.RUNTIME_ARITY,
                )
                return self._zero(ValueType.INSTANCE)
            message = self._coerce(
                arguments[0],
                TypeDesc(ValueType.STRING),
                expr.paren.line,
            )
            call = self.builder.call(layout.ctor, [message.llvm])
            return Value(ValueType.INSTANCE, call, class_name=name)

        init = layout.effective_init()
        minimum = 0 if init is None else init.fn_sig.min_params
        maximum = 0 if init is None else len(init.fn_sig.params)
        count = len(arguments)
        if not minimum <= count <= maximum:
            self._poison(
                expr.paren,
                self._arity_message(minimum, maximum, count),
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.INSTANCE)

        if init is not None:
            for index in range(count, maximum):
                default = init.params[index].default
                assert default is not None
                arguments.append(self._expr(default))
            arguments = [
                self._coerce(argument, expected, expr.paren.line)
                for argument, expected in zip(arguments, init.fn_sig.params, strict=True)
            ]

        call_args = (
            [
                self._arg_llvm(argument, param)
                for argument, param in zip(arguments, init.fn_sig.params, strict=True)
            ]
            if init is not None
            else []
        )
        if binding.layout_key is not None:
            call_args.insert(0, class_ptr.llvm)
        self._set_call_site(expr.paren)
        call = self.builder.call(layout.ctor, call_args)
        return Value(ValueType.INSTANCE, call, class_name=name)

    def _closure_field(self, closure: Value, index: int) -> Any:
        struct_ = self.builder.bitcast(closure.llvm, _CLOSURE.as_pointer())
        field = self.builder.gep(
            struct_,
            [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
        )
        return self.builder.load(field)

    def _print_call(self, expr: Call) -> Value:
        arguments = [self._expr(argument) for argument in expr.arguments]
        if len(arguments) != 1:
            self._poison(
                expr.paren,
                f"Expected 1 arguments but got {len(arguments)}.",
                code=Code.RUNTIME_ARITY,
            )
            return self._zero(ValueType.NIL)

        value = arguments[0]
        if value.optional:
            self._print_optional(value)
        else:
            self._print_value(value)
        return self._zero(ValueType.NIL)

    def _arity_message(self, minimum: int, maximum: int, count: int) -> str:
        if minimum == maximum:
            return f"Expected {minimum} arguments but got {count}."
        if count < minimum:
            return f"Expected at least {minimum} arguments but got {count}."
        return f"Expected {minimum} to {maximum} arguments but got {count}."
