# SPDX-License-Identifier: MIT OR Apache-2.0
"""Lowering de funções, lambdas e o ABI de closure do L4 (ADR-0046)."""

from __future__ import annotations

from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _CLOSURE,
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    BackendError,
    Binding,
    CaptureBinding,
    FnSig,
    FunctionInfo,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.frontend.ty import FnTy, GenericFnTy, Ty
from loxia_core.thir import (
    TFnDecl as Function,
)
from loxia_core.thir import (
    TFunction,
    TStmt,
)
from loxia_core.thir import (
    TLambda as Lambda,
)
from loxia_core.thir import (
    TParam as Param,
)


class FunctionLowering(LoweringBase):
    def _predeclare_functions(self, statements: tuple[TStmt, ...]) -> None:
        for statement in statements:
            if not isinstance(statement, Function):
                continue
            fn = statement.fn
            if fn.type_params:
                continue

            info = self._function_info(fn, llvm_name=f"lox.{fn.name}")
            self._top_level[fn.id] = info

            slot = llvm_ir.global_variable(self.module, f"g.{fn.name}", _I8_PTR)
            self._globals[fn.name or ""] = Binding(
                slot,
                ValueType.FUNCTION,
                info.fn_sig,
                function=info,
            )

    def _function_info(
        self,
        fn: TFunction,
        *,
        llvm_name: str | None = None,
        this_class: str | None = None,
        this_interface: str | None = None,
        method_class: str | None = None,
        is_init: bool = False,
        allow_generic: bool = False,
    ) -> FunctionInfo:
        decl = self._decl(fn.id)
        if fn.type_params and not allow_generic:
            raise _unsupported("Generic functions", self._line(decl.span))

        params: list[TypeDesc] = []
        minimum = 0
        variadic = False
        vararg_element: TypeDesc | None = None
        for param in fn.params:
            if param.variadic:
                variadic = True
                vararg_element = self._param_desc(param)
                params.append(TypeDesc(ValueType.LIST))
                continue
            desc = self._param_desc(param)
            params.append(desc)
            if param.default is None:
                minimum += 1

        if is_init:
            return_desc = TypeDesc(ValueType.NIL)
        else:
            return_desc = self._return_desc(fn.ret_ty, self._line(decl.span), fn.name)
        sig = FnSig(
            tuple(params),
            return_desc,
            minimum,
            variadic,
            vararg_element,
        )

        if llvm_name is None:
            self._function_counter += 1
            llvm_name = f"lox.{fn.name}.{self._function_counter}"

        result = _VOID if return_desc.ty is ValueType.NIL else self._storage_llvm_type(return_desc)
        has_this = this_class is not None or this_interface is not None
        prefix = [_I8_PTR, *([_I8_PTR] if has_this else [])]
        signature = llvm_ir.declare(
            self.module,
            llvm_name,
            result,
            [*prefix, *[self._param_llvm_type(param) for param in params]],
        )
        return FunctionInfo(
            signature,
            list(fn.params),
            sig,
            this_class=this_class,
            this_interface=this_interface,
            method_class=method_class,
            is_init=is_init,
            trace_name=fn.display_name,
            decl_file=decl.span.file if decl.span is not None else "",
            decl_line=self._line(decl.span),
            decl_column=self._column(decl.span),
            fn_ty=fn.fn_ty,
        )

    def _param_desc(self, param: Param) -> TypeDesc:
        if param.ty is None:
            raise BackendError(
                f"Parameter '{param.name}' needs a type annotation for the backend.",
                self._line(param.span),
                code=Code.BACKEND_UNSUPPORTED,
            )
        return self._type_desc(param.ty, self._line(param.span))

    def _return_desc(self, ty: Ty | None, line: int, name: str | None) -> TypeDesc:
        if ty is None:
            raise BackendError(
                f"Function '{name}' needs a return type annotation for the backend.",
                line,
                code=Code.BACKEND_UNSUPPORTED,
            )
        return self._type_desc(ty, line)

    def _define_top_level_function(self, fn: TFunction, info: FunctionInfo) -> None:
        decl = self._decl(fn.id)
        binding = self._globals.get(decl.name)
        if binding is None or binding.ty is not ValueType.FUNCTION:
            raise BackendError(
                f"Global '{decl.name}' was redefined as a non-function.",
                self._line(decl.span),
            )

        closure = self._build_closure(info, (), f"<fn {fn.display_name}>")
        self.builder.store(closure.llvm, binding.storage)

    def _local_function(self, fn: TFunction) -> None:
        decl = self._decl(fn.id)
        info = self._function_info(fn, method_class=self._method_class)

        if decl.cell:
            cell = self._alloc_cell()
            self._store_null_cell(cell)
            binding = Binding(
                cell,
                ValueType.FUNCTION,
                info.fn_sig,
                cell=True,
                function=info,
            )
        else:
            slot = self.builder.alloca(_I8_PTR, name=decl.name)
            binding = Binding(
                slot,
                ValueType.FUNCTION,
                info.fn_sig,
                function=info,
            )

        self._scopes[-1][decl.name] = binding

        captures = self._make_captures(fn)
        closure = self._build_closure(info, captures, f"<fn {fn.display_name}>")
        self._store_binding(binding, closure)

        self._emit_function(info, fn, captures)

    def _lambda(self, expr: Lambda) -> Value:
        ty = expr.storage_ty
        if isinstance(ty, GenericFnTy):
            return Value(
                ValueType.FUNCTION,
                llvm_ir.null_pointer(),
                generic=ty,
                generic_node=expr.fn,
            )
        info = self._lambda_info(expr.fn, expr.storage_ty, self._line(expr.span))
        captures = self._make_captures(expr.fn)
        closure = self._build_closure(info, captures, "<lambda>")
        self._emit_function(info, expr.fn, captures)
        return closure

    def _lambda_info(self, fn: TFunction, ty: Ty | None, line: int | None) -> FunctionInfo:
        fn_ty: FnTy | None = ty if isinstance(ty, FnTy) else None
        if fn_ty is None:
            if isinstance(ty, GenericFnTy):
                raise _unsupported("Generic function value", line or 0)
            raise _unsupported("Lambda without a concrete function type", line or 0)

        desc = self._type_desc(fn_ty, line)
        assert desc.fn is not None
        sig = desc.fn

        self._function_counter += 1
        llvm_name = f"lox.lambda.{self._function_counter}"
        result = _VOID if sig.ret.ty is ValueType.NIL else self._storage_llvm_type(sig.ret)
        signature = llvm_ir.declare(
            self.module,
            llvm_name,
            result,
            [_I8_PTR, *[self._param_llvm_type(param) for param in sig.params]],
        )
        decl = self._decl(fn.id)
        return FunctionInfo(
            signature,
            list(fn.params),
            sig,
            method_class=self._method_class,
            trace_name="<lambda>",
            decl_file=decl.span.file if decl.span is not None else "",
            decl_line=self._line(decl.span),
            decl_column=self._column(decl.span),
            fn_ty=fn_ty,
        )

    def _make_captures(self, node: TFunction) -> tuple[CaptureBinding, ...]:
        result: list[CaptureBinding] = []
        for capture in node.captures:
            binding = self._find_binding(capture.name)
            if binding is None:
                raise BackendError(f"Internal capture error for '{capture.name}'.", None)
            if not binding.cell:
                raise BackendError(f"Captured variable '{capture.name}' was not boxed.", None)
            result.append(CaptureBinding(capture.name, binding))

        return tuple(result)

    def _build_closure(
        self,
        info: FunctionInfo,
        captures: tuple[CaptureBinding, ...],
        display: str,
    ) -> Value:
        env: Any = llvm_ir.null_pointer()
        if captures:
            raw_env = self.builder.call(
                self._function("lox_alloc_env", _I8_PTR, [_INT]),
                [llvm_ir.constant(_INT, len(captures))],
            )
            env_type = llvm_ir.literal_struct([_I8_PTR] * len(captures))
            env_struct = self.builder.bitcast(raw_env, env_type.as_pointer())
            for index, capture in enumerate(captures):
                field = self.builder.gep(
                    env_struct,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
                )
                self.builder.store(capture.binding.storage, field)
            env = raw_env

        raw_closure = self.builder.call(self._function("lox_alloc_closure", _I8_PTR, []), [])
        closure = self.builder.bitcast(raw_closure, _CLOSURE.as_pointer())
        fn_slot = self.builder.gep(closure, [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 0)])
        env_slot = self.builder.gep(closure, [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 1)])
        name_slot = self.builder.gep(
            closure, [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, 2)]
        )
        self.builder.store(self.builder.bitcast(info.ir, _I8_PTR), fn_slot)
        self.builder.store(env, env_slot)
        self.builder.store(self._display_pointer(display), name_slot)
        self._closure_sig_fields(closure, info.fn_sig, info.fn_ty)

        return Value(ValueType.FUNCTION, raw_closure, info.fn_sig)

    def _emit_function(
        self,
        info: FunctionInfo,
        fn: TFunction,
        captures: tuple[CaptureBinding, ...],
    ) -> None:
        saved_builder = self.builder
        saved_scopes = self._scopes
        saved_captures = self._captures
        saved_function = self._function_ir
        saved_return = self._return_type_desc
        saved_in_init = self._in_init
        saved_method_class = self._method_class
        saved_type_subst = self._type_subst
        saved_cleanup = self._cleanup_stack
        saved_loops = self._loop_stack
        saved_emitting_finally = self._emitting_finally

        self._function_ir = info.ir
        self._type_subst = {**self._type_subst, **(info.type_subst or {})}
        self._return_type_desc = info.fn_sig.ret
        self._in_init = info.is_init
        self._method_class = info.this_class or info.method_class
        self._scopes = [{}]
        self._captures = {}
        self._cleanup_stack = []
        self._loop_stack = []
        self._emitting_finally = set()
        self.builder = llvm_ir.builder(self._control.new_block(info.ir, "entry"))
        self._stack_enter(info)

        env_arg = info.ir.args[0]
        if captures:
            env_type = llvm_ir.literal_struct([_I8_PTR] * len(captures))
            env_struct = self.builder.bitcast(env_arg, env_type.as_pointer())
            for index, capture in enumerate(captures):
                field = self.builder.gep(
                    env_struct,
                    [llvm_ir.constant(_I32, 0), llvm_ir.constant(_I32, index)],
                )
                cell = self.builder.load(field)
                self._captures[capture.name] = Binding(
                    cell,
                    capture.binding.ty,
                    capture.binding.sig,
                    capture.binding.optional,
                    cell=True,
                    function=capture.binding.function,
                    class_name=capture.binding.class_name,
                )

        offset = 1
        if info.this_class is not None or info.this_interface is not None:
            this_desc = TypeDesc(
                ValueType.INSTANCE,
                class_name=info.this_class,
                interface_name=info.this_interface,
            )
            this_decl = fn.this_decl
            if this_decl is not None and self._decl(this_decl).cell:
                # Lambdas/funções locais capturam `this` como qualquer variável:
                # o receptor precisa viver em célula para atravessar o `env`.
                this_slot = self._alloc_cell()
                self.builder.store(info.ir.args[1], self._cell_pointer(this_slot, this_desc))
                this_binding = Binding(
                    this_slot,
                    ValueType.INSTANCE,
                    cell=True,
                    class_name=info.this_class,
                    interface_name=info.this_interface,
                )
            else:
                this_slot = self.builder.alloca(_I8_PTR, name="this")
                self.builder.store(info.ir.args[1], this_slot)
                this_binding = Binding(
                    this_slot,
                    ValueType.INSTANCE,
                    class_name=info.this_class,
                    interface_name=info.this_interface,
                )
            self._scopes[-1]["this"] = this_binding
            offset = 2

        for index, param in enumerate(info.params):
            desc = info.fn_sig.params[index]
            argument = info.ir.args[offset + index]
            if self._decl(param.decl).cell:
                cell = self._alloc_cell()
                typed = self._cell_pointer(cell, desc)
                self.builder.store(argument, typed)
                binding = Binding(
                    cell,
                    desc.ty,
                    desc.fn,
                    desc.optional,
                    cell=True,
                    class_name=desc.class_name,
                    interface_name=desc.interface_name,
                )
            else:
                slot = self.builder.alloca(self._param_llvm_type(desc), name=param.name)
                self.builder.store(argument, slot)
                binding = Binding(
                    slot,
                    desc.ty,
                    desc.fn,
                    desc.optional,
                    class_name=desc.class_name,
                    interface_name=desc.interface_name,
                )

            self._scopes[-1][param.name] = binding

        for inner in fn.body:
            if self.builder.block.is_terminated:
                break
            self._stmt(inner)

        if not self.builder.block.is_terminated:
            if info.fn_sig.ret.ty is ValueType.NIL:
                self._stack_leave()
                self.builder.ret_void()
            elif info.fn_sig.ret.optional:
                self._stack_leave()
                self.builder.ret(self._zero_desc(info.fn_sig.ret).llvm)
            else:
                # O checker garante `return` em todos os caminhos.
                self.builder.unreachable()
        self._seal_blocks(info.ir)

        self.builder = saved_builder
        self._scopes = saved_scopes
        self._captures = saved_captures
        self._function_ir = saved_function
        self._return_type_desc = saved_return
        self._in_init = saved_in_init
        self._method_class = saved_method_class
        self._type_subst = saved_type_subst
        self._cleanup_stack = saved_cleanup
        self._loop_stack = saved_loops
        self._emitting_finally = saved_emitting_finally

    def _seal_blocks(self, function: Any) -> None:
        """Todo bloco precisa de terminador; continuações de panic ficam `unreachable`."""
        for block in function.blocks:
            if not block.is_terminated:
                self.builder = llvm_ir.builder(block)
                self.builder.unreachable()

    def _alloc_cell(self) -> Any:
        return self.builder.call(self._function("lox_alloc_cell", _I8_PTR, []), [])

    def _cell_pointer(self, cell: Any, desc: TypeDesc) -> Any:
        return self.builder.bitcast(cell, self._param_llvm_type(desc).as_pointer())

    def _store_null_cell(self, cell: Any) -> None:
        pointer = self.builder.bitcast(cell, _I8_PTR.as_pointer())
        self.builder.store(llvm_ir.null_pointer(), pointer)
