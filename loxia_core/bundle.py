# SPDX-License-Identifier: MIT OR Apache-2.0
"""Localização dos recursos que viajam com o pacote: `std/` e `runtime/`.

Em desenvolvimento (`uv run main.py`, pytest) os dois ficam na raiz do repo, porque é
assim que o projeto é editado e testado. No wheel eles precisam estar **dentro** do
pacote instalado (senão `--emit` e `import std.*` quebram fora do clone). O `hatchling`
copia `std/` para `loxia_core/std` e `runtime/` para `loxia_core/runtime` no build
([ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md)); este módulo resolve os
dois casos na mesma ordem:

1. raiz do repo (dev) — é o que existe quando o projeto é rodado do clone;
2. bundle do pacote instalado (`importlib.resources`).

O fallback por `importlib.resources` assume wheel instalado como diretório (é o caso do
`pip`/`uv`); um importador zipado não é suportado.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_PACKAGE = "loxia_core"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def bundle_dir(name: str) -> Path:
    """Diretório `std`/`runtime`: no repo em dev, no pacote quando instalado."""
    local = _REPO_ROOT / name
    if local.is_dir():
        return local

    return Path(str(resources.files(_PACKAGE))) / name


def bundle_file(name: str, *parts: str) -> Path:
    """Arquivo dentro de um `bundle_dir`, com a mesma regra de resolução."""
    return bundle_dir(name).joinpath(*parts)
