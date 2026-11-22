# SPDX-License-Identifier: MIT OR Apache-2.0
"""Motor de regex nativo: binding ctypes e protocolo das primitivas (ADR-0131)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution import regex_runtime
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.primitives import PRIMITIVE_BY_LOX
from loxia_core.native_build import cargo_binary

pytestmark = pytest.mark.skipif(
    cargo_binary() is None, reason="Rust toolchain (cargo) is not available"
)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Compila uma vez num cache isolado; os testes seguintes reusam."""
    previous = os.environ.get("LOX_BUILD_CACHE")
    os.environ["LOX_BUILD_CACHE"] = str(tmp_path_factory.mktemp("regex-cache"))
    try:
        yield regex_runtime.library_path()
    finally:
        if previous is None:
            os.environ.pop("LOX_BUILD_CACHE", None)
        else:
            os.environ["LOX_BUILD_CACHE"] = previous


def test_compile_and_match_count_code_points(built: Path) -> None:
    code, handle = regex_runtime.compile_pattern(r"\p{L}+", 0, regex_runtime.MODE_LINEAR)
    assert code == 0
    assert handle >= 1

    code, spans = regex_runtime.match_pattern(handle, "café ☕ 123", 0)
    assert (code, spans) == (2, [0, 4])
    regex_runtime.free_pattern(handle)


def test_full_mode_supports_backreferences(built: Path) -> None:
    code, handle = regex_runtime.compile_pattern(r"(\w+)\s+\1", 0, regex_runtime.MODE_FULL)
    assert code == 0

    code, spans = regex_runtime.match_pattern(handle, "hello hello world", 0)
    assert code == 4
    assert spans[0:2] == [0, 11]
    assert spans[2:4] == [0, 5]
    regex_runtime.free_pattern(handle)


def test_no_match_is_not_an_error(built: Path) -> None:
    code, handle = regex_runtime.compile_pattern("z+", 0, regex_runtime.MODE_LINEAR)
    assert code == 0

    code, spans = regex_runtime.match_pattern(handle, "abc", 0)
    assert code == regex_runtime.NO_MATCH
    assert spans == []
    regex_runtime.free_pattern(handle)


def test_syntax_error_returns_a_code(built: Path) -> None:
    code, handle = regex_runtime.compile_pattern("(", 0, regex_runtime.MODE_LINEAR)
    assert code != 0
    assert handle == 0


def test_primitive_protocol_returns_a_tagged_list(built: Path) -> None:
    compile_fn = PRIMITIVE_BY_LOX["regex_engine.compile"].py
    match_fn = PRIMITIVE_BY_LOX["regex_engine.find"].py
    free_fn = PRIMITIVE_BY_LOX["regex_engine.free"].py

    compiled = compile_fn(r"(\d+)", 0, 0)
    assert isinstance(compiled, LoxList)
    tag, handle = compiled.elements
    assert tag == 1

    matched = match_fn(handle, "abc 123", 0)
    assert isinstance(matched, LoxList)
    assert matched.elements == [4, 7, 4, 7]

    free_fn(handle)


def test_unknown_handle_raises(built: Path) -> None:
    match_fn = PRIMITIVE_BY_LOX["regex_engine.find"].py
    with pytest.raises(NativeError, match="handle is closed or unknown"):
        match_fn(999_999, "abc", 0)


def test_build_is_cached(built: Path) -> None:
    assert built.is_file()
    assert regex_runtime.library_path() == built
