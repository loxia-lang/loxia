# SPDX-License-Identifier: MIT OR Apache-2.0
"""Loader de módulos e privacidade `_` (ADR-0073)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.diagnostics.source import SourceMap
from loxia_core.frontend.expr import Call, Variable
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Function, Return
from loxia_core.loader.loader import ModuleLoader

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


def _run(path: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *flags, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _project(tmp_path: Path) -> Path:
    (tmp_path / "dtos").mkdir()
    (tmp_path / "dtos" / "dtoA.lx").write_text(
        "class DtoA {\n"
        "  val nome: String\n"
        "  init(nome: String) { this.nome = nome }\n"
        "  fn publico() -> String { return this.nome }\n"
        '  fn _segredo() -> String { return "x" }\n'
        "}\n"
        "enum Status { Ativo, Inativo }\n"
        'fn helper() -> String { return "ok" }\n'
        'fn _oculto() -> String { return "x" }\n',
        encoding="utf-8",
    )
    return tmp_path


def test_from_importa_publicos(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lx"
    main.write_text(
        "from dtos.dtoA import DtoA, Status, helper\n"
        """print(DtoA("a").publico())
"""
        """print(Status.Ativo)
"""
        """print(helper())
""",
        encoding="utf-8",
    )

    result = _run(main)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "a\nStatus.Ativo\nok\n"


def test_namespace_e_alias(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lx"
    main.write_text(
        "import dtos.dtoA as d\n"
        """print(d.DtoA("b").publico())
"""
        """print(d.helper())
""",
        encoding="utf-8",
    )

    result = _run(main)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "b\nok\n"


def test_privado_e_rejeitado_em_from_e_namespace(tmp_path: Path) -> None:
    root = _project(tmp_path)
    from_main = root / "from.lx"
    from_main.write_text("from dtos.dtoA import _oculto\n", encoding="utf-8")
    ns_main = root / "ns.lx"
    ns_main.write_text(
        """import dtos.dtoA as d
print(d._oculto)
""",
        encoding="utf-8",
    )

    for main in (from_main, ns_main):
        result = _run(main)
        assert result.returncode == 65
        assert "private" in result.stderr


def test_pasta_nao_e_modulo(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lx"
    main.write_text("from dtos import dtoA\n", encoding="utf-8")

    result = _run(main)

    assert result.returncode == 65
    assert "Module 'dtos' not found." in result.stderr


def test_ciclo_e_erro(tmp_path: Path) -> None:
    (tmp_path / "a.lx").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.lx").write_text("import a\n", encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("import a\n", encoding="utf-8")

    result = _run(main)

    assert result.returncode == 65
    assert "cycle" in result.stderr.lower()


def test_modulo_so_declara(tmp_path: Path) -> None:
    (tmp_path / "m.lx").write_text(
        """print(1)
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text("import m\n", encoding="utf-8")

    result = _run(main)

    assert result.returncode == 65
    assert "only imports, functions, classes, interfaces, enums and type aliases" in result.stderr


def test_importa_type_alias(tmp_path: Path) -> None:
    (tmp_path / "types.lx").write_text(
        "type UserId = Int\ntype Nomes = List[String]\nfn eco(x: UserId) -> UserId { return x }\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text(
        "from types import UserId, Nomes, eco\n"
        "val id: UserId = 7\n"
        'val nomes: Nomes = ["a"]\n'
        """print(eco(id))
"""
        """print(nomes)
""",
        encoding="utf-8",
    )

    result = _run(main)

    assert result.returncode == 0, result.stderr
    assert result.stdout == '7\n["a"]\n'


def test_display_de_classe_de_modulo_preserva_nome(tmp_path: Path) -> None:
    root = _project(tmp_path)
    main = root / "main.lx"
    main.write_text(
        "from dtos.dtoA import DtoA\n"
        """print(DtoA("a"))
""",
        encoding="utf-8",
    )

    result = _run(main)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "DtoA instance\n"


