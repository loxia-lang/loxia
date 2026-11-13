"""Tipos de representação, optionais e coerções do lowering (ADR-0045/0047)."""

from __future__ import annotations

from typing import Any

from src.backend import llvm_ir
from src.backend.lower_base import LoweringBase
from src.backend.lower_model import (
    _ANY,
    _BOOL,
    _FLOAT,
    _I8_PTR,
    _INT,
    _VOID,
    ANY_TAG_BOOL,
    ANY_TAG_CLASS,
    ANY_TAG_FLOAT,
    ANY_TAG_FUNCTION,
    ANY_TAG_INSTANCE,
    ANY_TAG_INT,
    ANY_TAG_NIL,
    ANY_TAG_STRING,
    NUMERIC,
    BackendError,
    FnSig,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
)
from src.frontend.expr import Expr
from src.frontend.token_type import TokenType
from src.frontend.ty import ANY as TY_ANY
from src.frontend.ty import BOOL as TY_BOOL
from src.frontend.ty import FLOAT as TY_FLOAT
from src.frontend.ty import INT as TY_INT
from src.frontend.ty import NIL as TY_NIL
from src.frontend.ty import STRING as TY_STRING
from src.frontend.ty import (
    ClassObjectTy,
    ClassTy,
    FnTy,
    GenericFnTy,
    Ty,
    UnionTy,
)


