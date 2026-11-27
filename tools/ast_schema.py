# SPDX-License-Identifier: MIT OR Apache-2.0
"""Generate schema/ast-v2.json from the AST dataclasses.

The schema is a contract, not a second source of truth: field names come from the
same dataclasses that `ast_json` serializes. `--check` compares the checked-in file
with the generated one; `--write` regenerates it.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import types
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from loxia_core.diagnostics.diagnostic import Span
from loxia_core.frontend import destructuring, expr, stmt
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import Ty

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "ast-v2.json"
SKIP_FIELDS = frozenset({"display_name"})
SKIP_CLASSES = frozenset({"Expr", "Stmt", "Visitor", "Position", "Span", "Ty"})


def _kind(name: str) -> str:
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _node_classes() -> dict[str, type[object]]:
    result: dict[str, type[object]] = {}
    for module in (expr, stmt, destructuring):
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__:
                continue
            if name in SKIP_CLASSES or not is_dataclass(cls):
                continue
            result[_kind(name)] = cls
    return result


def _is_node_type(tp: object) -> bool:
    if not isinstance(tp, type):
        return False
    node = cast(type[Any], tp)
    return node.__module__ in {
        expr.__name__,
        stmt.__name__,
        destructuring.__name__,
    } and is_dataclass(node)


def _type_schema(tp: object) -> dict[str, object]:
    if tp is Token:
        return {"$ref": "#/$defs/token_ref"}
    if tp is Ty:
        return {"type": "string"}
    if tp is Span:
        return {"$ref": "#/$defs/span"}
    if tp is expr.Expr or tp is stmt.Stmt:
        return {"$ref": "#/$defs/node"}
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
    if _is_node_type(tp):
        return {"$ref": f"#/$defs/{_kind(cast(type[Any], tp).__name__)}"}

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
    kind = _kind(cls.__name__)
    localns = {
        name: value
        for module in (expr, stmt, destructuring)
        for name, value in vars(module).items()
        if isinstance(value, type)
    }
    hints = get_type_hints(
        cls,
        globalns=vars(sys.modules[cls.__module__]),
        localns=localns,
    )
    properties: dict[str, object] = {
        "kind": {"const": kind},
        "span": {"oneOf": [{"$ref": "#/$defs/span"}, {"type": "null"}]},
    }
    required = ["kind", "span"]
    for item in fields(cast(Any, cls)):
        if item.name in SKIP_FIELDS:
            continue
        properties[item.name] = _type_schema(hints[item.name])
        required.append(item.name)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def build_schema() -> dict[str, object]:
    nodes = _node_classes()
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
            "required": ["start", "end"],
            "properties": {
                "start": {"$ref": "#/$defs/position"},
                "end": {"$ref": "#/$defs/position"},
            },
        },
        "token_ref": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "lexeme", "span"],
            "properties": {
                "type": {"type": "string"},
                "lexeme": {"type": "string"},
                "span": {"$ref": "#/$defs/span"},
            },
        },
        "token": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "lexeme", "span", "doc", "literal"],
            "properties": {
                "type": {"type": "string"},
                "lexeme": {"type": "string"},
                "span": {"$ref": "#/$defs/span"},
                "doc": {"type": ["string", "null"]},
                "literal": {},
            },
        },
        "trivia": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "text", "span"],
            "properties": {
                "kind": {
                    "enum": [
                        "whitespace",
                        "newline",
                        "line_comment",
                        "block_comment",
                        "doc_comment",
                        "other",
                    ]
                },
                "text": {"type": "string"},
                "span": {"$ref": "#/$defs/span"},
            },
        },
        "typed_expression": {
            "type": "object",
            "additionalProperties": False,
            "required": ["span", "type"],
            "properties": {
                "span": {"$ref": "#/$defs/span"},
                "type": {"type": "string"},
            },
        },
        "syntax": {
            "type": "object",
            "additionalProperties": False,
            "required": ["statements", "tokens", "trivia"],
            "properties": {
                "statements": {"type": "array", "items": {"$ref": "#/$defs/node"}},
                "tokens": {"type": "array", "items": {"$ref": "#/$defs/token"}},
                "trivia": {"type": "array", "items": {"$ref": "#/$defs/trivia"}},
            },
        },
        "typed": {
            "type": "object",
            "additionalProperties": False,
            "required": ["expressions"],
            "properties": {
                "expressions": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/typed_expression"},
                }
            },
        },
    }
    for kind, cls in sorted(nodes.items()):
        definitions[kind] = _node_schema(cls)
    # `anyOf` (não `oneOf`): os `kind` são únicos, então a primeira alternativa que casa
    # é a correta; `oneOf` obrigava o validador a testar todas as 50+ alternativas.
    definitions["node"] = {
        "anyOf": [{"$ref": f"#/$defs/{kind}"} for kind in sorted(nodes)],
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/loxia-lang/loxia/schema/ast-v2.json",
        "title": "Loxia AST v2",
        "description": "Machine-readable AST of `loxia ast --file-only --format=json`. Syntax is stable; typed is optional checker metadata.",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "kind", "file", "syntax"],
        "properties": {
            "schema_version": {"const": 2},
            "kind": {"const": "program"},
            "file": {"type": "string"},
            "syntax": {"$ref": "#/$defs/syntax"},
            "typed": {"$ref": "#/$defs/typed"},
        },
        "$defs": definitions,
    }


def render_schema() -> str:
    return json.dumps(build_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render_schema()
    if args.write:
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(text, encoding="utf-8")
        return 0
    if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text(encoding="utf-8") != text:
        print("schema/ast-v2.json is stale; run tools/ast_schema.py --write")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
