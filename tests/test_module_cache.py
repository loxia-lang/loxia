# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cache de parse de módulos (ADR-0143): reuso por conteúdo e invalidação."""

from __future__ import annotations

from pathlib import Path

from loxia.engine import Loxia
from loxia_core.loader.module_cache import ModuleCache


def _check(root: Path, source: str, cache: ModuleCache | None = None) -> Loxia:
    lox = Loxia(error_format="json", color="never", max_errors=0)
    lox.use_file(str(root / "main.lx"), module_root=root)
    lox.check(source, emit=False, module_overrides={}, module_cache=cache)
    return lox


def _codes(lox: Loxia) -> list[str]:
    return [diagnostic.code.value for diagnostic in lox.reporter.batch().diagnostics]


def test_cache_reuses_unchanged_source(tmp_path: Path) -> None:
    (tmp_path / "lib.lx").write_text("fn f() -> Int { return 1 }\n", encoding="utf-8")
    source = "from lib import f\nval x: Int = f()\n"
    cache = ModuleCache()

    first = _check(tmp_path, source, cache)
    second = _check(tmp_path, source, cache)

    assert len(cache) == 1
    assert repr(second.last_statements) == repr(first.last_statements)
    assert _codes(second) == _codes(first) == []


def test_cache_invalidates_on_content_change(tmp_path: Path) -> None:
    module = tmp_path / "lib.lx"
    module.write_text("fn f() -> Int { return 1 }\n", encoding="utf-8")
    source = "from lib import f\nval x: Int = f()\n"
    cache = ModuleCache()
    assert _check(tmp_path, source, cache).reporter.had_error is False

    module.write_text('fn f() -> String { return "x" }\n', encoding="utf-8")
    changed = _check(tmp_path, source, cache)

    assert len(cache) == 2
    assert "E3001" in _codes(changed)


def test_cache_does_not_store_parse_errors(tmp_path: Path) -> None:
    (tmp_path / "bad.lx").write_text("fn f( {}\n", encoding="utf-8")
    cache = ModuleCache()

    lox = _check(tmp_path, "import bad\n", cache)

    assert lox.reporter.had_error is True
    assert len(cache) == 0


def test_cache_evicts_by_entries(tmp_path: Path) -> None:
    (tmp_path / "a.lx").write_text("fn a() -> Int { return 1 }\n", encoding="utf-8")
    (tmp_path / "b.lx").write_text("fn b() -> Int { return 2 }\n", encoding="utf-8")
    cache = ModuleCache(max_entries=1)

    _check(tmp_path, "import a\n", cache)
    _check(tmp_path, "import b\n", cache)

    assert len(cache) == 1


def test_cached_module_does_not_change_the_parsed_program(tmp_path: Path) -> None:
    (tmp_path / "lib.lx").write_text(
        "class P {\n"
        "  val n: Int\n"
        "  fn init(n: Int) { this.n = n }\n"
        "}\n"
        "fn f(p: P) -> Int { return p.n }\n",
        encoding="utf-8",
    )
    source = "from lib import P, f\nval p = P(2)\nprint(f(p))\n"

    without = _check(tmp_path, source, None)
    cache = ModuleCache()
    _check(tmp_path, source, cache)
    warm = _check(tmp_path, source, cache)

    assert repr(warm.last_statements) == repr(without.last_statements)