class OptionalLowering(LoweringBase):
    def _type_desc(self, ty: Ty, line: int | None) -> TypeDesc:
        if ty is TY_INT:
            return TypeDesc(ValueType.INT)
        if ty is TY_FLOAT:
            return TypeDesc(ValueType.FLOAT)
        if ty is TY_BOOL:
            return TypeDesc(ValueType.BOOL)
        if ty is TY_STRING:
            return TypeDesc(ValueType.STRING)
        if ty is TY_NIL:
            return TypeDesc(ValueType.NIL)
        if ty is TY_ANY:
            return TypeDesc(ValueType.ANY)
        if isinstance(ty, UnionTy):
            members = ty.members
            non_nil = [member for member in members if member is not TY_NIL]
            if len(members) == 2 and len(non_nil) == 1:
                inner = self._type_desc(non_nil[0], line)
                if inner.ty is ValueType.NIL or inner.optional:
                    raise _unsupported("Nested optionals", line)
                return TypeDesc(inner.ty, inner.fn, True, inner.class_name)

            descs = [self._type_desc(member, line) for member in non_nil]
            if all(
                desc.ty
                in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL, ValueType.STRING)
                for desc in descs
            ):
                return TypeDesc(ValueType.ANY)
            raise _unsupported("Union of non-scalar values", line)

        if isinstance(ty, ClassTy):
            if ty.args:
                raise _unsupported("Generic class instances", line)
            if ty.name not in self._class_names:
                raise _unsupported(f"Class '{ty.name}'", line)
            return TypeDesc(ValueType.INSTANCE, class_name=ty.name)
        if isinstance(ty, ClassObjectTy):
            if ty.name not in self._class_names:
                raise _unsupported(f"Class '{ty.name}'", line)
            return TypeDesc(ValueType.CLASS, class_name=ty.name)

        if isinstance(ty, FnTy):
            params = tuple(self._type_desc(param, line) for param in ty.params)
            for param in params:
                if param.ty is ValueType.NIL:
                    raise _unsupported("A Nil parameter", line)
            ret = self._type_desc(ty.ret, line)
            return TypeDesc(ValueType.FUNCTION, FnSig(params, ret, ty.min_params))
        if isinstance(ty, GenericFnTy):
            raise _unsupported("Generic function value", line)

        raise _unsupported(f"Type '{ty}'", line)

    def _llvm_type(self, ty: ValueType) -> Any:
        match ty:
            case ValueType.INT:
                return _INT
            case ValueType.FLOAT:
                return _FLOAT
            case ValueType.BOOL:
                return _BOOL
            case ValueType.STRING:
                return _I8_PTR
            case ValueType.FUNCTION:
                return _I8_PTR
            case ValueType.CLASS | ValueType.INSTANCE:
                return _I8_PTR
            case ValueType.ANY:
                return _ANY
            case ValueType.NIL:
                return _VOID

    def _expr_type_desc(self, expr: Expr, line: int | None) -> TypeDesc:
        ty = self.types.get(expr)
        if ty is None:
            raise _unsupported("Type information for an expression", line)
        return self._type_desc(ty, line)

    def _storage_llvm_type(self, desc: TypeDesc) -> Any:
        if not desc.optional:
            return self._llvm_type(desc.ty)
        if desc.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return llvm_ir.literal_struct([_BOOL, self._llvm_type(desc.ty)])
        # Referências opcionais são ponteiro nulo; o L2.5 só habilita escalares.
        return self._llvm_type(desc.ty)

    def _zero_desc(self, desc: TypeDesc) -> Value:
        if not desc.optional:
            return self._zero(desc.ty)
        if desc.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            ty = self._storage_llvm_type(desc)
            return Value(desc.ty, llvm_ir.zero_value(ty), desc.fn, True)
        return Value(desc.ty, llvm_ir.null_pointer(), desc.fn, True)

    def _zero(self, ty: ValueType) -> Value:
        match ty:
            case ValueType.INT:
                return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
            case ValueType.FLOAT:
                return Value(ValueType.FLOAT, llvm_ir.float_constant(0.0))
            case ValueType.BOOL:
                return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))
            case ValueType.STRING:
                return Value(ValueType.STRING, llvm_ir.null_pointer())
            case ValueType.FUNCTION:
                return Value(ValueType.FUNCTION, llvm_ir.null_pointer())
            case ValueType.CLASS | ValueType.INSTANCE:
                return Value(ty, llvm_ir.null_pointer())
            case ValueType.ANY:
                return Value(ValueType.ANY, llvm_ir.zero_value(_ANY))
            case ValueType.NIL:
                return Value(ValueType.NIL)

    def _some(self, desc: TypeDesc, value: Value) -> Value:
        """Constrói `{1, payload}` (escalar) ou devolve o ponteiro não nulo."""
        if not desc.optional:
            raise BackendError("Invalid optional construction.", None)
        if desc.ty not in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return Value(
                desc.ty,
                value.llvm,
                desc.fn,
                True,
                desc.class_name,
            )

        aggregate = llvm_ir.zero_value(self._storage_llvm_type(desc))
        tagged = self.builder.insert_value(
            aggregate, llvm_ir.constant(_BOOL, 1), 0
        )
        return Value(
            desc.ty,
            self.builder.insert_value(tagged, value.llvm, 1),
            desc.fn,
            True,
            desc.class_name,
        )

    def _optional_tag(self, value: Value) -> Any:
        if value.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return self.builder.extract_value(value.llvm, 0)
        return self.builder.icmp_signed(
            "!=", value.llvm, llvm_ir.null_pointer()
        )

    def _optional_payload(self, value: Value) -> Value:
        if value.ty in (ValueType.INT, ValueType.FLOAT, ValueType.BOOL):
            return Value(
                value.ty,
                self.builder.extract_value(value.llvm, 1),
                value.sig,
                False,
                value.class_name,
            )
        return Value(
            value.ty,
            value.llvm,
            value.sig,
            False,
            value.class_name,
        )

    def _box_value(self, value: Value, line: int | None) -> Value:
        if value.ty is ValueType.ANY:
            return value
        if value.optional:
            raise _unsupported("Boxing an optional value", line)

        tag = {
            ValueType.NIL: ANY_TAG_NIL,
            ValueType.INT: ANY_TAG_INT,
            ValueType.FLOAT: ANY_TAG_FLOAT,
            ValueType.BOOL: ANY_TAG_BOOL,
            ValueType.STRING: ANY_TAG_STRING,
            ValueType.CLASS: ANY_TAG_CLASS,
            ValueType.INSTANCE: ANY_TAG_INSTANCE,
            ValueType.FUNCTION: ANY_TAG_FUNCTION,
        }.get(value.ty)
        if tag is None:
            raise _unsupported(f"Boxing {value.ty.name}", line)

        if value.ty is ValueType.NIL:
            payload = llvm_ir.constant(_INT, 0)
        elif value.ty is ValueType.FLOAT:
            payload = self.builder.bitcast(value.llvm, _INT)
        elif value.ty is ValueType.BOOL:
            payload = self.builder.zext(value.llvm, _INT)
        elif value.ty is ValueType.INT:
            payload = value.llvm
        else:
            payload = self.builder.ptrtoint(value.llvm, _INT)

        aggregate = llvm_ir.zero_value(_ANY)
        aggregate = self.builder.insert_value(
            aggregate, llvm_ir.constant(_INT, tag), 0
        )
        aggregate = self.builder.insert_value(aggregate, payload, 1)
        return Value(ValueType.ANY, aggregate)

    def _unwrap(self, value: Value, line: int, message: str) -> Value:
        """Extrai o payload de um `T?`; tag 0 vira `lox_panic` no ponto."""
        if not value.optional:
            return value

        tag = self._optional_tag(value)
        ok = llvm_ir.append_block(self._function_ir, "opt.ok")
        bad = llvm_ir.append_block(self._function_ir, "opt.nil")
        self.builder.cbranch(tag, ok, bad)

        self.builder = llvm_ir.builder(bad)
        self._poison(line, message)

        self.builder = llvm_ir.builder(ok)
        return self._optional_payload(value)

    def _unwrap_operand(self, value: Value, line: int, message: str) -> Value:
        if value.optional:
            return self._unwrap(value, line, message)
        if value.ty is ValueType.NIL:
            self._poison(line, message)
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
        return value

    def _coerce(self, value: Value, expected: TypeDesc, line: int | None) -> Value:
        """Converte `nil`/`T` para `T?` e faz unwrap checado de `T?` para `T`."""
        if expected.ty is ValueType.NIL:
            if value.ty is ValueType.NIL:
                return value
            raise BackendError(
                f"Can't use {value.ty.name} where Nil is expected.", line
            )

        if expected.ty is ValueType.ANY:
            return self._box_value(value, line)

        if value.ty is ValueType.ANY:
            raise _unsupported("Unboxing Any implicitly", line)

        if expected.optional:
            if value.ty is ValueType.NIL:
                return self._zero_desc(expected)
            if value.optional:
                inner = TypeDesc(value.ty, value.sig, False, value.class_name)
                if not inner.same_as(TypeDesc(expected.ty, expected.fn, False, expected.class_name)):
                    raise BackendError(
                        f"Can't use {value.ty.name}? where "
                        f"{expected.ty.name}? is expected.",
                        line,
                    )
                return value

            actual = value.desc
            if not actual.same_as(
                TypeDesc(expected.ty, expected.fn, False, expected.class_name)
            ):
                raise BackendError(
                    f"Can't use {value.ty.name} where {expected.ty.name}? "
                    "is expected.",
                    line,
                )
            return self._some(expected, value)

        if value.ty is ValueType.NIL:
            raise BackendError(
                f"Can't use nil where {expected.ty.name} is expected.", line
            )

        if value.optional:
            inner = TypeDesc(value.ty, value.sig, False, value.class_name)
            if not inner.same_as(expected):
                raise BackendError(
                    f"Can't use {value.ty.name}? where {expected.ty.name} "
                    "is expected.",
                    line,
                )
            return self._unwrap(value, line or 0, "Can't use nil value.")

        if not value.desc.same_as(expected):
            raise BackendError(
                f"Can't use {value.ty.name} where {expected.ty.name} is expected.",
                line,
            )
        return value

    def _optional_equality(
        self, left: Value, right: Value, operator: TokenType
    ) -> Value:
        equal = operator is TokenType.EQUAL_EQUAL
        if left.ty is ValueType.NIL or right.ty is ValueType.NIL:
            return self._equality_with_nil(left, right, equal)
        if left.optional and right.optional:
            return self._equality_both_optional(left, right, equal)
        if left.optional or right.optional:
            return self._equality_one_optional(left, right, equal)
        return self._plain_equality(left, right, operator)

    def _equality_with_nil(
        self, left: Value, right: Value, equal: bool
    ) -> Value:
        true = llvm_ir.constant(_BOOL, 1)
        false = llvm_ir.constant(_BOOL, 0)
        if left.ty is ValueType.NIL and right.ty is ValueType.NIL:
            return Value(ValueType.BOOL, true if equal else false)
        optional = right if left.ty is ValueType.NIL else left
        if not optional.optional:
            return Value(ValueType.BOOL, false if equal else true)
        tag = self._optional_tag(optional)
        is_nil = self.builder.icmp_signed(
            "==", tag, llvm_ir.constant(_BOOL, 0)
        )
        return Value(
            ValueType.BOOL,
            is_nil if equal else self.builder.not_(is_nil),
        )

    def _equality_both_optional(
        self, left: Value, right: Value, equal: bool
    ) -> Value:
        if not left.desc.same_as(right.desc) and not (
            left.ty in NUMERIC and right.ty in NUMERIC
        ):
            return Value(
                ValueType.BOOL,
                llvm_ir.constant(_BOOL, 0 if equal else 1),
            )

        left_tag = self._optional_tag(left)
        right_tag = self._optional_tag(right)
        both_nil = self.builder.and_(
            self.builder.not_(left_tag), self.builder.not_(right_tag)
        )
        both_some = self.builder.and_(left_tag, right_tag)
        payload_equal = self._plain_equality(
            self._optional_payload(left),
            self._optional_payload(right),
            TokenType.EQUAL_EQUAL,
        ).llvm
        result = self.builder.or_(
            both_nil, self.builder.and_(both_some, payload_equal)
        )
        return Value(
            ValueType.BOOL,
            result if equal else self.builder.not_(result),
        )

    def _equality_one_optional(
        self, left: Value, right: Value, equal: bool
    ) -> Value:
        optional = left if left.optional else right
        other = right if left.optional else left
        inner = TypeDesc(optional.ty, optional.sig, False, optional.class_name)
        if not inner.same_as(other.desc) and not (
            optional.ty in NUMERIC and other.ty in NUMERIC
        ):
            return Value(
                ValueType.BOOL,
                llvm_ir.constant(_BOOL, 0 if equal else 1),
            )

        tag = self._optional_tag(optional)
        payload = self._optional_payload(optional)
        if left.optional:
            payload_equal = self._plain_equality(
                payload, other, TokenType.EQUAL_EQUAL
            ).llvm
        else:
            payload_equal = self._plain_equality(
                other, payload, TokenType.EQUAL_EQUAL
            ).llvm

        result = self.builder.and_(tag, payload_equal)
        return Value(
            ValueType.BOOL,
            result if equal else self.builder.not_(result),
        )
