"""Header gerado da tabela de primitivas (ADR-0071, ADR-0094).

`runtime/kernel_gen.h` declara o símbolo C de cada primitiva com a assinatura que o
lowering espera. O `kernel.c` inclui o header, então tabela e definição C divergentes
quebram a compilação — este teste garante que o header versionado está atualizado.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loxia_core.execution.primitives import PRIMITIVES

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "runtime" / "gen_kernel.py"
HEADER = ROOT / "runtime" / "kernel_gen.h"


def test_header_gerado_esta_atualizado() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_header_declara_toda_a_tabela() -> None:
    text = HEADER.read_text(encoding="utf-8")

    missing = [
        primitive.c_symbol
        for primitive in PRIMITIVES
        if primitive.c_symbol not in text
    ]
    assert missing == [], f"fora do header: {missing}"


def test_header_respeita_site() -> None:
    """Primitivas com `site` recebem `(int32_t, int32_t)`; as demais, não."""
    text = HEADER.read_text(encoding="utf-8").splitlines()

    for primitive in PRIMITIVES:
        line = next(line for line in text if primitive.c_symbol in line)
        has_site = "int32_t, int32_t" in line
        assert has_site is primitive.site, primitive.lox
