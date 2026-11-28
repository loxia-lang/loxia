# SPDX-License-Identifier: MIT OR Apache-2.0
"""Variáveis, células, atribuição e escopo do lowering."""

from __future__ import annotations

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _INT,
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
from loxia_core.frontend.ty import ListTy, MapTy
from loxia_core.thir import (
    Ref,
    Storage,
)
from loxia_core.thir import (
    TAssign as Assign,
)
from loxia_core.thir import (
    TVar as Variable,
)
from loxia_core.thir import (
    TVarStmt as Var,
)

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
        ok = self._control.new_block(self._function_ir, "fn.ok")
        bad = self._control.new_block(self._function_ir, "fn.null")
        self.builder.cbranch(is_null, bad, ok)

        self.builder = llvm_ir.builder(bad)
        self._poison(
            line, f"Undefined variable '{name}'.", column=column, code=Code.UNDEFINED_VARIABLE
        )

        self.builder = llvm_ir.builder(ok)
        return value

    def _var(self, stmt: Var) -> None:
        value: Value
        decl = self._decl(stmt.decl)
        name_span = decl.span
        annotation = decl.ty
        if stmt.initializer is None:
            if annotation is None:
                raise BackendError(
                    "Uninitialized variables need a type annotation for the backend.",
                    self._line(name_span),
                    code=Code.BACKEND_UNSUPPORTED,
                )
            declared = self._type_desc(annotation, self._line(name_span))
            if not declared.optional and declared.ty is not ValueType.FUNCTION:
                # A variável anotada começa nil; até a representação unificada,
                # usa-se `Any` para preservar o comportamento do interpretador.
                declared = TypeDesc(ValueType.ANY)
            value = self._zero_desc(declared)
        else:
            saved_element = self._list_expected_element
            saved_key = self._map_expected_key
            saved_value = self._map_expected_value
            if isinstance(annotation, ListTy):
                self._list_expected_element = annotation.element
            if isinstance(annotation, MapTy):
                self._map_expected_key = annotation.key
                self._map_expected_value = annotation.value
            try:
                value = self._expr(stmt.initializer)
            finally:
                self._list_expected_element = saved_element
                self._map_expected_key = saved_key
                self._map_expected_value = saved_value
            if annotation is not None:
                annotated = self._type_desc(annotation, self._line(name_span))
                if annotated.interface_name is not None:
                    declared = annotated
                    value = self._coerce(value, annotated, self._line(name_span))
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
                                self._line(name_span),
                            )
                        declared = value.desc
                    else:
                        # Como no L2, o tipo do slot é o do valor em runtime:
                        # `var b: Float? = 2` guarda `Int?` e imprime `2`.
                        declared = TypeDesc(value.ty, value.sig, True, value.class_name)
                        value = self._some(declared, value)
                elif value.optional or value.ty is ValueType.NIL:
                    declared = annotated
                    value = self._coerce(value, annotated, self._line(name_span))
                elif annotated.ty is ValueType.ANY:
                    declared = annotated
                    value = self._box_value(value, self._line(name_span))
                else:
                    # Anotação não converte em runtime (L2): `val f: Float = 2`
                    # guarda `Int` e imprime `2`.
                    declared = value.desc
            else:
                declared = value.desc

        if self._function_ir is self.main and len(self._scopes) == 1:
            existing = self._globals.get(decl.name)
            if existing is not None:
                # Redeclaração de global (`var x = 1; var x = 2)`): o interpretador
                # mantém um único binding e sobrescreve o valor; reusar o slot é o
                # que preserva a leitura dinâmica em funções já compiladas.
                if not existing.mutable:
                    self._poison(
                        name_span,
                        immutable_redeclare_message(decl.name),
                        code=Code.RUNTIME_IMMUTABLE,
                    )
                    return
                if not existing.desc.same_as(declared):
                    raise BackendError(
                        f"Global '{decl.name}' was already declared as "
                        f"{existing.desc.ty.name}; redeclaring it as "
                        f"{declared.ty.name} is not supported by the backend yet.",
                        self._line(name_span),
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
                    mutable=decl.mutable,
                )
                self._globals[decl.name] = binding
                self.builder.store(self._arg_llvm(value, declared), binding.storage)
                return

            name = f"g.{decl.name}"
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
                mutable=decl.mutable,
            )
            self._globals[decl.name] = binding
            self.builder.store(self._arg_llvm(value, declared), global_)
            return

        if decl.cell:
            cell = self._alloc_cell()
            cell_pointer = self._cell_pointer(cell, declared)
            self.builder.store(self._arg_llvm(value, declared), cell_pointer)
            self._scopes[-1][decl.name] = Binding(
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
                mutable=decl.mutable,
            )
            return

        slot = self.builder.alloca(self._storage_llvm_type(declared), name=decl.name)
        self.builder.store(self._arg_llvm(value, declared), slot)
        self._scopes[-1][decl.name] = Binding(
            slot,
            declared.ty,
            declared.fn,
            declared.optional,
            class_name=declared.class_name,
            interface_name=declared.interface_name,
            function=value.function,
            generic=value.generic,
            generic_node=value.generic_node,
            mutable=decl.mutable,
        )

    def _variable(self, expr: Variable) -> Value:
        ref = expr.ref
        line = self._line(expr.span)
        if (
            ref.storage in (Storage.GLOBAL, Storage.BUILTIN, Storage.UNRESOLVED)
            and ref.name not in self._globals
        ):
            if ref.name in self._enum_layouts:
                raise _unsupported("Enum object as value", line)
            if ref.name in _NATIVE_VALUE_GAPS:
                raise _unsupported(f"Native value '{ref.name}'", line)
            self._poison(
                expr.span,
                f"Undefined variable '{ref.name}'.",
                code=Code.UNDEFINED_VARIABLE,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0), error=True)

        binding = self._lookup(ref, line)
        value = self._load_binding(binding)
        if value.generic is not None:
            return value
        if value.ty in (ValueType.FUNCTION, ValueType.CLASS) and not value.optional:
            # Só um slot obrigatório sem valor é "indefinido": num opcional o
            # ponteiro nulo é o próprio `nil`, valor legítimo.
            return self._guard_closure(
                value,
                ref.name,
                line,
                self._column(expr.span),
            )
        return value

    def _assign(self, expr: Assign) -> Value:
        value = self._expr(expr.value)
        ref = expr.ref
        line = self._line(expr.name_span)
        if (
            ref.storage in (Storage.GLOBAL, Storage.BUILTIN, Storage.UNRESOLVED)
            and ref.name not in self._globals
        ):
            self._poison(
                expr.name_span,
                f"Undefined variable '{ref.name}'.",
                code=Code.UNDEFINED_VARIABLE,
            )
            return value

        binding = self._lookup(ref, line)
        if not binding.mutable:
            self._poison(
                expr.name_span,
                immutable_assignment_message(ref.name),
                code=Code.RUNTIME_IMMUTABLE,
            )
            return value
        value = self._coerce(value, binding.desc, line, source=expr.value)
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
            self._replace_binding(ref, replacement)

        return value

    def _replace_binding(self, ref: Ref, binding: Binding) -> None:
        if ref.storage is Storage.CAPTURE:
            self._captures[ref.name] = binding
            return
        if ref.storage is Storage.LOCAL:
            for scope in reversed(self._scopes):
                if ref.name in scope:
                    scope[ref.name] = binding
                    return
        self._globals[ref.name] = binding

    def _lookup(self, ref: Ref, line: int) -> Binding:
        if ref.storage is Storage.CAPTURE:
            binding = self._captures.get(ref.name)
            if binding is None:
                layout = self._classes.get(self._method_class or "")
                if layout is not None and layout.local:
                    raise _unsupported("Captures in local class methods", line)
                raise BackendError(f"Undefined variable '{ref.name}'.", line)
            return binding

        if ref.storage is Storage.LOCAL:
            for scope in reversed(self._scopes):
                binding = scope.get(ref.name)
                if binding is not None:
                    return binding
            raise BackendError(f"Undefined variable '{ref.name}'.", line)

        binding = self._globals.get(ref.name)
        if binding is None:
            raise BackendError(f"Undefined variable '{ref.name}'.", line)
        return binding
