"""Manifest `loxia.toml`: dependências path, raízes e descoberta (ADR-0088/0100)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def _run(script: Path, *flags: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *flags, str(script)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _manifest(app: Path, text: str) -> None:
    (app / "loxia.toml").write_text(text, encoding="utf-8")


def _app_and_dep(tmp_path: Path) -> tuple[Path, Path]:
    app = tmp_path / "app"
    dep = tmp_path / "acme"
    app.mkdir()
    dep.mkdir()
    _manifest(
        app,
        '[package]\nname = "app"\n\n[dependencies]\nacme = { path = "../acme" }\n',
    )
    return app, dep


def test_dependencia_path_resolve_import_por_nome(tmp_path: Path) -> None:
    app, dep = _app_and_dep(tmp_path)
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n * 2 }\n", encoding="utf-8")
    (dep / "util.lx").write_text(
        "import acme.base as base\n"
        "fn quadruplo(n: Int) -> Int {\n"
        "  return base.dobro(base.dobro(n)) }\n",
        encoding="utf-8",
    )
    (app / "main.lx").write_text("import acme.util\nprint(util.quadruplo(2))\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "8\n"


def test_from_import_de_dependencia(tmp_path: Path) -> None:
    app, dep = _app_and_dep(tmp_path)
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n * 2 }\n", encoding="utf-8")
    (app / "main.lx").write_text(
        "from acme.base import dobro\nprint(dobro(21))\n", encoding="utf-8"
    )

    result = _run(app / "main.lx")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "42\n"


def test_manifest_no_ancestral_e_raiz_do_projeto(tmp_path: Path) -> None:
    app, dep = _app_and_dep(tmp_path)
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n * 2 }\n", encoding="utf-8")
    (app / "src").mkdir()
    (app / "lib").mkdir()
    (app / "lib" / "saudacao.lx").write_text(
        'fn oi() -> String { return "oi" }\n', encoding="utf-8"
    )
    (app / "src" / "main.lx").write_text(
        "import acme.base as base\n"
        "import lib.saudacao\n"
        "print(base.dobro(2))\n"
        "print(saudacao.oi())\n",
        encoding="utf-8",
    )

    result = _run(app / "src" / "main.lx")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "4\noi\n"


def test_modules_paths_declarado(tmp_path: Path) -> None:
    app = tmp_path / "app"
    shared = tmp_path / "shared"
    app.mkdir()
    shared.mkdir()
    _manifest(app, '[modules]\npaths = ["../shared"]\n')
    (shared / "extra.lx").write_text('fn oi() -> String { return "extra" }\n', encoding="utf-8")
    (app / "main.lx").write_text("import extra\nprint(extra.oi())\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "extra\n"


def test_ambiguidade_entre_projeto_e_dependencia(tmp_path: Path) -> None:
    app, dep = _app_and_dep(tmp_path)
    (app / "acme").mkdir()
    (app / "acme" / "foo.lx").write_text("fn valor() -> Int { return 1 }\n", encoding="utf-8")
    (dep / "foo.lx").write_text("fn valor() -> Int { return 2 }\n", encoding="utf-8")
    (app / "main.lx").write_text("import acme.foo\nprint(foo.valor())\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 65
    assert "Module 'acme.foo' is ambiguous" in result.stderr
    assert "project (acme/foo.lx)" in result.stderr
    assert "dependency 'acme' (../acme/foo.lx)" in result.stderr


def test_dependencia_nao_ve_modulo_do_projeto(tmp_path: Path) -> None:
    app, dep = _app_and_dep(tmp_path)
    (app / "acme").mkdir()
    (app / "acme" / "segredo.lx").write_text("fn valor() -> Int { return 1 }\n", encoding="utf-8")
    (dep / "util.lx").write_text(
        "import acme.segredo\nfn usa() -> Int { return segredo.valor() }\n",
        encoding="utf-8",
    )
    (app / "main.lx").write_text("import acme.util\nprint(util.usa())\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 65
    assert "not found in dependency 'acme'" in result.stderr
    assert "acme/util.lx" in result.stderr


def test_module_path_flag(tmp_path: Path) -> None:
    app = tmp_path / "app"
    extra = tmp_path / "extra"
    app.mkdir()
    extra.mkdir()
    (extra / "ext.lx").write_text('fn oi() -> String { return "extra" }\n', encoding="utf-8")
    (app / "main.lx").write_text("import ext\nprint(ext.oi())\n", encoding="utf-8")

    result = _run(app / "main.lx", "--module-path", str(extra))

    assert result.returncode == 0, result.stderr
    assert result.stdout == "extra\n"


def test_import_com_ponto_ponto_continua_erro(tmp_path: Path) -> None:
    (tmp_path / "main.lx").write_text("import ..acme.foo\n", encoding="utf-8")

    result = _run(tmp_path / "main.lx")

    assert result.returncode == 65
    assert "error[E1001]" in result.stderr
    assert "Expect module name." in result.stderr


def test_manifest_invalido_aponta_o_arquivo(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    _manifest(app, "[dependencies\n")
    (app / "main.lx").write_text("print(1)\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 65
    assert "loxia.toml:1" in result.stderr
    assert "Invalid TOML" in result.stderr


def test_dependencia_com_path_inexistente(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    _manifest(app, '[dependencies]\nacme = { path = "../nope" }\n')
    (app / "main.lx").write_text("print(1)\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 65
    assert "dependencies.acme.path" in result.stderr
    assert "does not exist" in result.stderr


def test_std_nao_pode_ser_dependencia(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    _manifest(app, '[dependencies]\nstd = { path = "." }\n')
    (app / "main.lx").write_text("print(1)\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 65
    assert "Dependency name 'std' is reserved." in result.stderr


def test_std_do_projeto_nao_sombreia_o_bundle(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "std").mkdir()
    (app / "std" / "foo.lx").write_text("fn valor() -> Int { return 1 }\n", encoding="utf-8")
    (app / "main.lx").write_text("import std.foo\nprint(foo.valor())\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 65
    assert "Module 'std.foo' not found." in result.stderr


def test_so_o_nome_da_dependencia_nao_e_modulo(tmp_path: Path) -> None:
    app, _ = _app_and_dep(tmp_path)
    (app / "main.lx").write_text("import acme\n", encoding="utf-8")

    result = _run(app / "main.lx")

    assert result.returncode == 65
    assert "Expect a module name after 'acme'." in result.stderr
