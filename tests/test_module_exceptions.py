"""Regressão de `except` com classe de exceção definida em módulo (TODO §9.1 `R4`).

O interpretador casa a classe; o binário cai no `except Exception` porque o loader
reescreve o nome do `except` para `modulo$Classe` e o descritor guarda o nome simples.
`xfail` estrito: quando a correção entrar, este teste vira XPASS e pede remoção.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.backend
@pytest.mark.xfail(
    strict=True,
    reason="R4: loader mangles except name; descriptor keeps the simple name",
)
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
