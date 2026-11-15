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
from src.diagnostics.codes import Code
from src.frontend.stmt import Raise, Stmt, Try


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
            synthetic_exception=True,
        )
        exception.ctor = llvm_ir.declare(
            self.module, "lox.ctor.Exception", _I8_PTR, [_I8_PTR]
        )
        runtime_error = ClassLayout(
            "RuntimeError",
            901,
            [],
            [],
            None,
            super_name="Exception",
            super_layout=exception,
            instance_type=instance_type,
            synthetic_exception=True,
        )
        runtime_error.ctor = llvm_ir.declare(
            self.module, "lox.ctor.RuntimeError", _I8_PTR, [_I8_PTR]
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
        for name in ("Exception", "RuntimeError"):
            self._emit_top_level_class(self._classes[name])

    def _raise(self, stmt: Raise) -> None:
        line = stmt.keyword.line
        column = stmt.keyword.column
        if stmt.value is None:
            self.builder.call(
                self._function("lox_raise_current", _VOID, [_I32, _I32]),
                [
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            self.builder.unreachable()
            self._new_block("raise.next")
            return
        value = self._expr(stmt.value)
        if value.ty is not ValueType.INSTANCE:
            self._poison(
                line, "Can only raise exceptions.", column=column, code=Code.INVALID_VALUE
            )
            return
        layout = self._classes.get(value.class_name or "")
        type_name = layout.display if layout is not None else "Exception"
        message = llvm_ir.null_pointer()
        if layout is not None:
            field = layout.field("message")
            if field is not None:
                raw = self.builder.load(self._field_slot(value, field))
                string = self.builder.inttoptr(raw, _I8_PTR)
                message = self.builder.call(
                    self._function("lox_str_data", _I8_PTR, [_I8_PTR]),
                    [string],
                )
        self.builder.call(
            self._function(
                "lox_throw", _VOID, [_I8_PTR, _I8_PTR, _I8_PTR, _I32, _I32]
            ),
            [
                value.llvm,
                self._cstring_pointer(type_name),
                message,
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
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
        setjmp = self._function("_setjmp", _I32, [_I8_PTR])
        setjmp.attributes.add("returns_twice")
        status = self.builder.call(setjmp, [buffer])
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
        context = self._push_cleanup(frame, stmt.finally_body)
        try:
            for statement in stmt.body:
                if self.builder.block.is_terminated:
                    break
                self._stmt(statement)
        finally:
            self._scopes.pop()
            self._pop_cleanup(context)
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
            handler_context = self._push_cleanup(None, stmt.finally_body)
            try:
                binding = self.builder.alloca(_I8_PTR, name=clause.binding.lexeme)
                self._bind_handler_exception(exception, binding)
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
                self._scopes.pop()
                self._pop_cleanup(handler_context)
            if not self.builder.block.is_terminated:
                self._emit_finally(stmt, end, None)
            self.builder = llvm_ir.builder(next_block)

        # Nenhum handler: finally e rethrow.
        if stmt.finally_body is not None:
            self._emit_finally(stmt, end, exception)
        else:
            self.builder.call(
                self._function("lox_rethrow", _VOID, [_I8_PTR, _I32, _I32]),
                [
                    exception,
                    llvm_ir.constant(_I32, stmt.keyword.line),
                    llvm_ir.constant(_I32, stmt.keyword.column),
                ],
            )
            self.builder.unreachable()
        self.builder = llvm_ir.builder(end)

    def _bind_handler_exception(self, exception: Any, binding: Any) -> None:
        """Liga `except Tipo as e`: instância do usuário ou `RuntimeError` novo.

        `lox_panic` (divisão por zero etc.) não tem instância, só `type_name` e
        `message`; sem esta materialização, `e.message` desreferenciava NULL.
        """
        raw = self.builder.call(
            self._function("lox_exception_instance", _I8_PTR, [_I8_PTR]),
            [exception],
        )
        missing = self.builder.icmp_signed("==", raw, llvm_ir.null_pointer())
        runtime_block = llvm_ir.append_block(self._function_ir, "except.runtime")
        bound_block = llvm_ir.append_block(self._function_ir, "except.bound")
        self.builder.cbranch(missing, runtime_block, bound_block)
        instance_end = self.builder.block

        self.builder = llvm_ir.builder(runtime_block)
        message = self.builder.call(
            self._function("lox_exception_message", _I8_PTR, [_I8_PTR]),
            [exception],
        )
        text = self.builder.call(
            self._function("lox_str_from_cstr", _I8_PTR, [_I8_PTR]),
            [message],
        )
        layout = self._classes["RuntimeError"]
        assert layout.ctor is not None
        constructed = self.builder.call(layout.ctor, [text])
        runtime_end = self.builder.block
        self.builder.branch(bound_block)

        self.builder = llvm_ir.builder(bound_block)
        instance = self.builder.phi(_I8_PTR, "except.value")
        instance.add_incoming(raw, instance_end)
        instance.add_incoming(constructed, runtime_end)
        self.builder.store(instance, binding)

    def _emit_finally(
        self, stmt: Try, end: Any, pending: Any | None
    ) -> None:
        if stmt.finally_body is None:
            if pending is not None:
                self.builder.call(
                    self._function("lox_rethrow", _VOID, [_I8_PTR, _I32, _I32]),
                    [
                        pending,
                        llvm_ir.constant(_I32, stmt.keyword.line),
                        llvm_ir.constant(_I32, stmt.keyword.column),
                    ],
                )
                self.builder.unreachable()
            else:
                self.builder.branch(end)
            return
        # O frame já foi desempilhado antes de chamar o finally; um `return` aqui
        # deve rodar apenas os cleanups de fora, nunca este de novo.
        self._lower_finally_body(stmt.finally_body)
        if self.builder.block.is_terminated:
            return
        if pending is not None:
            self.builder.call(
                self._function("lox_rethrow", _VOID, [_I8_PTR, _I32, _I32]),
                [
                    pending,
                    llvm_ir.constant(_I32, stmt.keyword.line),
                    llvm_ir.constant(_I32, stmt.keyword.column),
                ],
            )
            self.builder.unreachable()
        else:
            self.builder.branch(end)

    def _lower_finally_body(self, body: list[Stmt]) -> None:
        """Emite o corpo do `finally` uma única vez, no contexto atual."""
        self._scopes.append({})
        try:
            for statement in body:
                if self.builder.block.is_terminated:
                    break
                self._stmt(statement)
        finally:
            self._scopes.pop()

    def _new_block(self, name: str) -> None:
        block = llvm_ir.append_block(self._function_ir, name)
        self.builder = llvm_ir.builder(block)

    def _cstring_pointer(self, message: str) -> Any:
        return llvm_ir.cstring_pointer(self.builder, self._cstring(message))
