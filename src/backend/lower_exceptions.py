"""Exceções do L6j: try/raise/finally com ABI setjmp/longjmp (ADR-0062)."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    Binding,
    ClassLayout,
    FieldLayout,
    TypeDesc,
    ValueType,
)
from src.frontend.stmt import Raise, Try


class ExceptionLowering(LoweringBase):
    def _prepare_exception_classes(self) -> None:
        if "Exception" in self._classes:
            return
        message = FieldLayout(
            "message",
            TypeDesc(ValueType.STRING),
            False,
            None,
            0,
            0,
        )
        instance_type = llvm_ir.literal_struct([_I8_PTR, _INT, _INT])
        exception = ClassLayout(
            "Exception",
            900,
            [message],
            [],
            None,
            instance_type=instance_type,
        )
        exception.ctor = llvm_ir.declare(
            self.module, "lox.ctor.Exception", _I8_PTR, []
        )
        runtime_error = ClassLayout(
            "LoxRuntimeError",
            901,
            [],
            [],
            None,
            super_name="Exception",
            super_layout=exception,
            instance_type=instance_type,
        )
        runtime_error.ctor = llvm_ir.declare(
            self.module, "lox.ctor.LoxRuntimeError", _I8_PTR, []
        )
        for layout in (exception, runtime_error):
            self._classes[layout.name] = layout
            self._globals[layout.name] = Binding(
                llvm_ir.global_variable(
                    self.module, f"g.{layout.name}", _I8_PTR
                ),
                ValueType.CLASS,
                class_name=layout.name,
            )

    def _emit_exception_classes(self) -> None:
        for name in ("Exception", "LoxRuntimeError"):
            self._emit_top_level_class(self._classes[name])

    def _raise(self, stmt: Raise) -> None:
        line = stmt.keyword.line
        if stmt.value is None:
            self.builder.call(
                self._function("lox_raise_current", _VOID, [_I32]),
                [llvm_ir.constant(_I32, line)],
            )
            self.builder.unreachable()
            self._new_block("raise.next")
            return
        value = self._expr(stmt.value)
        if value.ty is not ValueType.INSTANCE:
            self._poison(line, "Can only raise exceptions.")
            return
        layout = self._classes.get(value.class_name or "")
        type_name = layout.display if layout is not None else "Exception"
        self.builder.call(
            self._function(
                "lox_throw", _VOID, [_I8_PTR, _I8_PTR, _I8_PTR, _I32]
            ),
            [
                value.llvm,
                self._cstring_pointer(type_name),
                llvm_ir.null_pointer(),
                llvm_ir.constant(_I32, line),
            ],
        )
        self.builder.unreachable()
        self._new_block("raise.next")

    def _try(self, stmt: Try) -> None:
        frame = self.builder.call(
            self._function("lox_try_push", _I8_PTR, []), []
        )
        buffer = self.builder.call(
            self._function("lox_try_buffer", _I8_PTR, [_I8_PTR]), [frame]
        )
        status = self.builder.call(
            self._function("_setjmp", _I32, [_I8_PTR]), [buffer]
        )
        normal = llvm_ir.append_block(self._function_ir, "try.normal")
        caught = llvm_ir.append_block(self._function_ir, "try.caught")
        end = llvm_ir.append_block(self._function_ir, "try.end")
        ok = self.builder.icmp_signed(
            "==", status, llvm_ir.constant(_I32, 0)
        )
        self.builder.cbranch(ok, normal, caught)

        # Caminho normal: corpo, pop, finally.
        self.builder = llvm_ir.builder(normal)
        self._scopes.append({})
        if stmt.finally_body is not None:
            self._finally_stack.append(stmt.finally_body)
        try:
            for statement in stmt.body:
                if self.builder.block.is_terminated:
                    break
                self._stmt(statement)
        finally:
            if (
                stmt.finally_body is not None
                and self._finally_stack
                and self._finally_stack[-1] is stmt.finally_body
            ):
                self._finally_stack.pop()
            self._scopes.pop()
        if not self.builder.block.is_terminated:
            self.builder.call(
                self._function("lox_try_pop", _VOID, [_I8_PTR]), [frame]
            )
            self._emit_finally(stmt, end, None)

        # Caminho de exceção: captura, handlers, finally/rethrow.
        self.builder = llvm_ir.builder(caught)
        self.builder.call(
            self._function("lox_try_pop", _VOID, [_I8_PTR]), [frame]
        )
        exception = self.builder.call(
            self._function("lox_try_exception", _I8_PTR, [_I8_PTR]), [frame]
        )
        handler_blocks = []
        for clause in stmt.handlers:
            match = self.builder.call(
                self._function(
                    "lox_exception_matches", _I32, [_I8_PTR, _I8_PTR]
                ),
                [exception, self._cstring_pointer(clause.type_name.lexeme)],
            )
            matched = self.builder.icmp_signed(
                "!=", match, llvm_ir.constant(_I32, 0)
            )
            body = llvm_ir.append_block(self._function_ir, "except.body")
            next_block = llvm_ir.append_block(self._function_ir, "except.next")
            self.builder.cbranch(matched, body, next_block)
            handler_blocks.append(body)
            self.builder = llvm_ir.builder(body)
            self._scopes.append({})
            if stmt.finally_body is not None:
                self._finally_stack.append(stmt.finally_body)
            try:
                binding = self.builder.alloca(_I8_PTR, name=clause.binding.lexeme)
                instance = self.builder.call(
                    self._function("lox_exception_instance", _I8_PTR, [_I8_PTR]),
                    [exception],
                )
                self.builder.store(instance, binding)
                self._scopes[-1][clause.binding.lexeme] = Binding(
                    binding,
                    ValueType.INSTANCE,
                    class_name=clause.type_name.lexeme,
                )
                for statement in clause.body:
                    if self.builder.block.is_terminated:
                        break
                    self._stmt(statement)
            finally:
                if (
                    stmt.finally_body is not None
                    and self._finally_stack
                    and self._finally_stack[-1] is stmt.finally_body
                ):
                    self._finally_stack.pop()
                self._scopes.pop()
            if not self.builder.block.is_terminated:
                self._emit_finally(stmt, end, None)
            self.builder = llvm_ir.builder(next_block)

        # Nenhum handler: finally e rethrow.
        if stmt.finally_body is not None:
            self._emit_finally(stmt, end, exception)
        else:
            self.builder.call(
                self._function("lox_rethrow", _VOID, [_I8_PTR, _I32]),
                [exception, llvm_ir.constant(_I32, stmt.keyword.line)],
            )
            self.builder.unreachable()
        self.builder = llvm_ir.builder(end)

    def _emit_finally(
        self, stmt: Try, end: Any, pending: Any | None
    ) -> None:
        if stmt.finally_body is None:
            if pending is not None:
                self.builder.call(
                    self._function("lox_rethrow", _VOID, [_I8_PTR, _I32]),
                    [pending, llvm_ir.constant(_I32, stmt.keyword.line)],
                )
                self.builder.unreachable()
            else:
                self.builder.branch(end)
            return
        self._finally_stack.append(stmt.finally_body)
        try:
            self._scopes.append({})
            try:
                for statement in stmt.finally_body:
                    if self.builder.block.is_terminated:
                        break
                    self._stmt(statement)
            finally:
                self._scopes.pop()
        finally:
            if self._finally_stack and self._finally_stack[-1] is stmt.finally_body:
                self._finally_stack.pop()
        if self.builder.block.is_terminated:
            return
        if pending is not None:
            self.builder.call(
                self._function("lox_rethrow", _VOID, [_I8_PTR, _I32]),
                [pending, llvm_ir.constant(_I32, stmt.keyword.line)],
            )
            self.builder.unreachable()
        else:
            self.builder.branch(end)

    def _new_block(self, name: str) -> None:
        block = llvm_ir.append_block(self._function_ir, name)
        self.builder = llvm_ir.builder(block)

    def _cstring_pointer(self, message: str) -> Any:
        return llvm_ir.cstring_pointer(self.builder, self._cstring(message))
