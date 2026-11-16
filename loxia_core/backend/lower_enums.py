"""Enums, `Result` e `match` (L6i, ADR-0061)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower_base import LoweringBase
from loxia_core.backend.lower_model import (
    _ANY,
    _I8_PTR,
    _I32,
    _INT,
    _VOID,
    Binding,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from loxia_core.diagnostics.codes import Code
from loxia_core.frontend.expr import (
    Call,
    Get,
    Match,
    VariantPattern,
    WildcardPattern,
)
from loxia_core.frontend.stmt import EnumDecl
from loxia_core.frontend.ty import EnumTy, Ty, TyVar


@dataclass(frozen=True)
class EnumVariantLayout:
    name: str
    payload: tuple[Ty, ...]


@dataclass(frozen=True)
class EnumLayout:
    name: str
    enum_id: int
    type_params: tuple[str, ...]
    variants: tuple[EnumVariantLayout, ...]

    def variant(self, name: str) -> EnumVariantLayout | None:
        for variant in self.variants:
            if variant.name == name:
                return variant
        return None


class EnumLowering(LoweringBase):
    def _prepare_enums(self, statements: list[Any]) -> None:
        layouts: dict[str, EnumLayout] = {}
        # Result é embutido e sempre o id 0.
        layouts["Result"] = EnumLayout(
            "Result",
            0,
            ("T", "E"),
            (
                EnumVariantLayout("Ok", (TyVar("T", -1),)),
                EnumVariantLayout("Err", (TyVar("E", -2),)),
            ),
        )
        next_id = 1
        for stmt in statements:
            if not isinstance(stmt, EnumDecl):
                continue
            variants = tuple(
                EnumVariantLayout(
                    variant.name.lexeme,
                    tuple(variant.payload),
                )
                for variant in stmt.variants
            )
            layouts[stmt.name.lexeme] = EnumLayout(
                stmt.display_name or stmt.name.lexeme,
                next_id,
                tuple(param.lexeme for param in stmt.type_params),
                variants,
            )
            next_id += 1
        self._enum_layouts = layouts
        self._enum_names = {
            stmt.name.lexeme: stmt
            for stmt in statements
            if isinstance(stmt, EnumDecl)
        }

    def _cstring_ptr(self, message: str) -> Any:
        return llvm_ir.cstring_pointer(self.builder, self._cstring(message))

    def _enum_decl(self, stmt: EnumDecl) -> None:
        # O layout já foi registrado; a declaração não aloca valor em runtime.
        return

    def _enum_of(self, expr: Any) -> EnumTy | None:
        ty = self.types.get(expr)
        return ty if isinstance(ty, EnumTy) else None

    def _enum_payload_descs(
        self, layout: EnumLayout, enum_ty: EnumTy
    ) -> dict[str, tuple[TypeDesc, ...]]:
        mapping = {
            name: arg
            for name, arg in zip(layout.type_params, enum_ty.args, strict=False)
            if not (isinstance(arg, TyVar) and arg.name == name)
        }
        saved = self._type_subst
        try:
            self._type_subst = {**saved, **mapping}
            return {
                variant.name: tuple(
                    self._type_desc(self._subst_ty(item), None)
                    for item in variant.payload
                )
                for variant in layout.variants
            }
        finally:
            self._type_subst = saved

    def _enum_build(
        self,
        layout: EnumLayout,
        variant: EnumVariantLayout,
        expr: Call,
        payload: list[Value],
    ) -> Value:
        count = len(payload)
        raw = self.builder.call(
            self._function(
                "lox_enum_new", _I8_PTR, [_INT, _I8_PTR, _I8_PTR, _INT]
            ),
            [
                llvm_ir.constant(_INT, layout.enum_id),
                self._cstring_ptr(layout.name),
                self._cstring_ptr(variant.name),
                llvm_ir.constant(_INT, count),
            ],
        )
        for index, argument in enumerate(payload):
            boxed = self._box_value(argument, None)
            self.builder.call(
                self._function(
                    "lox_enum_set", _VOID, [_I8_PTR, _INT, _INT, _INT]
                ),
                [
                    raw,
                    llvm_ir.constant(_INT, index),
                    self.builder.extract_value(boxed.llvm, 0),
                    self.builder.extract_value(boxed.llvm, 1),
                ],
            )
        return Value(ValueType.ENUM, raw)

    def _enum_value(
        self, layout: EnumLayout, variant: EnumVariantLayout, expr: Any
    ) -> Value:
        enum_ty = self._enum_of(expr)
        payload: list[Value] = []
        for index, argument in enumerate(expr.arguments):
            if index >= len(variant.payload):
                break
            value = self._expr(argument)
            expected: TypeDesc | None = None
            if enum_ty is not None:
                try:
                    descs = self._enum_payload_descs(layout, enum_ty)
                    expected = descs[variant.name][index]
                except Exception:
                    expected = None
            payload.append(
                self._coerce(value, expected, expr.paren.line)
                if expected is not None
                else value
            )
        return self._enum_build(layout, variant, expr, payload)

    def _enum_construct(self, expr: Call) -> Value:
        assert isinstance(expr.callee, Get)
        assert hasattr(expr.callee.object, "name")
        enum_name = expr.callee.object.name.lexeme
        layout = self._enum_layouts.get(enum_name)
        if layout is None:
            raise _unsupported(f"Enum '{enum_name}'", expr.paren.line)
        variant = layout.variant(expr.callee.name.lexeme)
        if variant is None:
            raise _unsupported(
                f"Variant '{enum_name}.{expr.callee.name.lexeme}'",
                expr.paren.line,
            )
        if len(expr.arguments) != len(variant.payload):
            self._poison(
                expr.paren,
                f"Expected {len(variant.payload)} arguments but got "
                f"{len(expr.arguments)}.",
                code=Code.RUNTIME_ARITY,
            )
            return Value(ValueType.ENUM, llvm_ir.null_pointer())
        return self._enum_value(layout, variant, expr)

    def _enum_get(self, expr: Get) -> Value:
        assert hasattr(expr.object, "name")
        enum_name = expr.object.name.lexeme
        layout = self._enum_layouts.get(enum_name)
        if layout is None:
            raise _unsupported(f"Enum '{enum_name}'", expr.name.line)
        variant = layout.variant(expr.name.lexeme)
        if variant is None:
            raise _unsupported(f"Enum variant '{expr.name.lexeme}'", expr.name.line)
        if variant.payload:
            raise _unsupported(
                "Enum variant with payload as a value", expr.name.line
            )
        return self._enum_build(layout, variant, None, [])  # type: ignore[arg-type]

    def _match(self, expr: Match) -> Value:
        scrutinee = self._expr(expr.scrutinee)
        if scrutinee.ty is ValueType.ANY:
            scrutinee = self._unbox_any(
                scrutinee, TypeDesc(ValueType.ENUM), expr.keyword.line
            )
        if scrutinee.ty is not ValueType.ENUM:
            raise _unsupported("match on non-enum", expr.keyword.line)
        enum_ty = self._enum_of(expr.scrutinee)
        if enum_ty is None:
            raise _unsupported("match enum type", expr.keyword.line)
        layout = self._enum_layouts.get(enum_ty.name)
        print("DEBUG match", enum_ty, self.types.get(expr.scrutinee))
        if layout is None:
            raise _unsupported(f"Enum '{enum_ty.name}'", expr.keyword.line)

        result_desc = self._type_desc(self.types[expr], expr.keyword.line)
        end = llvm_ir.append_block(self._function_ir, "match.end")
        incoming: list[tuple[Any, Any]] = []

        for arm in expr.arms:
            pattern = arm.pattern
            body = llvm_ir.append_block(self._function_ir, "match.arm")
            next_block = llvm_ir.append_block(self._function_ir, "match.next")
            if isinstance(pattern, WildcardPattern):
                self.builder.branch(body)
            else:
                assert isinstance(pattern, VariantPattern)
                variant = layout.variant(pattern.variant.lexeme)
                if variant is None:
                    raise _unsupported(
                        f"Variant '{pattern.variant.lexeme}'", pattern.variant.line
                    )
                check = self.builder.call(
                    self._function(
                        "lox_enum_variant_index",
                        _INT,
                        [_I8_PTR, _I8_PTR],
                    ),
                    [scrutinee.llvm, self._cstring_ptr(variant.name)],
                )
                matched = self.builder.icmp_signed(
                    "!=", check, llvm_ir.constant(_INT, 0)
                )
                self.builder.cbranch(matched, body, next_block)

            self.builder = llvm_ir.builder(body)
            self._scopes.append({})
            try:
                if isinstance(pattern, VariantPattern):
                    descs = self._enum_payload_descs(layout, enum_ty)
                    for index, (binding, desc) in enumerate(
                        zip(pattern.bindings, descs[variant.name], strict=False)
                    ):
                        raw = self.builder.call(
                            self._function(
                                "lox_enum_payload",
                                _ANY,
                                [_I8_PTR, _INT, _I32, _I32],
                            ),
                            [
                                scrutinee.llvm,
                                llvm_ir.constant(_INT, index),
                                llvm_ir.constant(_I32, binding.line),
                                llvm_ir.constant(_I32, binding.column),
                            ],
                        )
                        value = self._unbox_value(raw, desc, binding.line)
                        slot = self.builder.alloca(
                            self._storage_llvm_type(desc), name=binding.lexeme
                        )
                        self.builder.store(value.llvm, slot)
                        self._scopes[-1][binding.lexeme] = Binding(
                            slot,
                            desc.ty,
                            desc.fn,
                            desc.optional,
                            class_name=desc.class_name,
                            interface_name=desc.interface_name,
                        )
                value = self._coerce(
                    self._expr(arm.body), result_desc, expr.keyword.line
                )
            finally:
                self._scopes.pop()
            if not self.builder.block.is_terminated:
                self.builder.branch(end)
                incoming.append((value, self.builder.block))
            self.builder = llvm_ir.builder(next_block)

        # O checker garante exaustividade; o bloco final é só uma salvaguarda.
        if not self.builder.block.is_terminated:
            self.builder.branch(end)
            incoming.append(
                (
                    self._zero_desc(result_desc),
                    self.builder.block,
                )
            )
        self.builder = llvm_ir.builder(end)
        if not incoming:
            return self._zero_desc(result_desc)
        if result_desc.ty is ValueType.NIL:
            return Value(ValueType.NIL)
        merged = self.builder.phi(
            self._storage_llvm_type(result_desc), "match.value"
        )
        for value, block in incoming:
            merged.add_incoming(value.llvm, block)
        return Value(
            result_desc.ty,
            merged,
            result_desc.fn,
            result_desc.optional,
            result_desc.class_name,
            interface_name=result_desc.interface_name,
        )
