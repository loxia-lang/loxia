"""Notes de proveniência nos erros de tipo (ADR-0090/ADR-0099)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loxia.cli import Loxia
from loxia_core.diagnostics.diagnostic import Diagnostic

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def _diagnostics(source: str) -> list[Diagnostic]:
    lox = Loxia(error_format="json", color="never", max_errors=0)
    lox.check(source, emit=False)
    return list(lox.reporter.batch().diagnostics)


def test_nota_de_proveniencia_em_var_anotada() -> None:
    diagnostics = _diagnostics(
        "class Pessoa {\n"
        "  val nome: String\n"
        "  init(nome: String) { this.nome = nome }\n"
        "}\n"
        'val pessoa = Pessoa("Ana")\n'
        "val total: Int = pessoa.nome\n"
    )

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.message == "Expected Int, found String."
    assert diagnostic.notes == (
        "the value comes from `pessoa.nome` (line 6)",
    )


def test_nota_de_proveniencia_em_argumento() -> None:
    diagnostics = _diagnostics(
        "fn f(x: Int) -> Nil { return nil }\n"
        'val nome = "Ana"\n'
        "f(nome)\n"
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].notes == (
        "the value comes from `nome` (line 3)",
    )


def test_nota_de_proveniencia_em_atribuicao() -> None:
    diagnostics = _diagnostics(
        "var total: Int = 0\n"
        'val nome = "Ana"\n'
        "total = nome\n"
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].notes == (
        "the value comes from `nome` (line 3)",
    )


def test_literal_nao_ganha_nota_de_proveniencia() -> None:
    diagnostics = _diagnostics('val total: Int = "Ana"\n')

    assert len(diagnostics) == 1
    assert diagnostics[0].notes == ()


def test_nota_de_proveniencia_em_modulo(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text(
        "class Pessoa {\n"
        "  val nome: String\n"
        "  init(nome: String) { this.nome = nome }\n"
        "}\n"
        "fn total(p: Pessoa) -> Int {\n"
        "  val n: Int = p.nome\n"
        "  return n\n"
        "}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text(
        "import mod\n"
        'val p = mod.Pessoa("Ana")\n'
        "print(mod.total(p))\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--check", str(main)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 65
    assert "mod.lx:6:7: error[E3001]: Expected Int, found String." in result.stderr
    assert "note: the value comes from `p.nome` (line 6)" in result.stderr
