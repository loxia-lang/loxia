# SPDX-License-Identifier: MIT OR Apache-2.0
"""Assinaturas de `Bytes` e de seus métodos (ADR-0125).

Fonte única para o checker (tipos) e para o dispatcher do interpretador (aritmética de
métodos). O backend, no 79b, lê os mesmos nomes/aridades em `lower_bytes.py`.
"""

from __future__ import annotations

from loxia_core.frontend.ty import BYTES, INT, STRING, EnumTy, FnTy, ListTy, Ty

BYTES_ERROR = EnumTy("BytesError")


def _result(ok: Ty) -> EnumTy:
    return EnumTy("Result", (ok, BYTES_ERROR))


# Namespace estático: `Bytes.empty()` etc.
BYTES_STATICS: dict[str, FnTy] = {
    "empty": FnTy((), BYTES, 0),
    "fromList": FnTy((ListTy(INT),), BYTES, 1),
    "fromText": FnTy((STRING,), BYTES, 1),
    "fromHex": FnTy((STRING,), _result(BYTES), 1),
    "fromBase64": FnTy((STRING,), _result(BYTES), 1),
}

# Métodos do valor: `b.slice(...)` etc.
BYTES_METHODS: dict[str, FnTy] = {
    "slice": FnTy((INT, INT), BYTES, 2),
    "concat": FnTy((BYTES,), BYTES, 1),
    "toList": FnTy((), ListTy(INT), 0),
    "toText": FnTy((), _result(STRING), 0),
    "toHex": FnTy((), STRING, 0),
    "toBase64": FnTy((), STRING, 0),
}
