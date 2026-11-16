"""Regressão de `except` com classe de exceção definida em módulo (`R4`, corrigido).

O loader reescreve o nome do `except` para `modulo$Classe`, mas o descritor guarda o
nome de exibição simples; o matcher do backend passou a comparar o ponteiro do descritor.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.backend
def test_excecao_de_classe_de_modulo_casa(tmp_path: Path) -> None:
    (tmp_path / "lib.lx").write_text(
        "class MyError(Exception) {\n"
        "  init(msg: String) { this.message = msg }\n"
        "}\n"
        "fn catch_it() -> Nil {\n"
        "  try {\n"
        '    raise MyError("x")\n'
        "  } except MyError as e {\n"
        '    print("my: ${e.message}")\n'
        "  } except Exception as e {\n"
        '    print("generic: ${e.message}")\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text("import lib\nlib.catch_it()\n", encoding="utf-8")
    binary = tmp_path / "main.bin"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "loxia",
            "build",
            str(main),
            "-o",
            str(binary),
            "--emit=exe",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    result = subprocess.run(
        [str(binary)], capture_output=True, text=True, check=False
    )
    assert result.stdout == "my: x\n"
