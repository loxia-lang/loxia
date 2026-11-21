# SPDX-License-Identifier: MIT OR Apache-2.0
"""Variáveis, células, atribuição e escopo do lowering."""

from __future__ import annotations

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    BackendError,
    Binding,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.diagnostics.errors import (
    immutable_assignment_message,
    immutable_redeclare_message,
)
from loxia_core.execution.prelude import BUILTIN_NAMES
from loxia_core.frontend.expr import Assign, Expr, Variable
from loxia_core.frontend.stmt import Var
from loxia_core.frontend.ty import ListTy, MapTy

_NATIVE_VALUE_GAPS = BUILTIN_NAMES - {"Exception", "RuntimeError", "Result"}


class VariableLowering(LoweringBase):
    def _find_binding(self, name: str) -> Binding | None:
        for scope in reversed(self._scopes):
            binding = scope.get(name)
            if binding is not None:
                return binding

        return self._captures.get(name)

    def _load_binding(self, binding: Binding) -> Value:
        if binding.ty is ValueType.NIL:
            # `Nil` has no value representation: the slot only exists so the name exists.
            return Value(ValueType.NIL)
        if binding.cell:
            pointer = self._cell_pointer(binding.storage, binding.desc)
            loaded = self.builder.load(pointer)
        else:
            loaded = self.builder.load(binding.storage)

        return Value(
            binding.ty,
            loaded,
            binding.sig,
            binding.optional,
            binding.class_name,
            binding.function,
            binding.generic,
            binding.generic_node,
            binding.interface_name,
        )

    def _store_binding(self, binding: Binding, value: Value) -> None:
        if binding.cell:
            pointer = self._cell_pointer(binding.storage, binding.desc)
            self.builder.store(self._arg_llvm(value, binding.desc), pointer)
        else:
            self.builder.store(self._arg_llvm(value, binding.desc), binding.storage)

    def _guard_closure(self, value: Value, name: str, line: int, column: int = 0) -> Value:
        is_null = self.builder.icmp_signed("==", value.llvm, llvm_ir.null_pointer())
        ok = llvm_ir.append_block(self._function_ir, "fn.ok")
        bad = llvm_ir.append_block(self._function_ir, "fn.null")
        self.builder.cbranch(is_null, bad, ok)

        self.builder = llvm_ir.builder(bad)
        self._poison(
            line, f"Undefined variable '{name}'.", column=column, code=Code.UNDEFINED_VARIABLE
        )

        self.builder = llvm_ir.builder(ok)
        return value

    def _var(self, stmt: Var) -> None:
        value: Value
        if stmt.initializer is None:
            if stmt.type_annotation is None:
                raise BackendError(
                    "Uninitialized variables need a type annotation for the backend.",
                    stmt.name.line,
                    code=Code.BACKEND_UNSUPPORTED,
                )
            declared = self._type_desc(stmt.type_annotation, stmt.name.line)
            if not declared.optional and declared.ty is not ValueType.FUNCTION:
                # A variável anotada começa nil; até a representação unificada,
                # usa-se `Any` para preservar o comportamento do interpretador.
                declared = TypeDesc(ValueType.ANY)
            value = self._zero_desc(declared)
        else:
            saved_element = self._list_expected_element
            saved_key = self._map_expected_key
            saved_value = self._map_expected_value
            if isinstance(stmt.type_annotation, ListTy):
                self._list_expected_element = stmt.type_annotation.element
            if isinstance(stmt.type_annotation, MapTy):
                self._map_expected_key = stmt.type_annotation.key
                self._map_expected_value = stmt.type_annotation.value
            try:
                value = self._expr(stmt.initializer)
            finally:
                self._list_expected_element = saved_element
                self._map_expected_key = saved_key
                self._map_expected_value = saved_value
            if stmt.type_annotation is not None:
                annotated = self._type_desc(stmt.type_annotation, stmt.name.line)
                if annotated.interface_name is not None:
                    declared = annotated
                    value = self._coerce(value, annotated, stmt.name.line)
                elif annotated.optional:
                    if value.ty is ValueType.NIL:
                        declared = annotated
                        value = self._zero_desc(annotated)
                    elif value.optional:
                        if not TypeDesc(value.ty, value.sig).same_as(
                            TypeDesc(annotated.ty, annotated.fn)
                        ):
                            raise BackendError(
                                f"Can't initialize {annotated.ty.name}? with {value.ty.name}?.",
                                stmt.name.line,
                            )
                        declared = value.desc
                    else:
                        # Como no L2, o tipo do slot é o do valor em runtime:
                        # `var b: Float? = 2` guarda `Int?` e imprime `2`.
                        declared = TypeDesc(value.ty, value.sig, True, value.class_name)
                        value = self._some(declared, value)
                elif value.optional or value.ty is ValueType.NIL:
                    declared = annotated
                    value = self._coerce(value, annotated, stmt.name.line)
                elif annotated.ty is ValueType.ANY:
                    declared = annotated
                    value = self._box_value(value, stmt.name.line)
                else:
                    # Anotação não converte em runtime (L2): `val f: Float = 2`
                    # guarda `Int` e imprime `2`.
                    declared = value.desc
            else:
                declared = value.desc

        if self._function_ir is self.main and len(self._scopes) == 1:
            existing = self._globals.get(stmt.name.lexeme)
            if existing is not None:
                # Redeclaração de global (`var x = 1; var x = 2)`): o interpretador
                # mantém um único binding e sobrescreve o valor; reusar o slot é o
                # que preserva a leitura dinâmica em funções já compiladas.
                if not existing.mutable:
                    self._poison(
                        stmt.name,
                        immutable_redeclare_message(stmt.name.lexeme),
                        code=Code.RUNTIME_IMMUTABLE,
                    )
                    return
                if not existing.desc.same_as(declared):
                    raise BackendError(
                        f"Global '{stmt.name.lexeme}' was already declared as "
                        f"{existing.desc.ty.name}; redeclaring it as "
                        f"{declared.ty.name} is not supported by the backend yet.",
                        stmt.name.line,
                        code=Code.BACKEND_UNSUPPORTED,
                    )
                # `var f = ...` depois de `fn f` deixa de ser uma chamada direta.
                binding = Binding(
                    existing.storage,
                    declared.ty,
                    declared.fn,
                    declared.optional,
                    class_name=declared.class_name,
                    interface_name=declared.interface_name,
                    function=value.function,
                    generic=value.generic,
                    generic_node=value.generic_node,
                    mutable=stmt.mutable,
                )
                self._globals[stmt.name.lexeme] = binding
                self.builder.store(self._arg_llvm(value, declared), binding.storage)
                return

            name = f"g.{stmt.name.lexeme}"
            global_ = llvm_ir.global_variable(self.module, name, self._storage_llvm_type(declared))
            binding = Binding(
                global_,
                declared.ty,
                declared.fn,
                declared.optional,
                class_name=declared.class_name,
                interface_name=declared.interface_name,
                function=value.function,
                generic=value.generic,
                generic_node=value.generic_node,
                mutable=stmt.mutable,
            )
            self._globals[stmt.name.lexeme] = binding
            self.builder.store(self._arg_llvm(value, declared), global_)
            return

        if self._analysis.is_captured(stmt):
            cell = self._alloc_cell()
            cell_pointer = self._cell_pointer(cell, declared)
            self.builder.store(self._arg_llvm(value, declared), cell_pointer)
            self._scopes[-1][stmt.name.lexeme] = Binding(
                cell,
                declared.ty,
                declared.fn,
                declared.optional,
                cell=True,
                class_name=declared.class_name,
                interface_name=declared.interface_name,
                function=value.function,
                generic=value.generic,
                generic_node=value.generic_node,
                mutable=stmt.mutable,
            )
            return

        slot = self.builder.alloca(self._storage_llvm_type(declared), name=stmt.name.lexeme)
        self.builder.store(self._arg_llvm(value, declared), slot)
        self._scopes[-1][stmt.name.lexeme] = Binding(
            slot,
            declared.ty,
            declared.fn,
            declared.optional,
            class_name=declared.class_name,
            interface_name=declared.interface_name,
            function=value.function,
            generic=value.generic,
            generic_node=value.generic_node,
            mutable=stmt.mutable,
        )

    def _variable(self, expr: Variable) -> Value:
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            if expr.name.lexeme in self._enum_layouts:
                raise _unsupported("Enum object as value", expr.name.line)
            if expr.name.lexeme in _NATIVE_VALUE_GAPS:
                raise _unsupported(f"Native value '{expr.name.lexeme}'", expr.name.line)
            self._poison(
                expr.name,
                f"Undefined variable '{expr.name.lexeme}'.",
                code=Code.UNDEFINED_VARIABLE,
            )
            return self._zero(ValueType.INT)

        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        value = self._load_binding(binding)
        if value.generic is not None:
            return value
        if value.ty in (ValueType.FUNCTION, ValueType.CLASS):
            return self._guard_closure(value, expr.name.lexeme, expr.name.line, expr.name.column)
        return value

    def _assign(self, expr: Assign) -> Value:
        value = self._expr(expr.value)
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(
                expr.name,
                f"Undefined variable '{expr.name.lexeme}'.",
                code=Code.UNDEFINED_VARIABLE,
            )
            return value

        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        if not binding.mutable:
            self._poison(
                expr.name,
                immutable_assignment_message(expr.name.lexeme),
                code=Code.RUNTIME_IMMUTABLE,
            )
            return value
        value = self._coerce(value, binding.desc, expr.name.line)
        self._store_binding(binding, value)

        if binding.function is not None:
            # O binding agora aponta para outra função: chamadas seguintes são
            # indiretas (o corpo pode ter mudado).
            replacement = Binding(
                binding.storage,
                value.ty,
                value.sig,
                value.optional,
                binding.cell,
                class_name=value.class_name,
                interface_name=value.interface_name,
            )
            self._replace_binding(expr, expr.name.lexeme, replacement)

        return value

    def _replace_binding(self, expr: Expr, name: str, binding: Binding) -> None:
        depth = self.depths.get(expr)
        if depth is None:
            self._globals[name] = binding
        elif depth < len(self._scopes):
            self._scopes[-1 - depth][name] = binding
        else:
            self._captures[name] = binding

    def _lookup(self, expr: Expr, name: str, line: int) -> Binding:
        depth = self.depths.get(expr)
        if depth is None:
            binding = self._globals.get(name)
            if binding is None:
                raise BackendError(f"Undefined variable '{name}'.", line)
            return binding

        if depth < len(self._scopes):
            return self._scopes[-1 - depth][name]

        binding = self._captures.get(name)
        if binding is None:
            layout = self._classes.get(self._method_class or "")
            if layout is not None and layout.local:
                raise _unsupported("Captures in local class methods", line)
            raise BackendError(f"Undefined variable '{name}'.", line)
        return binding
