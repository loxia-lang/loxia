# SPDX-License-Identifier: MIT OR Apache-2.0
"""JSON determinístico da AST para o oráculo do front-end (ADR-0129).

O `AstPrinter` continua sendo o dump de debug (S-expression). Este módulo é o **contrato
de máquina** usado pelo port do parser em Lox: envelope versionado, tokens com spans
half-open e cada nó com `kind`, `span` e os campos da dataclass, em ordem de declaração.

Regras do contrato:

- só é válido para o modo **arquivo único** (`loxia ast --file-only`): a árvore não passou
  pelo loader, então nomes e imports são os do fonte, sem mangling;
- `span.start`/`end` são half-open, coluna 1-based em code points e offset 0-based em bytes
  UTF-8; spans de nós são derivados dos tokens contidos;
- tokens no array `tokens` são completos; tokens embutidos nos nós carregam só
  `type`/`lexeme`/`span` para não duplicar payload;
- `Ty` vira a forma canônica de `display()`; tipos de função/uniões saem como texto estável;
- a saída não contém caminho absoluto, PID, timestamp nem ordem de `set`/`dict`;
- `schema_version` muda só em quebra do contrato.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import fields, is_dataclass
from typing import Any, cast

from loxia_core.diagnostics.diagnostic import Position, Span
from loxia_core.frontend.spans import node_span, span_of_token_exact
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.trivia import Trivia
from loxia_core.frontend.ty import Ty, display

SCHEMA_VERSION = 2
_DISPLAY_ONLY = frozenset({"display_name"})

_TOKEN_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def dumps(payload: dict[str, object]) -> str:
    """Saída legível, determinística e terminada em newline."""
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def canonical(payload: dict[str, object]) -> str:
    """Forma compacta e ordenada; é o que o snapshot hasheia."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def program_payload(
    statements: list[Stmt],
    tokens: list[Token],
    file: str,
    *,
    trivia: list[Trivia] | tuple[Trivia, ...] = (),
    typed: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Envelope `program` v2: `syntax` estável e `typed` opcional."""
    memo: dict[int, Span | None] = {}
    syntax: dict[str, object] = {
        "statements": [_value(statement, memo) for statement in statements],
        "tokens": [_token(token, full=True) for token in tokens],
        "trivia": [_trivia(item) for item in trivia],
    }
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "program",
        "file": file,
        "syntax": syntax,
    }
    if typed is not None:
        payload["typed"] = {"expressions": typed}
    return payload


def _value(value: object, memo: dict[int, Span | None]) -> object:
    if isinstance(value, Token):
        return _token(value, full=False)
    if isinstance(value, Ty):
        return display(value)
    if isinstance(value, Span):
        return _span_json(value)
    if isinstance(value, (list, tuple)):
        return [_value(item, memo) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _float(value)
    if isinstance(value, str) or value is None:
        return value
    if _is_record(value):
        return _record(value, memo)
    raise TypeError(f"unsupported AST value: {type(value).__name__}")


def _float(value: float) -> object:
    # O scanner aceita `1e999` como Float; JSON estrito não tem Infinity/NaN. O marcador
    # mantém a distinção entre o Float infinito e a String `"inf"`.
    if math.isfinite(value):
        return value
    return {"non_finite_float": repr(value)}


def _record(value: object, memo: dict[int, Span | None]) -> dict[str, object]:
    payload: dict[str, object] = {"kind": _kind(type(value).__name__)}
    span = node_span(value, memo)
    payload["span"] = _span_json(span) if span is not None else None
    for item in fields(cast(Any, value)):
        if item.name in _DISPLAY_ONLY:
            continue
        payload[item.name] = _value(getattr(value, item.name), memo)
    return payload


def _token(token: Token, *, full: bool) -> dict[str, object]:
    if token.line < 1:
        raise ValueError("AST JSON requires source tokens; synthetic line 0 is not allowed")
    payload: dict[str, object] = {
        "type": token.type.name,
        "lexeme": token.lexeme,
        "span": _span_json(span_of_token_exact(token)),
    }
    if full:
        payload["doc"] = token.doc
        payload["literal"] = _value(token.literal, {})
    return payload


def span_payload(span: Span) -> dict[str, object]:
    """Forma pública de um Span para o overlay tipado e os testes."""
    return _span_json(span)


def _trivia(value: Trivia) -> dict[str, object]:
    return {
        "kind": value.kind.value,
        "text": value.text,
        "span": _span_json(value.span),
    }


def _span_json(span: Span) -> dict[str, object]:
    return {"start": _position_json(span.start), "end": _position_json(span.end)}


def _position_json(position: Position) -> dict[str, object]:
    return {
        "line": position.line,
        "column": position.column,
        "offset": position.offset,
    }


def _kind(name: str) -> str:
    return _TOKEN_CAMEL.sub("_", name).lower()


def _is_record(value: object) -> bool:
    return is_dataclass(value) and not isinstance(value, type)
