# SPDX-License-Identifier: MIT OR Apache-2.0
"""Serialização do THIR: JSON v1 determinístico, com round-trip.

O THIR é o contrato entre o checker Python (build-time) e os motores em Loxia (runtime);
por isso ele é **serializado** e versionado (ADR-0149 §2, ADR-0154). Este módulo é a única
implementação do formato: `to_payload`/`from_payload` e os helpers de texto.

Formato:

- um documento por unidade de compilação; o topo é o próprio `TModule` com `k: "TModule"`
  e `schema_version` (só muda em quebra do contrato);
- todo registro vira `{"k": <Classe>, ...campos}`; enums viram o nome (`"LOCAL"`,
  `"MINUS"`); `Ty` vira um objeto estruturado com `k` (não a forma `display()`): o motor
  não deve precisar de um parser de tipo para ler o contrato;
- `Span` vira `{file, start:{line,column,offset}, end:{...}}`;
- Float não finito vira `{"non_finite_float": "inf"}` (JSON estrito não os tem), como no
  `ast_json` (ADR-0129).

Determinismo (I3): dicionários são emitidos com `sort_keys`, listas preservam a ordem
canônica do modelo (ids, capturas por nome, instâncias ordenadas), e nenhuma estrutura
derivada de `set` chega aqui. Dois builds do mesmo programa produzem o **mesmo texto**.
"""

from __future__ import annotations

import json
import math
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from loxia_core.diagnostics.diagnostic import Position, Span
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.ty import (
    ClassObjectTy,
    ClassTy,
    EnumObjectTy,
    EnumTy,
    FnTy,
    GenericFnTy,
    InterfaceTy,
    ListTy,
    MapTy,
    NativeFnTy,
    NativeModuleTy,
    Prim,
    TupleTy,
    Ty,
    TyVar,
    UnionTy,
)
from loxia_core.thir import model as thir_model
from loxia_core.thir.model import THIR_SCHEMA_VERSION, TModule


class ThirFormatError(ValueError):
    """Payload fora do contrato: versão desconhecida, `k` errado ou tipo não suportado."""


# --- texto --------------------------------------------------------------------


