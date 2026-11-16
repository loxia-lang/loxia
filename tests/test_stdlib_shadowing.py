from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "loxia_core"


def test_core_nao_sombreia_modulos_da_stdlib() -> None:
    """Nenhum módulo/pacote de topo de `loxia_core/` pode ter nome da stdlib.

    Se `loxia_core/` entrar no `sys.path` (ex.: `PYTHONPATH=loxia_core`), um `token.py` local
    sombreia o `token` da stdlib e quebra `dataclasses`/`inspect` com erro de
    import circular — por isso o módulo se chama `tokens.py`. Só o topo importa:
    módulos dentro de pacotes (`loxia_core/frontend/tokens.py`) não são alcançáveis por
    `import tokens`.
    """
    offenders = sorted(
        path.stem if path.is_file() else path.name
        for path in CORE.iterdir()
        if path.name != "__pycache__" and path.name in sys.stdlib_module_names
    )

    assert offenders == [], (
        "renomeie estes módulos de loxia_core/ para não sombrear a stdlib: "
        + ", ".join(offenders)
    )


def test_importar_stdlib_com_core_no_path_continua_funcionando() -> None:
    code = "import sys; sys.path.insert(0, 'loxia_core'); import dataclasses; print('ok')"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
