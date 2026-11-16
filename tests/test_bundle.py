"""Resolução de recursos empacotados (`std/` e `runtime/`), dev vs wheel (ADR-0088)."""

from __future__ import annotations

from pathlib import Path

import pytest

from loxia_core import bundle


def test_std_e_runtime_resolvem_no_repo() -> None:
    assert (bundle.bundle_dir("std") / "json.lx").is_file()
    assert bundle.bundle_file("runtime", "runtime.c").is_file()


def test_bundle_cai_para_o_pacote_quando_o_repo_nao_tem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sem `std/` na raiz (layout instalado), resolve dentro de `loxia_core`."""
    monkeypatch.setattr(bundle, "_REPO_ROOT", tmp_path)

    resolved = bundle.bundle_dir("std")

    assert resolved.name == "std"
    assert resolved.parent.name == "loxia_core"