def dumps(module: TModule) -> str:
    """Saída legível, determinística e terminada em newline (revisão/snapshot)."""
    return json.dumps(_encode(module), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical(module: TModule) -> str:
    """Forma compacta e ordenada; é o que o snapshot hasheia."""
    return json.dumps(_encode(module), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(text: str) -> TModule:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ThirFormatError("THIR payload must be a JSON object")
    return from_payload(payload)


def to_payload(module: TModule) -> dict[str, object]:
    payload = _encode(module)
    assert isinstance(payload, dict)
    return payload


def from_payload(payload: dict[str, object]) -> TModule:
    module = _decode(payload, TModule)
    if not isinstance(module, TModule):
        raise ThirFormatError("THIR payload does not describe a TModule")
    if module.schema_version != THIR_SCHEMA_VERSION:
        raise ThirFormatError(
            f"unsupported THIR schema_version {module.schema_version} "
            f"(expected {THIR_SCHEMA_VERSION})"
        )
    return module


# --- codificação ---------------------------------------------------------------


def _encode(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            # Mesmo marcador do ast_json: distingue o Float infinito da String "inf".
            return {"non_finite_float": repr(value)}
        return value
    if isinstance(value, Ty):
        return _encode_ty(value)
    if isinstance(value, Span):
        return _encode_span(value)
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        payload: dict[str, object] = {"k": type(value).__name__}
        for item in fields(value):
            payload[item.name] = _encode(getattr(value, item.name))
        return payload
    raise ThirFormatError(f"unsupported THIR value: {type(value).__name__}")


def _encode_span(span: Span) -> dict[str, object]:
    return {
        "file": span.file,
        "start": _encode_position(span.start),
        "end": _encode_position(span.end),
    }


def _encode_position(position: Position) -> dict[str, object]:
    return {"line": position.line, "column": position.column, "offset": position.offset}


def _encode_ty(ty: Ty) -> dict[str, object]:
    if isinstance(ty, Prim):
        return {"k": "prim", "name": ty.name}
    if isinstance(ty, TyVar):
        return {"k": "var", "name": ty.name, "id": ty.id, "bounds": list(ty.bounds)}
    if isinstance(ty, ListTy):
        return {"k": "list", "element": _encode_ty(ty.element)}
    if isinstance(ty, MapTy):
        return {"k": "map", "key": _encode_ty(ty.key), "value": _encode_ty(ty.value)}
    if isinstance(ty, TupleTy):
        return {"k": "tuple", "items": [_encode_ty(item) for item in ty.items]}
    if isinstance(ty, ClassTy):
        # `token` é metadado do parser (posição no fonte), não semântica: não serializa.
        return {"k": "class", "name": ty.name, "args": [_encode_ty(arg) for arg in ty.args]}
    if isinstance(ty, EnumTy):
        return {"k": "enum", "name": ty.name, "args": [_encode_ty(arg) for arg in ty.args]}
    if isinstance(ty, EnumObjectTy):
        return {"k": "enum_object", "name": ty.name}
    if isinstance(ty, ClassObjectTy):
        return {"k": "class_object", "name": ty.name}
    if isinstance(ty, InterfaceTy):
        return {"k": "interface", "name": ty.name}
    if isinstance(ty, NativeModuleTy):
        return {"k": "native_module", "name": ty.name}
    if isinstance(ty, UnionTy):
        return {"k": "union", "members": [_encode_ty(member) for member in ty.members]}
    if isinstance(ty, FnTy):
        return {
            "k": "fn",
            "params": [_encode_ty(param) for param in ty.params],
            "ret": _encode_ty(ty.ret),
            "min_params": ty.min_params,
            "variadic": ty.variadic,
        }
    if isinstance(ty, GenericFnTy):
        return {
            "k": "generic_fn",
            "name": ty.name,
            "type_params": [_encode_ty(param) for param in ty.type_params],
            "fn": _encode_ty(ty.fn),
        }
    if isinstance(ty, NativeFnTy):
        return {"k": "native_fn", "name": ty.name}
    raise ThirFormatError(f"unsupported Ty in THIR: {type(ty).__name__}")


# --- decodificação -------------------------------------------------------------


def _decode(value: object, annotation: object) -> object:
    if isinstance(value, dict) and set(value) == {"non_finite_float"}:
        return float(value["non_finite_float"])
    if annotation is None or annotation is Any or annotation is object:
        return value
    if isinstance(annotation, type) and issubclass(annotation, Ty):
        return _decode_ty(value)
    if annotation is Span:
        return _decode_span(value)
    if annotation is TokenType:
        return TokenType[str(value)]
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation[str(value)]
    origin = get_origin(annotation)
    if origin is types.UnionType or origin is Union:
        return _decode_union(value, get_args(annotation))
    if origin is tuple:
        return _decode_tuple(value, get_args(annotation))
    if origin is list:
        (item_annotation,) = get_args(annotation)
        return [_decode(item, item_annotation) for item in cast(list[object], value)]
    if is_dataclass(annotation) and isinstance(annotation, type):
        return _decode_record(value, annotation)
    if annotation in (int, str, bool, float):
        return value
    raise ThirFormatError(f"unsupported THIR annotation: {annotation!r}")


def _decode_union(value: object, args: tuple[object, ...]) -> object:
    if value is None:
        if type(None) in args:
            return None
        raise ThirFormatError("null for a non-optional THIR field")
    candidates = [arg for arg in args if arg is not type(None)]
    if len(candidates) == 1:
        return _decode(value, candidates[0])
    # Só `str | TExpr` cai aqui: a forma do valor decide o ramo.
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for arg in candidates:
            if isinstance(arg, type) and issubclass(arg, Ty):
                return _decode_ty(value)
            if arg is Span:
                return _decode_span(value)
            if is_dataclass(arg) and isinstance(arg, type):
                return _decode_record(value, arg)
    raise ThirFormatError(f"cannot decode THIR union value: {value!r}")


def _decode_tuple(value: object, args: tuple[object, ...]) -> tuple[object, ...]:
    items = cast(list[object], value)
    if not args:
        return tuple(items)
    if args[-1] is Ellipsis:
        (item_annotation,) = args[:1]
        return tuple(_decode(item, item_annotation) for item in items)
    if len(items) != len(args):
        raise ThirFormatError(f"THIR tuple arity {len(items)} != {len(args)}")
    return tuple(_decode(item, annotation) for item, annotation in zip(items, args, strict=True))


def _node_classes() -> dict[str, type[object]]:
    return {
        name: value
        for name, value in vars(thir_model).items()
        if isinstance(value, type)
        and is_dataclass(value)
        and value.__module__ == thir_model.__name__
    }


def _decode_record(value: object, cls: type[object]) -> object:
    if not isinstance(value, dict):
        raise ThirFormatError(f"THIR {cls.__name__} must be a JSON object")
    payload = cast(dict[str, object], value)
    kind = payload.get("k")
    if kind != cls.__name__:
        # Campo anotado com a base (`TExpr`, `TStmt`, `TPattern`): o `k` escolhe a
        # subclasse concreta.
        concrete = _node_classes().get(str(kind))
        if concrete is None or not issubclass(concrete, cls):
            raise ThirFormatError(f"expected THIR {cls.__name__}, got {kind!r}")
        return _decode_record(value, concrete)
    hints = get_type_hints(cls)
    kwargs: dict[str, object] = {}
    for item in fields(cast(Any, cls)):
        if item.name not in payload:
            continue
        kwargs[item.name] = _decode(payload[item.name], hints[item.name])
    return cast(Any, cls)(**kwargs)


def _decode_span(value: object) -> Span:
    payload = cast(dict[str, object], value)
    return Span(
        file=cast(str, payload.get("file", "")),
        start=_decode_position(cast(dict[str, object], payload["start"])),
        end=_decode_position(cast(dict[str, object], payload["end"])),
    )


def _decode_position(payload: dict[str, object]) -> Position:
    column = payload.get("column")
    offset = payload.get("offset")
    return Position(
        line=cast(int, payload["line"]),
        column=None if column is None else cast(int, column),
        offset=None if offset is None else cast(int, offset),
    )


def _decode_ty(value: object) -> Ty:
    payload = cast(dict[str, object], value)
    kind = payload.get("k")
    if kind == "prim":
        return Prim(cast(str, payload["name"]))
    if kind == "var":
        return TyVar(
            name=cast(str, payload["name"]),
            id=cast(int, payload["id"]),
            bounds=tuple(cast(list[str], payload.get("bounds", []))),
        )
    if kind == "list":
        return ListTy(_decode_ty(payload["element"]))
    if kind == "map":
        return MapTy(_decode_ty(payload["key"]), _decode_ty(payload["value"]))
    if kind == "tuple":
        return TupleTy(tuple(_decode_ty(item) for item in cast(list[object], payload["items"])))
    if kind == "class":
        return ClassTy(
            cast(str, payload["name"]),
            tuple(_decode_ty(arg) for arg in cast(list[object], payload["args"])),
        )
    if kind == "enum":
        return EnumTy(
            cast(str, payload["name"]),
            tuple(_decode_ty(arg) for arg in cast(list[object], payload["args"])),
        )
    if kind == "enum_object":
        return EnumObjectTy(cast(str, payload["name"]))
    if kind == "class_object":
        return ClassObjectTy(cast(str, payload["name"]))
    if kind == "interface":
        return InterfaceTy(cast(str, payload["name"]))
    if kind == "native_module":
        return NativeModuleTy(cast(str, payload["name"]))
    if kind == "union":
        return UnionTy(
            tuple(_decode_ty(member) for member in cast(list[object], payload["members"]))
        )
    if kind == "fn":
        return FnTy(
            params=tuple(_decode_ty(param) for param in cast(list[object], payload["params"])),
            ret=_decode_ty(payload["ret"]),
            min_params=cast(int, payload["min_params"]),
            variadic=cast(bool, payload.get("variadic", False)),
        )
    if kind == "generic_fn":
        return GenericFnTy(
            cast(str, payload["name"]),
            tuple(
                cast(TyVar, _decode_ty(param))
                for param in cast(list[object], payload["type_params"])
            ),
            cast(FnTy, _decode_ty(payload["fn"])),
        )
    if kind == "native_fn":
        return NativeFnTy(cast(str, payload["name"]))
    raise ThirFormatError(f"unsupported Ty kind in THIR: {kind!r}")
