# SPDX-License-Identifier: MIT OR Apache-2.0
"""Binding `ctypes` do motor de regex nativo (ADR-0131).

A biblioteca é construída sob demanda por `loxia_core.native_build` e expõe o ABI
de `native/regex/include/lox_regex.h`. Nada aqui conhece valores do Loxia: as
strings entram como UTF-8 e os offsets saem em code points.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Final

from loxia_core.diagnostics.errors import NativeError
from loxia_core.native_build import library as native_library

ABI_VERSION: Final = 2
MODE_LINEAR: Final = 0
MODE_FULL: Final = 1

NO_MATCH: Final = -100
ERR_LIMIT: Final = -4
ERR_HANDLE: Final = -5
ERR_CAPACITY: Final = -8
ERR_TOO_BIG: Final = -9
ERR_COMPILE: Final = -10
ERR_ENGINE: Final = -11

# Teto de grupos de captura que o binding aceita antes de desistir.
MAX_GROUPS: Final = 4096

_library: ctypes.CDLL | None = None


def _load() -> ctypes.CDLL:
    global _library
    if _library is None:
        loaded = ctypes.CDLL(str(native_library()))

        loaded.loxr_abi_version.restype = ctypes.c_uint32

        compile_fn = loaded.loxr_compile
        compile_fn.restype = ctypes.c_int32
        compile_fn.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_int64),
        ]

        match_fn = loaded.loxr_match
        match_fn.restype = ctypes.c_int32
        match_fn.argtypes = [
            ctypes.c_int64,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int64),
            ctypes.c_size_t,
        ]

        names_fn = loaded.loxr_group_names
        names_fn.restype = ctypes.c_int32
        names_fn.argtypes = [
            ctypes.c_int64,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]

        free_fn = loaded.loxr_free
        free_fn.restype = None
        free_fn.argtypes = [ctypes.c_int64]

        version = int(loaded.loxr_abi_version())
        if version != ABI_VERSION:
            raise NativeError(f"regex: native engine ABI {version} does not match {ABI_VERSION}.")
        _library = loaded
    return _library


def library_path() -> Path:
    """Caminho da `cdylib` (constrói sob demanda)."""
    return native_library()


def compile_pattern(pattern: str, flags: int, mode: int) -> tuple[int, int, int]:
    """Compila o padrão; devolve `(código, handle, offset)` como no ABI.

    `offset` é o deslocamento em bytes do primeiro erro de sintaxe, ou `-1`
    quando não há erro de sintaxe (sucesso, limites, argumentos).
    """
    raw = pattern.encode("utf-8")
    handle = ctypes.c_int64(0)
    offset = ctypes.c_int64(-1)
    code = int(
        _load().loxr_compile(raw, len(raw), flags, mode, ctypes.byref(handle), ctypes.byref(offset))
    )
    return code, int(handle.value), int(offset.value)


def match_pattern(handle: int, subject: str, start: int) -> tuple[int, list[int]]:
    """Casa o padrão; devolve `(código, spans)` com spans em code points."""
    raw = subject.encode("utf-8")
    capacity = 64
    spans: ctypes.Array[ctypes.c_int64]
    while True:
        spans = (ctypes.c_int64 * capacity)()
        code = int(_load().loxr_match(handle, raw, len(raw), start, spans, capacity))
        if code != ERR_CAPACITY:
            break
        capacity *= 2
        if capacity > MAX_GROUPS * 2:
            raise NativeError("regex: pattern has too many capture groups.")
    if code < 0:
        return code, []
    return code, [int(spans[index]) for index in range(code)]


def error_message(code: int) -> str:
    """Mensagem estável de um código negativo do ABI (idêntica ao adaptador C)."""
    if code == ERR_LIMIT:
        return "regex match limit exceeded."
    if code == ERR_HANDLE:
        return "regex handle is closed or unknown."
    return "regex engine internal error."


def group_names(handle: int) -> list[str]:
    """Nomes dos grupos de captura (índice 0 vazio); `[]` quando não há grupos."""
    engine = _load()
    needed = int(engine.loxr_group_names(handle, None, 0))
    if needed < 0:
        raise NativeError(error_message(needed))
    if needed == 0:
        return []
    buffer = (ctypes.c_uint8 * needed)()
    written = int(engine.loxr_group_names(handle, buffer, needed))
    if written != needed:
        raise NativeError("regex engine internal error.")
    return [part.decode("utf-8") for part in bytes(buffer)[:-1].split(b"\0")]


def free_pattern(handle: int) -> None:
    """Libera um handle; idempotente, como no ABI."""
    _load().loxr_free(handle)
