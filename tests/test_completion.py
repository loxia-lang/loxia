"""Completion do LSP: escopo, imports, módulos, `this` e enums."""

from __future__ import annotations

from pathlib import Path

from loxia.cli import Loxia
from loxia.completion import complete
from loxia.symbols import SymbolIndex


def items(source: str, marker: str) -> list[dict[str, object]]:
    offset = source.rindex(marker) + len(marker)
    lox = Loxia()
    lox._file = "t.lx"
    lox._sources.add("t.lx", source)
    lox.check(source, emit=False)
    index = SymbolIndex(
        lox.last_statements or [],
        source=source,
        checker=lox.last_checker,
        resolver=lox.last_resolver,
    )
    return complete(source, Path("t.lx"), len(source[:offset].encode("utf-8")), index)


def labels(source: str, marker: str) -> list[str]:
    return [str(item["label"]) for item in items(source, marker)]


def test_completion_de_local_nao_vaza_de_outra_funcao() -> None:
    source = "fn f() -> Nil {\n  val total = 1\n  tot\n}\nfn g() -> Nil {\n  val outro = 2\n}\n"
    found = labels(source, "tot")
    assert "total" in found
    assert "outro" not in found
    assert all("$" not in name for name in found)


def test_completion_de_modulo_std() -> None:
    source = "import std.strings as strings\nval x = strings.\n"
    found = labels(source, "strings.")
    assert "upper" in found
    assert "trim" in found
    assert all("$" not in name for name in found)


def test_completion_de_this_e_enum() -> None:
    klass = (
        "class C {\n  val value: Int\n"
        "  init() { this.value = 1 }\n"
        "  fn m() -> Nil {\n    this.\n  }\n}\n"
    )
    this = labels(klass, "this.")
    assert {"value", "m"} <= set(this)

    enum = "enum Color {\n  Red,\n  Blue\n}\nval c = Color.\n"
    assert {"Red", "Blue"} <= set(labels(enum, "Color."))


def test_completion_de_keywords_com_documento_incompleto() -> None:
    found = labels("fn f( {\n  \n", "  ")
    assert {"fn", "if", "val", "return"} <= set(found)


def test_completion_de_enum_com_virgula_final() -> None:
    source = "enum Color {\n  Red,\n  Blue,\n}\nval c = Color.\n"
    assert {"Red", "Blue"} <= set(labels(source, "Color."))


def test_completion_de_caminho_de_import() -> None:
    found = labels("import std.\n", "std.")
    assert "json" in found
    assert "strings" in found
    assert "std.json" not in found


def test_completion_de_metodos_de_lista_e_builtin() -> None:
    source = "val xs = [1, 2]\nxs.\n"
    found = labels(source, "xs.")
    assert {"push", "pop"} <= set(found)

    assert "parse" in labels("val n = Int.\n", "Int.")


def test_completion_filtra_pelo_prefixo() -> None:
    source = "import std.strings as strings\nstrings.up\n"
    found = labels(source, "strings.up")
    assert "upper" in found
    assert "trim" not in found


def test_completion_de_from_import() -> None:
    found = labels("from std.strings import \n", "import ")
    assert "upper" in found
    assert "trim" in found

    values = items("from std.strings import upper\nupper\n", "upper")
    upper = next(item for item in values if item["label"] == "upper")
    assert "fn upper" in str(upper["detail"])


def test_completion_global_nao_tem_nome_mangled() -> None:
    source = "import std.strings as strings\nfn f() -> Int {\n  return 1\n}\n"
    found = labels(source, "return ")
    assert "f" in found
    assert "strings" in found
    assert "if" in found
    assert all("$" not in name for name in found)
