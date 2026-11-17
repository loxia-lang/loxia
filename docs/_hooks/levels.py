"""Gera o bloco de status do corpus em `docs/spec/garantias.md`.

O bloco entre `<!-- levels:start -->` e `<!-- levels:end -->` é **gerado** a partir de
`tests/corpus_manifest.py`; não edite à mão. Isso impede o descompasso que já aconteceu
neste repositório: o manifesto promovia casos e a prosa continuava dizendo "L5 na fila".

Uso:

    uv run python docs/_hooks/levels.py           # imprime o bloco
    uv run python docs/_hooks/levels.py --write   # reescreve o bloco em garantias.md
    uv run python docs/_hooks/levels.py --check   # exit 1 se o bloco estiver defasado

`tests/test_docs_consistency.py` chama o `--check` em CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.corpus_manifest import LEVELS, NEGATIVE, PENDING  # noqa: E402

PAGE = ROOT / "docs" / "spec" / "garantias.md"
START = "<!-- levels:start -->"
END = "<!-- levels:end -->"


def _level_key(level: str) -> tuple[int, float]:
    """Ordem semântica: `l2`, `l2.5`, `l3`… e `t7` no fim."""
    if level.startswith("l"):
        return (0, float(level[1:]))
    return (1, float("".join(char for char in level if char.isdigit()) or 0))


def render() -> str:
    """Bloco markdown determinístico (ordem e conteúdo derivados do manifesto)."""
    lines = [
        START,
        "| Nível | Casos que compilam e concordam (I1) |",
        "| --- | --- |",
    ]
    for level in sorted(LEVELS, key=_level_key):
        lines.append(f"| `{level}` | {len(LEVELS[level])} |")

    total = sum(len(cases) for cases in LEVELS.values())
    pending = ", ".join(f"`{Path(case).stem}` ({level})" for case, level in sorted(PENDING.items()))
    lines.append("")
    lines.append(
        f"**{total} casos** em {len(LEVELS)} níveis compilam e concordam; "
        f"**{len(PENDING)} em `PENDING`** ({pending}); "
        f"**{len(NEGATIVE)} negativos** de propósito."
    )
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
            "tests/corpus_manifest.py. Rode: make docs-sync"
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
