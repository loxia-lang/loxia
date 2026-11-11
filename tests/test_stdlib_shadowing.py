from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_src_nao_sombreia_modulos_da_stdlib() -> None:
    """Nenhum módulo de `src/` pode ter nome de módulo da stdlib.

    Se `src/` entrar no `sys.path` (ex.: `PYTHONPATH=src`), um `token.py` local
    sombreia o `token` da stdlib e quebra `dataclasses`/`inspect` com erro de
    import circular — por isso o módulo se chama `tokens.py`.
    """
    offenders = sorted(
        path.stem for path in SRC.glob("*.py") if path.stem in sys.stdlib_module_names
    )

    assert offenders == [], (
        "renomeie estes módulos de src/ para não sombrear a stdlib: "
        + ", ".join(offenders)
    )


def test_importar_stdlib_com_src_no_path_continua_funcionando() -> None:
    code = "import sys; sys.path.insert(0, 'src'); import dataclasses; print('ok')"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
