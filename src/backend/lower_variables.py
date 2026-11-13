"""Variáveis, células, atribuição e escopo do lowering."""

from __future__ import annotations

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    BackendError,
    Binding,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.frontend.expr import Assign, Expr, Variable
from src.frontend.stmt import Var
from src.frontend.ty import ListTy


class VariableLowering(LoweringBase):
    def _find_binding(self, name: str) -> Binding | None:
        for scope in reversed(self._scopes):
            binding = scope.get(name)
            if binding is not None:
                return binding

        return self._captures.get(name)

    def _load_binding(self, binding: Binding) -> Value:
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
        )

    def _store_binding(self, binding: Binding, value: Value) -> None:
        if binding.cell:
            pointer = self._cell_pointer(binding.storage, binding.desc)
            self.builder.store(value.llvm, pointer)
        else:
            self.builder.store(value.llvm, binding.storage)

    def _guard_closure(self, value: Value, name: str, line: int) -> Value:
        is_null = self.builder.icmp_signed(
            "==", value.llvm, llvm_ir.null_pointer()
        )
        ok = llvm_ir.append_block(self._function_ir, "fn.ok")
        bad = llvm_ir.append_block(self._function_ir, "fn.null")
        self.builder.cbranch(is_null, bad, ok)

        self.builder = llvm_ir.builder(bad)
        self._poison(line, f"Undefined variable '{name}'.")

        self.builder = llvm_ir.builder(ok)
        return value

    def _var(self, stmt: Var) -> None:
        value: Value
        if stmt.initializer is None:
            if stmt.type_annotation is None:
                raise BackendError(
                    "Uninitialized variables need a type annotation "
                    "for the backend.",
                    stmt.name.line,
                )
            declared = self._type_desc(stmt.type_annotation, stmt.name.line)
            if not declared.optional:
                raise BackendError(
                    "Uninitialized variables of non-optional type are not "
                    "supported by the backend yet.",
                    stmt.name.line,
                )
            value = self._zero_desc(declared)
        else:
            saved_element = self._list_expected_element
            if isinstance(stmt.type_annotation, ListTy):
                self._list_expected_element = stmt.type_annotation.element
            try:
                value = self._expr(stmt.initializer)
            finally:
                self._list_expected_element = saved_element
            if stmt.type_annotation is not None:
                annotated = self._type_desc(stmt.type_annotation, stmt.name.line)
                if annotated.optional:
                    if value.ty is ValueType.NIL:
                        declared = annotated
                        value = self._zero_desc(annotated)
                    elif value.optional:
                        if not TypeDesc(value.ty, value.sig).same_as(
                            TypeDesc(annotated.ty, annotated.fn)
                        ):
                            raise BackendError(
                                f"Can't initialize {annotated.ty.name}? with "
                                f"{value.ty.name}?.",
                                stmt.name.line,
                            )
                        declared = value.desc
                    else:
                        # Como no L2, o tipo do slot é o do valor em runtime:
                        # `var b: Float? = 2` guarda `Int?` e imprime `2`.
                        declared = TypeDesc(
                            value.ty, value.sig, True, value.class_name
                        )
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
                if value.ty is ValueType.NIL:
                    raise BackendError(
                        "Variables of type Nil are not supported by the backend yet.",
                        stmt.name.line,
                    )
                declared = value.desc

        if self._function_ir is self.main and len(self._scopes) == 1:
            existing = self._globals.get(stmt.name.lexeme)
            if existing is not None:
                # Redeclaração de global (`var x = 1; var x = 2;`): o interpretador
                # mantém um único binding e sobrescreve o valor; reusar o slot é o
                # que preserva a leitura dinâmica em funções já compiladas.
                if not existing.desc.same_as(declared):
                    raise BackendError(
                        f"Global '{stmt.name.lexeme}' was already declared as "
                        f"{existing.desc.ty.name}; redeclaring it as "
                        f"{declared.ty.name} is not supported by the backend yet.",
                        stmt.name.line,
                    )
                # `var f = ...` depois de `fn f` deixa de ser uma chamada direta.
                binding = Binding(
                    existing.storage,
                    declared.ty,
                    declared.fn,
                    declared.optional,
                    class_name=declared.class_name,
                )
                self._globals[stmt.name.lexeme] = binding
                self.builder.store(value.llvm, binding.storage)
                return

            name = f"g.{stmt.name.lexeme}"
            global_ = llvm_ir.global_variable(
                self.module, name, self._storage_llvm_type(declared)
            )
            binding = Binding(
                global_,
                declared.ty,
                declared.fn,
                declared.optional,
                class_name=declared.class_name,
            )
            self._globals[stmt.name.lexeme] = binding
            self.builder.store(value.llvm, global_)
            return

        if self._analysis.is_captured(stmt):
            cell = self._alloc_cell()
            cell_pointer = self._cell_pointer(cell, declared)
            self.builder.store(value.llvm, cell_pointer)
            self._scopes[-1][stmt.name.lexeme] = Binding(
                cell,
                declared.ty,
                declared.fn,
                declared.optional,
                cell=True,
                class_name=declared.class_name,
            )
            return

        slot = self.builder.alloca(
            self._storage_llvm_type(declared), name=stmt.name.lexeme
        )
        self.builder.store(value.llvm, slot)
        self._scopes[-1][stmt.name.lexeme] = Binding(
            slot,
            declared.ty,
            declared.fn,
            declared.optional,
            class_name=declared.class_name,
        )

    def _variable(self, expr: Variable) -> Value:
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(expr.name.line, f"Undefined variable '{expr.name.lexeme}'.")
            return self._zero(ValueType.INT)

        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        if (
            binding.function is not None
            and binding.function.fn_sig.min_params
            < len(binding.function.fn_sig.params)
        ):
            raise BackendError(
                "Functions with default parameters as values are not supported by the "
                "backend yet.",
                expr.name.line,
            )

        value = self._load_binding(binding)
        if value.ty in (ValueType.FUNCTION, ValueType.CLASS):
            return self._guard_closure(value, expr.name.lexeme, expr.name.line)
        return value

    def _assign(self, expr: Assign) -> Value:
        value = self._expr(expr.value)
        depth = self.depths.get(expr)
        if depth is None and expr.name.lexeme not in self._globals:
            self._poison(expr.name.line, f"Undefined variable '{expr.name.lexeme}'.")
            return value

        binding = self._lookup(expr, expr.name.lexeme, expr.name.line)
        if (
            binding.function is not None
            and binding.function.fn_sig.min_params
            < len(binding.function.fn_sig.params)
        ):
            raise BackendError(
                "Functions with default parameters as values are not supported by the "
                "backend yet.",
                expr.name.line,
            )

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
