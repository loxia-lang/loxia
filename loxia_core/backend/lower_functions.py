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
from loxia_core.frontend.expr import Lambda
from loxia_core.frontend.stmt import Function, Param, Stmt
from loxia_core.frontend.ty import FnTy, GenericFnTy, Ty


class FunctionLowering(LoweringBase):
    def _predeclare_functions(self, statements: list[Stmt]) -> None:
        for statement in statements:
            if not isinstance(statement, Function):
                continue
            if statement.type_params:
                continue

            info = self._function_info(statement, llvm_name=f"lox.{statement.name.lexeme}")
            self._top_level[id(statement)] = info

            slot = llvm_ir.global_variable(self.module, f"g.{statement.name.lexeme}", _I8_PTR)
            self._globals[statement.name.lexeme] = Binding(
                slot,
                ValueType.FUNCTION,
                info.fn_sig,
                function=info,
            )

    def _function_info(
        self,
        stmt: Function,
        *,
        llvm_name: str | None = None,
        this_class: str | None = None,
        this_interface: str | None = None,
        method_class: str | None = None,
        is_init: bool = False,
        allow_generic: bool = False,
    ) -> FunctionInfo:
        if stmt.type_params and not allow_generic:
            raise _unsupported("Generic functions", stmt.name.line)

        params: list[TypeDesc] = []
        minimum = 0
        variadic = False
        vararg_element: TypeDesc | None = None
        for param in stmt.params:
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
            return_desc = self._return_desc(stmt.return_type, stmt.name.line, stmt.name.lexeme)
        sig = FnSig(
            tuple(params),
            return_desc,
            minimum,
            variadic,
            vararg_element,
        )

        if llvm_name is None:
            self._function_counter += 1
            llvm_name = f"lox.{stmt.name.lexeme}.{self._function_counter}"

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
            stmt.params,
            sig,
            this_class=this_class,
            this_interface=this_interface,
            method_class=method_class,
            is_init=is_init,
            trace_name=stmt.display_name or stmt.name.lexeme,
            decl_file=stmt.name.file,
            decl_line=stmt.name.line,
            decl_column=stmt.name.column,
        )

    def _param_desc(self, param: Param) -> TypeDesc:
        if param.type_annotation is None:
            raise BackendError(
                f"Parameter '{param.name.lexeme}' needs a type annotation for the backend.",
                param.name.line,
                code=Code.BACKEND_UNSUPPORTED,
            )
        return self._type_desc(param.type_annotation, param.name.line)

    def _return_desc(self, ty: Ty | None, line: int, name: str) -> TypeDesc:
        if ty is None:
            raise BackendError(
                f"Function '{name}' needs a return type annotation for the backend.",
                line,
                code=Code.BACKEND_UNSUPPORTED,
            )
        return self._type_desc(ty, line)

    def _define_top_level_function(self, stmt: Function, info: FunctionInfo) -> None:
        binding = self._globals.get(stmt.name.lexeme)
        if binding is None or binding.ty is not ValueType.FUNCTION:
            raise BackendError(
                f"Global '{stmt.name.lexeme}' was redefined as a non-function.",
                stmt.name.line,
            )

        closure = self._build_closure(info, (), f"<fn {stmt.display_name or stmt.name.lexeme}>")
        self.builder.store(closure.llvm, binding.storage)

    def _local_function(self, stmt: Function) -> None:
        info = self._function_info(stmt, method_class=self._method_class)
        captured = self._analysis.is_captured(stmt)

        if captured:
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
            slot = self.builder.alloca(_I8_PTR, name=stmt.name.lexeme)
            binding = Binding(
                slot,
                ValueType.FUNCTION,
                info.fn_sig,
                function=info,
            )

        self._scopes[-1][stmt.name.lexeme] = binding

        captures = self._make_captures(stmt)
        closure = self._build_closure(
            info, captures, f"<fn {stmt.display_name or stmt.name.lexeme}>"
        )
        self._store_binding(binding, closure)

        self._emit_function(info, stmt, captures)

    def _lambda(self, expr: Lambda) -> Value:
        ty = self.types.get(expr)
        if isinstance(ty, GenericFnTy):
            return Value(
                ValueType.FUNCTION,
                llvm_ir.null_pointer(),
                generic=ty,
                generic_node=expr,
            )
        info = self._lambda_info(expr)
        captures = self._make_captures(expr)
        closure = self._build_closure(info, captures, "<lambda>")
        self._emit_function(info, expr, captures)
        return closure

    def _lambda_info(self, expr: Lambda, fn_ty: FnTy | None = None) -> FunctionInfo:
        ty = self.types.get(expr)
        if fn_ty is None:
            if isinstance(ty, GenericFnTy):
                raise _unsupported("Generic function value", expr.keyword.line)
            if not isinstance(ty, FnTy):
                raise _unsupported("Lambda without a concrete function type", expr.keyword.line)
            fn_ty = ty

        desc = self._type_desc(fn_ty, expr.keyword.line)
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
        return FunctionInfo(
            signature,
            expr.params,
            sig,
            method_class=self._method_class,
            trace_name="<lambda>",
            decl_file=expr.keyword.file,
            decl_line=expr.keyword.line,
            decl_column=expr.keyword.column,
        )

    def _make_captures(self, node: Function | Lambda) -> tuple[CaptureBinding, ...]:
        result: list[CaptureBinding] = []
        for capture in self._analysis.captures_of(node):
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

        return Value(ValueType.FUNCTION, raw_closure, info.fn_sig)

    def _emit_function(
        self,
        info: FunctionInfo,
        stmt: Function | Lambda,
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

        self._function_ir = info.ir
        self._type_subst = {**self._type_subst, **(info.type_subst or {})}
        self._return_type_desc = info.fn_sig.ret
        self._in_init = info.is_init
        self._method_class = info.this_class or info.method_class
        self._scopes = [{}]
        self._captures = {}
        self._cleanup_stack = []
        self.builder = llvm_ir.builder(llvm_ir.block_of(info.ir, "entry"))
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
            if self._analysis.is_captured(stmt):
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
            if self._analysis.is_captured(param):
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
                slot = self.builder.alloca(self._param_llvm_type(desc), name=param.name.lexeme)
                self.builder.store(argument, slot)
                binding = Binding(
                    slot,
                    desc.ty,
                    desc.fn,
                    desc.optional,
                    class_name=desc.class_name,
                    interface_name=desc.interface_name,
                )

            self._scopes[-1][param.name.lexeme] = binding

        for inner in stmt.body:
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

    def _seal_blocks(self, function: Any) -> None:
        """Todo bloco precisa de terminador; continuações de panic ficam `unreachable`."""
        for block in function.blocks:
            if not block.is_terminated:
                llvm_ir.builder(block).unreachable()

    def _alloc_cell(self) -> Any:
        return self.builder.call(self._function("lox_alloc_cell", _I8_PTR, []), [])

    def _cell_pointer(self, cell: Any, desc: TypeDesc) -> Any:
        return self.builder.bitcast(cell, self._param_llvm_type(desc).as_pointer())

    def _store_null_cell(self, cell: Any) -> None:
        pointer = self.builder.bitcast(cell, _I8_PTR.as_pointer())
        self.builder.store(llvm_ir.null_pointer(), pointer)
