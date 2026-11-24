# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cache do build nativo (ADR-0131): persistente e content-addressed.

O build do crate Rust custa dezenas de segundos. Se a suíte apontar cada sessão
para um diretório temporário novo, todo `make check`/`make test-fast` paga um
`cargo build` a frio — mesmo com as fontes e o toolchain inalterados.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia_core import native_build


def test_regex_build_cache_e_o_cache_persistente(regex_build_cache: str) -> None:
    """O fixture reusa o cache do produto, não inventa um cache por sessão."""
    assert Path(regex_build_cache) == native_build.cache_base()


def test_cache_base_respeita_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`LOX_BUILD_CACHE` continua sendo o override do diretório-base."""
    cache = tmp_path / "cache"
    monkeypatch.setenv(native_build.CACHE_ENV, str(cache))

    assert native_build.cache_base() == cache
