# SPDX-License-Identifier: MIT OR Apache-2.0
"""Gera o catálogo de códigos de diagnóstico em `docs/spec/erros.md`.

A tabela entre `<!-- codes:start -->` e `<!-- codes:end -->` é **gerada** a partir de
`loxia_core/diagnostics/codes.py` (`Code`, `CODE_PHASE` e `CODE_DESCRIPTIONS`); não edite à mão.
Assim o catálogo não descola do enum: um código novo sem descrição quebra o `--check`.

Uso:

    uv run python docs/_hooks/codes.py           # imprime o bloco
    uv run python docs/_hooks/codes.py --write   # reescreve o bloco em erros.md
    uv run python docs/_hooks/codes.py --check   # exit 1 se o bloco estiver defasado

`tests/test_docs_consistency.py` chama o `--check` em CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loxia_core.diagnostics.codes import (  # noqa: E402
    CODE_DESCRIPTIONS,
    CODE_PHASE,
    Code,
)
from loxia_core.diagnostics.diagnostic import Phase  # noqa: E402

PAGE = ROOT / "docs" / "spec" / "erros.md"
START = "<!-- codes:start -->"
END = "<!-- codes:end -->"

PHASES: tuple[Phase, ...] = (
    Phase.LEXER,
    Phase.PARSER,
    Phase.RESOLVER,
    Phase.CHECKER,
    Phase.BACKEND,
    Phase.RUNTIME,
    Phase.CLI,
)

HEADINGS = {
    Phase.LEXER: "### Lexicon",
    Phase.PARSER: "### Syntax",
    Phase.RESOLVER: "### Resolver",
    Phase.CHECKER: "### Checker",
    Phase.BACKEND: "### Backend",
    Phase.RUNTIME: "### Runtime",
    Phase.CLI: "### CLI",
}


def render() -> str:
    """Bloco markdown determinístico (ordem derivada de `Code`)."""
    lines = [START]
    for phase in PHASES:
        lines.append(HEADINGS[phase])
        lines.append("")
        lines.append("| Code | Family |")
        lines.append("| --- | --- |")
        codes = sorted(
            (code for code in Code if CODE_PHASE[code] == phase),
            key=lambda code: code.value,
        )
        for code in codes:
            description = CODE_DESCRIPTIONS.get(code)
            if description is None:
                raise SystemExit(
                    f"{code.value}: sem descrição em CODE_DESCRIPTIONS "
                    "(loxia_core/diagnostics/codes.py)"
                )
            escaped = description.replace("|", "\\|")
            lines.append(f"| `{code.value}` | {escaped} |")
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def extract(text: str) -> str | None:
    """Bloco atual da página, ou `None` quando os marcadores não existem."""
    start = text.find(START)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + len(END)]


def main(argv: list[str]) -> int:
    block = render()

    if "--write" in argv:
        text = PAGE.read_text(encoding="utf-8")
        current = extract(text)
        if current is None:
            print(f"{PAGE.relative_to(ROOT)}: marcadores {START}/{END} ausentes")
            return 1
        PAGE.write_text(text.replace(current, block), encoding="utf-8")
        print(f"{PAGE.relative_to(ROOT)}: bloco atualizado")
        return 0

    if "--check" in argv:
        current = extract(PAGE.read_text(encoding="utf-8"))
        if current == block:
            return 0
        print(
            f"{PAGE.relative_to(ROOT)} está defasado em relação a "
            "loxia_core/diagnostics/codes.py. Rode: make codes"
        )
        print("--- esperado ---")
        print(block)
        print("--- encontrado ---")
        print(current if current is not None else "(marcadores ausentes)")
        return 1

    print(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
