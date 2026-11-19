# SPDX-License-Identifier: MIT OR Apache-2.0
"""Shared documentation metadata for the Starlight site and the agent index.

`tools/docs_site.py` and `tools/docs_index.py` must agree on page slugs and URLs:
the site publishes `docs/spec/sintaxe.md` as `/reference/syntax/`, and the index has to
point at exactly that URL. The anchor algorithm is the same one Starlight uses
(`github-slugger`): lower-case, punctuation removed, spaces to hyphens, duplicates
suffixed `-1`, `-2`, ... This module is the single place for those rules.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SPEC = DOCS / "spec"
STDLIB = DOCS / "stdlib"
VERSIONS = DOCS / "versions"

SITE_BASE = "https://loxia-lang.github.io/loxia"
REPOSITORY = "https://github.com/loxia-lang/loxia"

# (source file, site slug, sidebar order)
SPEC_PAGES: tuple[tuple[str, str, int], ...] = (
    ("lexico.md", "lexicon", 1),
    ("sintaxe.md", "syntax", 2),
    ("semantica.md", "semantics", 3),
    ("erros.md", "errors", 4),
    ("garantias.md", "guarantees", 5),
)
SPEC_SLUGS = {source.removesuffix(".md"): slug for source, slug, _ in SPEC_PAGES}
STDLIB_TITLES: dict[str, str] = {"builtins": "Builtins and kernel"}

LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
_SLUG_STRIP = re.compile(r"[^\w\- ]", re.UNICODE)


@dataclass(frozen=True)
class Document:
    front_matter: str
    body: str


def split_front_matter(text: str) -> Document:
    if not text.startswith("---\n"):
        return Document("", text)
    end = text.find("\n---", 4)
    if end == -1:
        return Document("", text)
    return Document(text[4:end], text[end + 4 :].lstrip("\n"))


def front_matter_value(block: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in block.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip().strip("'\"")
    return None


def sources(block: str) -> tuple[str, ...]:
    found: list[str] = []
    inside = False
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("sources:"):
            inside = True
            continue
        if inside:
            if stripped.startswith("- "):
                found.append(stripped[2:].strip().strip("'\""))
            elif stripped and not line.startswith((" ", "\t")):
                break
    return tuple(found)


def title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def strip_h1(body: str) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[index + 1 :]).lstrip("\n")
    return body.lstrip("\n")


def slugify(heading: str) -> str:
    """Anchor exactly like `github-slugger` (the Starlight heading id)."""
    value = heading.strip().lower()
    value = _SLUG_STRIP.sub("", value)
    return value.replace(" ", "-")


def spec_url(source: str) -> str:
    stem = posixpath.basename(source).removesuffix(".md")
    return f"{SITE_BASE}/reference/{SPEC_SLUGS[stem]}/"


def stdlib_url(page: str) -> str:
    name = posixpath.basename(page).removesuffix(".md")
    if name == "index":
        return f"{SITE_BASE}/stdlib/"
    return f"{SITE_BASE}/stdlib/{name}/"


def repo_blob(path: str, ref: str = "main") -> str:
    return f"{REPOSITORY}/blob/{ref}/{path.lstrip('/')}"


def rewrite_links(text: str, resolver: Callable[[str], str]) -> str:
    """Rewrite Markdown links outside fenced code blocks."""
    resolve = resolver
    output: list[str] = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            fenced = not fenced
            output.append(line)
            continue
        if fenced:
            output.append(line)
            continue
        output.append(
            LINK.sub(
                lambda match: match.group(1) + resolve(match.group(2)) + match.group(3),
                line,
            )
        )
    return "".join(output)
