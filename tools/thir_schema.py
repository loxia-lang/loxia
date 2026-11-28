# SPDX-License-Identifier: MIT OR Apache-2.0
"""Generate schema/thir-v1.json from the THIR dataclasses.

O schema é contrato, não uma segunda fonte de verdade: nomes de campo e tipos vêm dos
mesmos dataclasses que `thir.serialize` grava. `--check` compara o arquivo versionado com
o gerado; `--write` regenera.

Diferenças em relação ao `ast_schema`: o discriminador é `k` com o **nome da classe**
(`TBinary`, `Decl`, `Ref`) e `Ty` é um objeto estruturado (`k` + campos), não a forma
`display()` — o motor não deve precisar de um parser de tipo (ADR-0154).
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from loxia_core.diagnostics.diagnostic import Span
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.ty import Ty
from loxia_core.thir import model

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "thir-v1.json"


def _node_classes() -> dict[str, type[object]]:
    return {
        name: value
        for name, value in vars(model).items()
        if isinstance(value, type) and is_dataclass(value) and value.__module__ == model.__name__
    }


# Toda subclasse direta de `Ty` precisa de um kind no schema e no serializador; o teste
# compara esta lista com `Ty.__subclasses__()` para o drift não passar silencioso.
TY_CLASSES = (
    "Prim",
    "TyVar",
    "ListTy",
    "MapTy",
    "TupleTy",
    "ClassTy",
    "EnumTy",
    "EnumObjectTy",
    "ClassObjectTy",
    "InterfaceTy",
    "NativeModuleTy",
    "UnionTy",
    "FnTy",
    "GenericFnTy",
    "NativeFnTy",
)


# Classes-base que só existem para agrupar: o payload traz o `k` da subclasse concreta,
# então o schema é um `oneOf` delas (como `$defs/node` no ast-v2).
_BASES = ("TExpr", "TStmt", "TPattern", "TDestructurePattern")


def _ref(name: str) -> dict[str, object]:
    return {"$ref": f"#/$defs/{name}"}


def _variant(kind: str, fields_: dict[str, object]) -> dict[str, object]:
    properties: dict[str, object] = {"k": {"const": kind}, **fields_}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def _ty_schema() -> dict[str, object]:
    """`Ty` é estruturado (não `display()`), então o schema é escrito por variante."""
    ty = _ref("Ty")
    return {
        "oneOf": [
            _variant("prim", {"name": _type_schema(str)}),
            _variant(
                "var",
                {
                    "name": _type_schema(str),
                    "id": _type_schema(int),
                    "bounds": {"type": "array", "items": _type_schema(str)},
                },
            ),
            _variant("list", {"element": ty}),
            _variant("map", {"key": ty, "value": ty}),
            _variant("tuple", {"items": {"type": "array", "items": ty}}),
            _variant(
                "class",
                {"name": _type_schema(str), "args": {"type": "array", "items": ty}},
            ),
            _variant(
                "enum",
                {"name": _type_schema(str), "args": {"type": "array", "items": ty}},
            ),
            _variant("enum_object", {"name": _type_schema(str)}),
            _variant("class_object", {"name": _type_schema(str)}),
            _variant("interface", {"name": _type_schema(str)}),
            _variant("native_module", {"name": _type_schema(str)}),
            _variant("union", {"members": {"type": "array", "items": ty}}),
            _variant(
                "fn",
                {
                    "params": {"type": "array", "items": ty},
                    "ret": ty,
                    "min_params": _type_schema(int),
                    "variadic": _type_schema(bool),
                },
            ),
            _variant(
                "generic_fn",
                {
                    "name": _type_schema(str),
                    "type_params": {"type": "array", "items": ty},
                    "fn": ty,
                },
            ),
            _variant("native_fn", {"name": _type_schema(str)}),
        ]
    }


def _type_schema(tp: object) -> dict[str, object]:
    if isinstance(tp, type) and issubclass(tp, Ty):
        return _ref("Ty")
    if isinstance(tp, type) and tp.__name__ in _BASES:
        return _ref(tp.__name__)
    if tp is Span:
        return _ref("span")
    if tp is TokenType:
        return {"type": "string", "enum": [item.name for item in TokenType]}
    if isinstance(tp, type) and issubclass(tp, Enum):
        return {"type": "string", "enum": [item.name for item in tp]}
    if tp is type(None):
        return {"type": "null"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is str:
        return {"type": "string"}
    if tp is object or tp is Any:
        return {}
    if isinstance(tp, type) and is_dataclass(tp):
        return _ref(cast(type[object], tp).__name__)

    origin = get_origin(tp)
    args = get_args(tp)
    if origin is Union or origin is types.UnionType:
        return {"anyOf": [_type_schema(arg) for arg in args]}
    if origin in (list, tuple):
        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": _type_schema(args[0])}
        if origin is tuple and len(args) > 1:
            return {
                "type": "array",
                "prefixItems": [_type_schema(arg) for arg in args],
                "minItems": len(args),
                "maxItems": len(args),
            }
        return {"type": "array", "items": _type_schema(args[0]) if args else {}}
    return {}


def _node_schema(cls: type[object]) -> dict[str, object]:
    hints = get_type_hints(cls)
    properties: dict[str, object] = {"k": {"const": cls.__name__}}
    required = ["k"]
    for item in fields(cast(Any, cls)):
        properties[item.name] = _type_schema(hints[item.name])
        required.append(item.name)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def build_schema() -> dict[str, object]:
    definitions: dict[str, object] = {
        "position": {
            "type": "object",
            "additionalProperties": False,
            "required": ["line", "column", "offset"],
            "properties": {
                "line": {"type": "integer", "minimum": 1},
                "column": {"type": ["integer", "null"], "minimum": 1},
                "offset": {"type": ["integer", "null"], "minimum": 0},
            },
        },
        "span": {
            "type": "object",
            "additionalProperties": False,
            "required": ["file", "start", "end"],
            "properties": {
                "file": {"type": "string"},
                "start": _ref("position"),
                "end": _ref("position"),
            },
        },
        "Ty": _ty_schema(),
    }
    classes = _node_classes()
    for name, cls in classes.items():
        if name in _BASES:
            continue
        definitions[name] = _node_schema(cls)
    for base in _BASES:
        parent = classes[base]
        definitions[base] = {
            "oneOf": [
                _ref(name)
                for name, cls in sorted(classes.items())
                if name != base and issubclass(cls, parent)
            ]
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://loxia-lang.github.io/loxia/schema/thir-v1.json",
        "title": "Loxia THIR v1",
        "description": "Contrato tipado entre o checker e os motores (ADR-0149, ADR-0154).",
        **_ref("TModule"),
        "$defs": definitions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="compara com o arquivo versionado")
    group.add_argument("--write", action="store_true", help="regenera o arquivo")
    args = parser.parse_args(argv)

    text = json.dumps(build_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.write:
        SCHEMA_PATH.write_text(text, encoding="utf-8")
        sys.stdout.write(f"wrote {SCHEMA_PATH.relative_to(ROOT)}\n")
        return 0
    current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
    if current != text:
        sys.stderr.write(
            f"{SCHEMA_PATH.relative_to(ROOT)} is stale; run `make thir-schema` "
            "(uv run python tools/thir_schema.py --write)\n"
        )
        return 1
    sys.stdout.write("thir schema is current\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
