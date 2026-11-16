"""Gera `docs/stdlib/` a partir de `std/*.lx` e do registry de builtins (ADR-0091)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loxia import docgen  # noqa: E402
from loxia.builtins_docs import BUILTIN_DOCS  # noqa: E402
from loxia_core.bundle import bundle_dir  # noqa: E402
from loxia_core.diagnostics.error_reporter import ErrorReporter  # noqa: E402
from loxia_core.frontend.parser import Parser  # noqa: E402
from loxia_core.frontend.scanner import Scanner  # noqa: E402
from loxia_core.frontend.stmt import Stmt  # noqa: E402

OUT = ROOT / "docs" / "stdlib"
STD = bundle_dir("std")

MODULES = {
    "asserts": "Assertions that raise `RuntimeError` on failure.",
    "cli": "Deterministic command-line parsing.",
    "convert": "Text conversions (integer/float/bool, Base64, hex).",
    "csv": "RFC 4180 CSV parsing and serialization.",
    "fmt": "Formatting helpers (templates, padding, numbers, byte sizes).",
    "fs": "File reading/writing (ambient: outside I1).",
    "io": "Standard input/output (ambient where it blocks).",
    "log": "Leveled logging to stderr, without timestamps.",
    "collections": "Stack, Queue, Deque and PriorityQueue.",
    "hash": "Non-cryptographic hashes (FNV-1a, djb2) over UTF-8 bytes.",
    "rand": "Deterministic PRNG with an explicit seed.",
    "timex": "UTC date/time helpers (no timezone).",
    "iter": "Iteration helpers (`enumerate`, `zip`, `sum`, `contains`, `Step`).",
    "json": "RFC 8259 JSON with insertion-ordered objects.",
    "lists": "Generic list combinators.",
    "maps": "Helpers for `Map[String, V]`.",
    "numeric": "Integer number theory and statistics.",
    "paths": "Lexical POSIX path helpers.",
    "proc": "Processes, streams and `poll` (POSIX, ambient).",
    "property": "Property-based testing with generators, shrinking and seeds.",
    "results": "Combinators for `Result[T, E]`.",
    "sets": "`Set[T]` backed by `Map[Any, Bool]`.",
    "utf8": "UTF-8 and UTF-16 widths (bytes, code units, columns).",
    "strings": "UTF-8 text operations over code points.",
    "test": "Mini-harness de testes (TAP, `Suite`, matchers, `Recorder`).",
}


def _parse(path: Path) -> list[Stmt]:
    reporter = ErrorReporter()
    statements = Parser(
        Scanner(path.read_text(encoding="utf-8"), reporter).scan_tokens(),
        reporter=reporter,
    ).parse()
    if reporter.had_error or statements is None:
        raise SystemExit(f"parse error in {path}")
    return statements


def _module_page(module: str) -> str:
    path = STD / f"{module}.lx"
    symbols = [
        symbol
        for symbol in docgen.extract(_parse(path))
        if symbol.visibility == "public"
        and (symbol.container is None or not symbol.container.startswith("_"))
    ]
    body = docgen.render_markdown(f"std/{module}.lx", symbols)
    title = f"# Loxia API — `std/{module}.lx`"
    replacement = f"# std.{module}\n\n{MODULES[module]}\n\n## API"
    if title in body:
        body = body.replace(title, replacement, 1)
    return (
        "---\n"
        f"title: std.{module}\n"
        "sources:\n"
        f"  - std/{module}.lx\n"
        "  - loxia/docgen.py\n"
        "---\n\n"
        f"{body}"
    )


def _builtins_page() -> str:
    lines = [
        "---",
        "title: Builtins e kernel",
        "sources:",
        "  - loxia/builtins_docs.py",
        "  - loxia_core/execution/primitives.py",
        "  - loxia_core/execution/prelude.py",
        "---",
        "",
        "# Builtins and kernel",
        "",
        "Global names and native namespaces documented from `loxia/builtins_docs.py`.",
        "They are available without an import; `std.*` modules are documented separately.",
        "",
        "## Global functions and namespaces",
        "",
    ]
    for item in BUILTIN_DOCS:
        if "." in item.name:
            continue
        lines.extend([f"### `{item.signature}`", "", item.doc, ""])
    lines.extend(["## Native module members", ""])
    for item in BUILTIN_DOCS:
        if "." not in item.name:
            continue
        lines.extend([f"### `{item.signature}`", "", item.doc, ""])
    return "\n".join(lines).rstrip() + "\n"


def _index_page() -> str:
    lines = [
        "---",
        "title: Standard library",
        "sources:",
        "  - std/*.lx",
        "  - loxia/builtins_docs.py",
        "---",
        "",
        "# Standard library",
        "",
        "Reference generated from `///` in `std/*.lx` and the builtins registry.",
        "",
        "## Modules",
        "",
        "| Module | Summary |",
        "| --- | --- |",
    ]
    for module in sorted(MODULES):
        lines.append(f"| [`std.{module}`]({module}.md) | {MODULES[module]} |")
    lines.extend(
        [
            "",
            "## Builtins",
            "",
            "See [builtins.md](builtins.md).",
            "",
        ]
    )
    return "\n".join(lines)


def render() -> dict[Path, str]:
    pages: dict[Path, str] = {
        OUT / "index.md": _index_page(),
        OUT / "builtins.md": _builtins_page(),
    }
    for module in sorted(MODULES):
        pages[OUT / f"{module}.md"] = _module_page(module)
    return pages


def main(argv: list[str]) -> int:
    pages = render()
    if "--write" in argv:
        OUT.mkdir(parents=True, exist_ok=True)
        for path, text in pages.items():
            path.write_text(text, encoding="utf-8")
        print(f"{OUT.relative_to(ROOT)}: {len(pages)} páginas atualizadas")
        return 0
    if "--check" in argv:
        stale = [
            path
            for path, text in pages.items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]
        if stale:
            for path in stale:
                print(f"desatualizado: {path.relative_to(ROOT)}")
            print("Rode: make stdlib-docs")
            return 1
        return 0
    for path in sorted(pages):
        print(f"--- {path.relative_to(ROOT)} ---")
        print(pages[path], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
