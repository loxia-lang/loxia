"""Relatório de frescor da documentação (inspirado no fluxo do Scrinalia).

Uma página que descreve código declara, no front matter, **quais arquivos ela documenta**:

    ---
    sources:
      - loxia_core/backend/**
      - runtime/runtime.c
    ---

O frescor é **derivado do git**, não de um campo `reviewed:` que envelhece sozinho:

- a página é candidata a desatualizada quando alguma fonte mudou **depois** do último
  commit que tocou a página;
- isso é um **relatório**, não um gate: a decisão ("atualizei" ou "continua verdadeiro")
  é humana e fica registrada em `docs/log.md`. O que bloqueia em CI é a cobertura
  mecânica (`tests/test_docs_consistency.py`), não este script.

Uso:

    uv run python docs/_hooks/freshness.py           # só páginas com fontes que mudaram
    uv run python docs/_hooks/freshness.py --all     # todas as páginas com fontes
    uv run python docs/_hooks/freshness.py --strict  # exit 1 se houver candidata
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
# ADRs são imutáveis por regra; o índice (`adr/README.md`) não declara fontes.
IMMUTABLE = ROOT / "docs" / "adr"
LEDGER = "docs/log.md"


@dataclass(frozen=True)
class Page:
    path: Path
    sources: tuple[str, ...]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _front_matter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return text[4:end] if end != -1 else None


def _sources(text: str) -> tuple[str, ...]:
    block = _front_matter(text)
    if block is None:
        return ()

    sources: list[str] = []
    inside = False
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("sources:"):
            inside = True
            continue
        if inside:
            if stripped.startswith("- "):
                sources.append(stripped[2:].strip().strip("'\""))
            elif stripped and not line.startswith((" ", "\t")):
                break
    return tuple(sources)


def pages() -> list[Page]:
    found: list[Page] = []
    for path in sorted(DOCS.rglob("*.md")):
        if path == IMMUTABLE or IMMUTABLE in path.parents:
            continue
        if path == DOCS / "log.md":
            continue
        sources = _sources(path.read_text(encoding="utf-8"))
        if sources:
            found.append(Page(path, sources))
    return found


def expand(page: Page) -> tuple[list[str], list[str]]:
    """(arquivos existentes, padrões que não casam com nada)."""
    files: list[str] = []
    broken: list[str] = []
    for pattern in page.sources:
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            broken.append(pattern)
        for match in matches:
            if match.is_file():
                files.append(match.relative_to(ROOT).as_posix())
    return files, broken


def _last_commit(files: list[str]) -> int:
    if not files:
        return 0
    stamp = _git("log", "-1", "--format=%ct", "--", *files)
    return int(stamp) if stamp.isdigit() else 0


def _commits_since(files: list[str], timestamp: int) -> list[str]:
    if not files or timestamp == 0:
        return _git("log", "--format=%h %s", "--", *files).splitlines()
    return _git(
        "log", "--format=%h %s", f"{timestamp + 1}..HEAD", "--", *files
    ).splitlines()


def _dirty(files: list[str]) -> list[str]:
    if not files:
        return []
    status = _git("status", "--porcelain", "--", *files)
    return [line for line in status.splitlines() if line.strip()]


def _date(timestamp: int) -> str:
    if timestamp == 0:
        return "sem commit"
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%d")


def report(page: Page, *, show_all: bool) -> tuple[bool, str]:
    """(precisa_triagem, linha_de_relatório)."""
    name = page.path.relative_to(ROOT).as_posix()
    files, broken = expand(page)

    if broken:
        return True, f"{name:<34} sources inválidas: {', '.join(broken)}"

    if not files:
        return True, f"{name:<34} sem arquivos em sources:"

    page_rel = page.path.relative_to(ROOT).as_posix()
    if _dirty([page_rel]):
        return False, f"{name:<34} pendente (página editada; o commit fecha)"

    page_stamp = _last_commit([page_rel])
    if page_stamp == 0:
        return False, f"{name:<34} novo (não versionado ainda)"

    source_stamp = _last_commit(files)
    dirty = _dirty(files)

    if source_stamp > page_stamp or dirty:
        commits = _commits_since(files, page_stamp)
        if dirty and not commits:
            detail = f"{len(dirty)} arquivo(s) não commitado(s)"
        else:
            detail = f"{len(commits)} commit(s) depois da página"
            if dirty:
                detail += f", {len(dirty)} arquivo(s) não commitado(s)"
        return True, f"{name:<34} stale — {detail}"

    if show_all:
        return False, f"{name:<34} ok — fontes de {_date(source_stamp)}"
    return False, ""


def main(argv: list[str]) -> int:
    show_all = "--all" in argv
    quiet = "--quiet" in argv
    strict = "--strict" in argv

    stale: list[str] = []
    for page in pages():
        needs, line = report(page, show_all=show_all)
        if needs:
            stale.append(page.path.relative_to(ROOT).as_posix())
        if line and not quiet:
            print(line)

    if not quiet:
        print()
        if stale:
            print(
                f"{len(stale)} página(s) para triar. Decida por página e registre em "
                f"{LEDGER} (veredicto `updated` ou `no-change` + motivo)."
            )
        else:
            print("Nenhuma página candidata a desatualizada.")

    if quiet and stale:
        print(
            f"docs: {len(stale)} página(s) candidata(s) a desatualizada(s); "
            f"rode `make docs-fresh`"
        )

    return 1 if strict and stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
