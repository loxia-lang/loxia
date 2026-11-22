# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cobertura mecânica do `AGENTS.md` e dos escopados (mesma ideia de `test_docs_consistency`).

Bloqueia o que é verificável sem julgamento: a tabela de skills bate com `.dsh/skills/`,
o exemplo de `--version` bate com `loxia.__version__`, todo link relativo resolve e toda
referência `AGENTS.md §N` usada pelas skills aponta para uma seção existente. O que é
julgamento (o texto estar bom) continua sendo revisão de PR.
"""

from __future__ import annotations

import re
from pathlib import Path

from loxia import __version__

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
SCOPED = (
    ROOT / "loxia_core" / "AGENTS.md",
    ROOT / "runtime" / "AGENTS.md",
    ROOT / "std" / "AGENTS.md",
    ROOT / "tests" / "AGENTS.md",
)
SKILLS = ROOT / ".dsh" / "skills"
AGENT_FILES = (AGENTS, *SCOPED)

SKILL_ROW = re.compile(r"^\| `([a-z0-9-]+)` \|", re.MULTILINE)
VERSION = re.compile(r"--version\s+#\s*loxia\s+(\d+\.\d+\.\d+)")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SECTION = re.compile(r"^## (\d+)\.", re.MULTILINE)
SECTION_REF = re.compile(r"AGENTS\.md`?\s*§(\d+)")


def test_skill_table_matches_disk() -> None:
    listed = set(SKILL_ROW.findall(AGENTS.read_text(encoding="utf-8")))
    on_disk = {path.parent.name for path in SKILLS.glob("*/SKILL.md")}

    assert listed == on_disk, (
        f"AGENTS.md §10 desatualizado — só na tabela: {sorted(listed - on_disk)}; "
        f"só no disco: {sorted(on_disk - listed)}"
    )


def test_version_example_matches_package() -> None:
    match = VERSION.search(AGENTS.read_text(encoding="utf-8"))

    assert match is not None, "AGENTS.md §4 não tem mais o exemplo `--version`"
    assert match.group(1) == __version__, (
        f"AGENTS.md mostra loxia {match.group(1)}, pacote é {__version__}"
    )


def test_relative_links_resolve() -> None:
    broken: list[str] = []
    for path in AGENT_FILES:
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            if not (path.parent / relative).exists():
                broken.append(f"{path.relative_to(ROOT)} -> {relative}")

    assert not broken, "link relativo quebrado no contexto de agentes:\n" + "\n".join(broken)


def test_section_references_exist() -> None:
    headings = set(SECTION.findall(AGENTS.read_text(encoding="utf-8")))
    missing: list[str] = []
    for skill in SKILLS.glob("*/SKILL.md"):
        for section in SECTION_REF.findall(skill.read_text(encoding="utf-8")):
            if section not in headings:
                missing.append(f"{skill.parent.name} -> §{section}")

    assert not missing, "skill citando seção inexistente do AGENTS.md:\n" + "\n".join(missing)


def test_agents_is_versioned_and_notes_are_ignored() -> None:
    ignored = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}

    assert "AGENTS.md" not in ignored, "AGENTS.md voltou para o .gitignore"
    assert "NOTAS.local.md" in ignored, "NOTAS.local.md (caderno local) deveria ser ignorado"


def test_claude_points_to_agents() -> None:
    assert "AGENTS.md" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
