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
from loxia_core.diagnostics.diagnostic import Span
from loxia_core.execution.primitives import PRIMITIVE_BY_LOX
from loxia_core.thir import (
    Ref,
    Storage,
    TExpr,
)
from loxia_core.thir import (
    TCall as Call,
)
from loxia_core.thir import (
    TGet as Get,
)
from loxia_core.thir import (
    TVar as Variable,
)


class CallLowering(LoweringBase):
    def _primitive_call(self, primitive: Any, expr: Call) -> Value:
        params = [self._type_desc(param, self._line(expr.paren_span)) for param in primitive.params]
        if len(expr.arguments) != len(params):
            self._poison(
                expr.paren_span,
                f"Expected {len(params)} arguments but got {len(expr.arguments)}.",
            )
            return Value(ValueType.NIL)

        arguments = [
            self._coerce(self._expr(argument), desc, self._line(expr.paren_span))
            for argument, desc in zip(expr.arguments, params, strict=True)
        ]
        result = self._type_desc(primitive.result, self._line(expr.paren_span))
        param_types = [self._param_llvm_type(desc) for desc in params]
        call_arguments = [
            self._arg_llvm(argument, desc) for argument, desc in zip(arguments, params, strict=True)
        ]
        if primitive.site:
            # Primitivas que podem falhar recebem o call site para o panic.
            param_types.extend([_I32, _I32])
            call_arguments.extend(
                [
                    llvm_ir.constant(_I32, self._line(expr.paren_span)),
                    llvm_ir.constant(_I32, self._column(expr.paren_span)),
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
        callee = expr.callee
        paren_line = self._line(expr.paren_span)
        receiver_name = self._global_ref_name(callee.receiver) if isinstance(callee, Get) else None

        if isinstance(callee, Get) and receiver_name is not None:
            primitive = PRIMITIVE_BY_LOX.get(f"{receiver_name}.{callee.name}")
            if primitive is not None:
                return self._primitive_call(primitive, expr)

        if receiver_name in {"Int", "Float"} and isinstance(callee, Get) and callee.name == "parse":
            return self._parse_call(expr, self._expr_type_desc(expr, paren_line))
        if receiver_name == "math":
            return self._math_call(expr)
        if receiver_name == "Bytes":
            result = self._bytes_static(expr)
            if result is not None:
                return cast("Value", result)
        if receiver_name in {"Int", "Float", "math"}:
            raise _unsupported("Native modules in the backend", paren_line)

        if isinstance(callee, Variable):
            generic = self._generic_fns.get(callee.ref.name)
            if generic is not None:
                return self._call_generic(generic, expr)
            if callee.ref.name in self._generic_class_nodes:
                return self._call_generic_class(callee.ref.name, expr)

        if isinstance(callee, Get) and receiver_name in self._enum_layouts:
            return self._enum_construct(expr)

        precomputed: Value | None = None
        if isinstance(callee, Get) and not callee.optional:
            # Avalia o receptor uma vez só: cadeias como `a.m().m()` não podem
            # executar `a.m()` de novo no despacho de lista/mapa.
            precomputed = self._narrowed(
                callee.receiver,
                self._expr(callee.receiver),
                self._line(callee.name_span),
            )
            if precomputed.ty is ValueType.LIST:
                return self._call_list_method(expr, precomputed)
            if precomputed.ty is ValueType.MAP:
                return self._call_map_method(expr, precomputed)
            if precomputed.ty is ValueType.BYTES:
                return cast("Value", self._call_bytes_method(expr, precomputed))
        elif isinstance(callee, Get):
            receiver = self._expr(callee.receiver)
            if receiver.ty is ValueType.LIST:
                return self._call_list_method(expr, receiver)
            if receiver.ty is ValueType.MAP:
                return self._call_map_method(expr, receiver)
            if receiver.ty is ValueType.BYTES:
                if receiver.optional:
                    return cast("Value", self._call_optional_bytes_method(expr, receiver))
                return cast("Value", self._call_bytes_method(expr, receiver))

        if isinstance(callee, Variable):
            name = callee.ref.name
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

        if isinstance(callee, Variable) and self._is_bound_ref(callee.ref):
            early = self._lookup(callee.ref, self._line(callee.span))
            if early.ty is ValueType.CLASS:
                return self._call_class(early, expr)

        info: FunctionInfo | None = None
        binding: Binding | None = None
        if isinstance(callee, Variable) and self._is_bound_ref(callee.ref):
            binding = self._lookup(callee.ref, self._line(callee.span))
            if binding.function is not None:
                info = binding.function

        if info is not None:
            assert binding is not None
            assert isinstance(callee, Variable)
            callee_value = self._load_binding(binding)
            if not callee_value.optional:
                callee_value = self._guard_closure(
                    callee_value,
                    callee.ref.name,
                    self._line(callee.span),
                    self._column(callee.span),
                )
        elif isinstance(callee, Get) and precomputed is not None:
            callee_value = self._get_instance(precomputed, callee)
        else:
            callee_value = self._narrowed(callee, self._expr(callee), paren_line)

        if callee_value.generic is not None:
            callee_value = self._call_generic_lambda(callee_value, expr)

        if callee_value.ty is ValueType.NIL:
            # `nil?.m(args)` é nil e não avalia os argumentos.
            return Value(ValueType.NIL)

        if callee_value.ty is not ValueType.FUNCTION or callee_value.sig is None:
            self._poison(
                expr.paren_span,
                "Can only call functions and classes.",
                code=Code.RUNTIME_NOT_CALLABLE,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0), error=True)

        if callee_value.optional:
            return self._call_optional(callee_value, expr)

        if callee_value.function is None:
            # Slot de função sem inicializador é a sentinela do runtime: chamar
            # antes de atribuir é R1001, como `nil(...)` no tree-walk.
            callee_value = self._guard_uninitialized_function(callee_value, expr.paren_span)

        arguments = [self._expr(argument) for argument in expr.arguments]
        effective = info if info is not None else callee_value.function
        sig = effective.fn_sig if effective is not None else callee_value.sig
        assert sig is not None
        prepared = self._prepare_call_arguments(
            sig,
            effective,
            arguments,
            expr.spread,
            expr.paren_span,
            sources=list(expr.arguments),
        )
        if prepared is None:
            return self._zero_desc(sig.ret)
        arguments = prepared

        fnptr = self._closure_field(callee_value, 0)
        env = self._closure_field(callee_value, 1)
        function_type = llvm_ir.function_pointer(
            _VOID if sig.ret.ty is ValueType.NIL else self._storage_llvm_type(sig.ret),
            [_I8_PTR, *[self._param_llvm_type(param) for param in sig.params]],
        )
        self._set_call_site(expr.paren_span)
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

    def _is_bound_ref(self, ref: Ref) -> bool:
        """O nome tem binding no lowering (local/captura ou global já declarada)."""
        return ref.storage in (Storage.LOCAL, Storage.CAPTURE) or ref.name in self._globals

    def _prepare_call_arguments(
        self,
        sig: FnSig,
        info: FunctionInfo | None,
        values: list[Value],
        spread: bool,
        span: Span | None,
        sources: list[TExpr] | None = None,
    ) -> list[Value] | None:
        fixed = len(sig.params) - 1 if sig.variadic else len(sig.params)
        count = len(values)
        # `sources` acompanha `values` (expressão de cada argumento) para que a
        # coerção consiga reconhecer um argumento `<error>` adiado — o panic site
        # já foi emitido e o valor é um zero de recheio (I1, ver `_coerce`).
        args = list(sources) if sources is not None else None

        def coerce(index: int, value: Value, expected: TypeDesc) -> Value:
            source = args[index] if args is not None and index < len(args) else None
            return self._coerce(value, expected, self._line(span), source=source)

        if spread:
            if not sig.variadic:
                self._poison(
                    span,
                    "Spread arguments are only supported for variadic functions.",
                    code=Code.RUNTIME_ARITY,
                )
                return None
            if count != fixed + 1:
                self._poison(
                    span,
                    "Spread arguments only fill the variadic parameter; "
                    "pass the fixed parameters explicitly.",
                    code=Code.RUNTIME_ARITY,
                )
                return None
            rest = values[-1]
            if rest.optional:
                rest = self._unwrap(rest, self._line(span), "Spread argument can't be nil.")
            if rest.ty is not ValueType.LIST:
                self._poison(
                    span,
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
                    span,
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
                raise _unsupported(
                    "Default parameters in indirect function calls", self._line(span)
                )
            return [coerce(index, value, sig.params[index]) for index, value in enumerate(values)]

        if count < sig.min_params:
            self._poison(
                span,
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
            raise _unsupported("Default parameters in indirect function calls", self._line(span))
        if len(fixed_values) != fixed:
            self._poison(
                span,
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
            boxed = self._box_value(coerced, self._line(span))
            self.builder.call(
                self._function("lox_list_push", _I8_PTR, [_I8_PTR, _INT, _INT]),
                [
                    raw,
                    self.builder.extract_value(boxed.llvm, 0),
                    self.builder.extract_value(boxed.llvm, 1),
                ],
            )
        return [*fixed_values, Value(ValueType.LIST, raw)]

    def _guard_uninitialized_function(self, callee: Value, span: Span | None) -> Value:
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
            span,
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
                    self._line(expr.paren_span),
                )
            if count != len(sig.params):
                self._poison(
                    expr.paren_span,
                    self._arity_message(len(sig.params), len(sig.params), count),
                    code=Code.RUNTIME_ARITY,
                )
                return self._zero_desc(sig.ret)

        result = self._expr_type_desc(expr, self._line(expr.paren_span))
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
                expr.paren_span,
                sources=list(expr.arguments),
            )
            if prepared is None:
                raise _unsupported(
                    "Variadic optional call with invalid arguments",
                    self._line(expr.paren_span),
                )
            arguments = prepared
        else:
            arguments = [
                self._coerce(
                    self._expr(argument),
                    expected,
                    self._line(expr.paren_span),
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
        self._set_call_site(expr.paren_span)
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
                self._line(expr.paren_span),
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
            raise _unsupported("Class construction", self._line(expr.paren_span))

        class_ptr = self._load_binding(binding)
        class_ptr = self._guard_closure(
            class_ptr, name, self._line(expr.paren_span), self._column(expr.paren_span)
        )

        arguments = [self._expr(argument) for argument in expr.arguments]
        if layout.synthetic_exception:
            if len(arguments) != 1:
                self._poison(
                    expr.paren_span,
                    self._arity_message(1, 1, len(arguments)),
                    code=Code.RUNTIME_ARITY,
                )
                return self._zero(ValueType.INSTANCE)
            message = self._coerce(
                arguments[0],
                TypeDesc(ValueType.STRING),
                self._line(expr.paren_span),
            )
            call = self.builder.call(layout.ctor, [message.llvm])
            return Value(ValueType.INSTANCE, call, class_name=name)

        init = layout.effective_init()
        minimum = 0 if init is None else init.fn_sig.min_params
        maximum = 0 if init is None else len(init.fn_sig.params)
        count = len(arguments)
        if not minimum <= count <= maximum:
            self._poison(
                expr.paren_span,
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
                self._coerce(argument, expected, self._line(expr.paren_span))
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
        self._set_call_site(expr.paren_span)
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
                expr.paren_span,
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