def test_erro_de_checker_aponta_o_arquivo_do_modulo(tmp_path: Path) -> None:
    """ADR-0075: o span carrega a origem real, não o arquivo da entrada."""
    (tmp_path / "mod.lx").write_text('fn f() -> Int {\n  return "boom"\n}\n', encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("import mod\n\nprint(mod.f())\n", encoding="utf-8")

    result = _run(main, "--check")

    assert result.returncode == 65
    assert "mod.lx:2:3: error[E3001]: Expected Int, found String." in result.stderr
    assert "main.lx:2" not in result.stderr
    assert '2 |   return "boom"' in result.stderr
    assert "  |   ^" in result.stderr


def test_erro_de_checker_em_modulo_aninhado_nao_vira_basename(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.lx").write_text(
        'fn f() -> Int {\n  return "boom"\n}\n', encoding="utf-8"
    )
    main = tmp_path / "main.lx"
    main.write_text("import pkg.mod\n\nprint(pkg.mod.f())\n", encoding="utf-8")

    result = _run(main, "--check")

    assert result.returncode == 65
    assert "pkg/mod.lx:2:3: error[E3001]" in result.stderr, result.stderr


def test_erro_de_resolver_aponta_o_arquivo_do_modulo(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text(
        "fn f() -> Int {\n  val x = 1\n  x = 2\n  return x\n}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text("import mod\n\nprint(mod.f())\n", encoding="utf-8")

    result = _run(main, "--check")

    assert result.returncode == 65
    assert "mod.lx:3:3: error[E2002]" in result.stderr
    assert "3 |   x = 2" in result.stderr


def test_json_do_checker_traz_span_do_modulo(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text('fn f() -> Int {\n  return "boom"\n}\n', encoding="utf-8")
    main = tmp_path / "main.lx"
    main.write_text("import mod\n\nprint(mod.f())\n", encoding="utf-8")

    result = _run(main, "--check", "--error-format=json")
    payload = json.loads(result.stdout)
    span = payload["diagnostics"][0]["span"]

    assert span["file"] == "mod.lx"
    assert span["start"]["line"] == 2
    assert span["start"]["column"] == 3
    assert span["start"]["offset"] > 0


def test_rewriter_preserva_posicao_do_token(tmp_path: Path) -> None:
    """O rewriter renomeia `f` para `a$f`; posição e arquivo não podem se perder."""
    (tmp_path / "a.lx").write_text("fn f() -> Int { return 1 }\n", encoding="utf-8")
    line = "fn h() -> Int { return g(f) }"
    (tmp_path / "b.lx").write_text(
        f"from a import f\nfn g(x: Int) -> Int {{ return x }}\n{line}\n",
        encoding="utf-8",
    )

    reporter = ErrorReporter()
    reporter.file = "main.lx"
    source = "import b\n"
    statements = Parser(Scanner(source, reporter).scan_tokens(), reporter=reporter).parse()
    assert statements is not None
    loaded = ModuleLoader(reporter, SourceMap(), tmp_path).load(statements, "main.lx")
    assert loaded is not None

    function = next(
        stmt for stmt in loaded if isinstance(stmt, Function) and stmt.display_name == "h"
    )
    return_stmt = next(stmt for stmt in function.body if isinstance(stmt, Return))
    call = return_stmt.value
    assert isinstance(call, Call)
    argument = call.arguments[0]
    assert isinstance(argument, Variable)

    assert argument.name.lexeme.endswith("$f")
    assert argument.name.file == "b.lx"
    assert argument.name.column == line.index("f)") + 1
    assert argument.name.offset > 0


def test_erro_de_runtime_aponta_o_modulo_e_o_frame(tmp_path: Path) -> None:
    """ADR-0089: o runtime também usa o arquivo do módulo e mostra o call site."""
    (tmp_path / "mod.lx").write_text(
        "fn f(x: Int) -> Int {\n  return x // 0\n}\n", encoding="utf-8"
    )
    main = tmp_path / "main.lx"
    main.write_text("import mod\n\nprint(mod.f(1))\n", encoding="utf-8")

    result = _run(main)

    assert result.returncode == 70
    assert "mod.lx:2:12: error[R1002]: Division by zero not allowed" in result.stderr
    assert "  at f (main.lx:3:14)\n" in result.stderr


def test_interface_importada_is_as_nos_dois_motores(tmp_path: Path) -> None:
    (tmp_path / "lib_iface.lx").write_text(
        "interface Named {\n"
        "  fn name() -> String\n"
        "}\n"
        "class C implements Named {\n"
        '  fn name() -> String { return "c" }\n'
        "}\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.lx"
    main.write_text(
        "from lib_iface import Named, C\n"
        "val a: Any = C()\n"
        "print(a is Named)\n"
        "print((a as Named).name())\n",
        encoding="utf-8",
    )

    interpreted = _run(main)
    assert interpreted.returncode == 0, interpreted.stderr
    assert interpreted.stdout == "true\nc\n"

    binary = tmp_path / "app"
    built = _run(main, "--emit=exe", "-o", str(binary))
    assert built.returncode == 0, built.stderr
    native = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert native.returncode == 0, native.stderr
    assert native.stdout == interpreted.stdout


def test_interface_importada_diagnostico_usa_nome_local(tmp_path: Path) -> None:
    (tmp_path / "lib_iface.lx").write_text(
        "interface Named {\n"
        "  fn name() -> String\n"
        "}\n"
        "class C implements Named {\n"
        '  fn name() -> String { return "c" }\n'
        "}\n",
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime.lx"
    runtime.write_text(
        "from lib_iface import Named\nval a: Any = 1\nprint(a as Named)\n",
        encoding="utf-8",
    )
    interpreted = _run(runtime)
    assert interpreted.returncode == 70
    assert "Can't cast value to Named." in interpreted.stderr

    binary = tmp_path / "app"
    built = _run(runtime, "--emit=exe", "-o", str(binary))
    assert built.returncode == 0, built.stderr
    native = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    assert native.returncode == 70
    assert "Can't cast value to Named." in native.stderr

    runtime_class = tmp_path / "runtime_class.lx"
    runtime_class.write_text(
        "from lib_iface import C\nval a: Any = 1\nprint(a as C)\n",
        encoding="utf-8",
    )
    interpreted_class = _run(runtime_class)
    assert interpreted_class.returncode == 70
    assert "Can't cast value to C." in interpreted_class.stderr

    static = tmp_path / "static.lx"
    static.write_text(
        "from lib_iface import Named\nclass Other {}\nprint(Other() as Named)\n",
        encoding="utf-8",
    )
    checked = _run(static, "--check")
    assert checked.returncode == 65
    assert "Can't cast Other to Named." in checked.stderr
