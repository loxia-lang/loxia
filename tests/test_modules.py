"""Loader de módulos e privacidade `_` (ADR-0073)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _project(tmp_path: Path) -> Path:
    (tmp_path / "dtos").mkdir()
    (tmp_path / "dtos" / "dtoA.lox").write_text(
        "class DtoA {\n"
        "  val nome: String\n"
        "  init(nome: String) { this.nome = nome }\n"
        "  fn publico() -> String { return this.nome }\n"
        "  fn _segredo() -> String { return \"x\" }\n"
        "}\n"
        "enum Status { Ativo, Inativo }\n"
        "fn helper() -> String { return \"ok\" }\n"
        "fn _oculto() -> String { return \"x\" }\n",
        encoding="utf-8",
    )
    return tmp_path


def test_from_importa_publicos(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lox"
    main.write_text(
        "from dtos.dtoA import DtoA, Status, helper\n"
        'print DtoA("a").publico()\n'
        "print Status.Ativo\n"
        "print helper()\n",
        encoding="utf-8",
    )

    result = _run(main)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "a\nStatus.Ativo\nok\n"


def test_namespace_e_alias(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lox"
    main.write_text(
        "import dtos.dtoA as d\n"
        'print d.DtoA("b").publico()\n'
        "print d.helper()\n",
        encoding="utf-8",
    )

    result = _run(main)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "b\nok\n"


def test_privado_e_rejeitado_em_from_e_namespace(tmp_path: Path) -> None:
    root = _project(tmp_path)
    from_main = root / "from.lox"
    from_main.write_text("from dtos.dtoA import _oculto\n", encoding="utf-8")
    ns_main = root / "ns.lox"
    ns_main.write_text("import dtos.dtoA as d\nprint d._oculto\n", encoding="utf-8")

    for main in (from_main, ns_main):
        result = _run(main)
        assert result.returncode == 65
        assert "private" in result.stderr


def test_pasta_nao_e_modulo(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lox"
    main.write_text("from dtos import dtoA\n", encoding="utf-8")

    result = _run(main)

    assert result.returncode == 65
    assert "Module 'dtos' not found." in result.stderr


def test_ciclo_e_erro(tmp_path: Path) -> None:
    (tmp_path / "a.lox").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.lox").write_text("import a\n", encoding="utf-8")
    main = tmp_path / "main.lox"
    main.write_text("import a\n", encoding="utf-8")

    result = _run(main)

    assert result.returncode == 65
    assert "cycle" in result.stderr.lower()


def test_modulo_so_declara(tmp_path: Path) -> None:
    (tmp_path / "m.lox").write_text("print 1\n", encoding="utf-8")
    main = tmp_path / "main.lox"
    main.write_text("import m\n", encoding="utf-8")

    result = _run(main)

    assert result.returncode == 65
    assert "only imports, functions, classes and enums" in result.stderr


def test_display_de_classe_de_modulo_preserva_nome(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lox"
    main.write_text(
        "from dtos.dtoA import DtoA\n"
        'print DtoA("a")\n',
        encoding="utf-8",
    )

    result = _run(main)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "DtoA instance\n"
