# SPDX-License-Identifier: MIT OR Apache-2.0
"""Deterministic index of the language reference, shipped with the wheel.

`tools/docs_index.py` generates ``loxia/_spec/index.json`` from ``docs/spec`` and
``docs/stdlib``. This module only reads that artifact: it never parses Markdown, never
touches the network and never depends on the repository being present. The future MCP
`loxia_spec` tool is a thin wrapper over :func:`load_index` and :meth:`DocsIndex.search`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import cast

INDEX_SCHEMA_VERSION = 1
INDEX_RESOURCE = ("_spec", "index.json")


class DocsIndexError(RuntimeError):
    """The packaged index is missing or malformed."""


def _mapping(value: object, what: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise DocsIndexError(f"{what}: expected an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, what: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise DocsIndexError(f"{what}: expected an array")
    return cast(Sequence[object], value)


def _string(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise DocsIndexError(f"{what}: expected a string")
    return value


def _integer(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DocsIndexError(f"{what}: expected an integer")
    return value


@dataclass(frozen=True)
class Section:
    """One heading and its body (children included), with a stable id."""

    id: str
    anchor: str
    title: str
    level: int
    line_start: int
    line_end: int
    url: str
    text: str

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "anchor": self.anchor,
            "title": self.title,
            "level": self.level,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "url": self.url,
            "text": self.text,
        }

    @classmethod
    def from_json(cls, payload: object, *, page_id: str) -> Section:
        data = _mapping(payload, f"{page_id}: section")
        section_id = _string(data.get("id"), f"{page_id}: section id")
        return cls(
            id=section_id,
            anchor=_string(data.get("anchor"), f"{section_id}: anchor"),
            title=_string(data.get("title"), f"{section_id}: title"),
            level=_integer(data.get("level"), f"{section_id}: level"),
            line_start=_integer(data.get("line_start"), f"{section_id}: line_start"),
            line_end=_integer(data.get("line_end"), f"{section_id}: line_end"),
            url=_string(data.get("url"), f"{section_id}: url"),
            text=_string(data.get("text"), f"{section_id}: text"),
        )


@dataclass(frozen=True)
class Page:
    """One reference page (`spec` or `stdlib`) and its sections."""

    id: str
    kind: str
    title: str
    path: str
    url: str
    summary: str
    sources: tuple[str, ...]
    sections: tuple[Section, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "path": self.path,
            "url": self.url,
            "summary": self.summary,
            "sources": list(self.sources),
            "sections": [section.to_json() for section in self.sections],
        }

    @classmethod
    def from_json(cls, payload: object) -> Page:
        data = _mapping(payload, "page")
        page_id = _string(data.get("id"), "page id")
        sources = _sequence(data.get("sources", []), f"{page_id}: sources")
        sections = _sequence(data.get("sections", []), f"{page_id}: sections")
        return cls(
            id=page_id,
            kind=_string(data.get("kind"), f"{page_id}: kind"),
            title=_string(data.get("title"), f"{page_id}: title"),
            path=_string(data.get("path"), f"{page_id}: path"),
            url=_string(data.get("url"), f"{page_id}: url"),
            summary=_string(data.get("summary", ""), f"{page_id}: summary"),
            sources=tuple(_string(item, f"{page_id}: source") for item in sources),
            sections=tuple(Section.from_json(item, page_id=page_id) for item in sections),
        )


@dataclass(frozen=True)
class DocsIndex:
    """The complete artifact: ordered pages, each with ordered sections."""

    schema_version: int
    loxia_version: str
    pages: tuple[Page, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "loxia_version": self.loxia_version,
            "pages": [page.to_json() for page in self.pages],
        }

    @classmethod
    def from_json(cls, payload: object) -> DocsIndex:
        data = _mapping(payload, "index")
        schema_version = _integer(data.get("schema_version"), "schema_version")
        if schema_version != INDEX_SCHEMA_VERSION:
            raise DocsIndexError(
                f"index schema {schema_version} is not supported "
                f"(expected {INDEX_SCHEMA_VERSION}); run `make docs-sync`"
            )
        pages = _sequence(data.get("pages"), "pages")
        return cls(
            schema_version=schema_version,
            loxia_version=_string(data.get("loxia_version"), "loxia_version"),
            pages=tuple(Page.from_json(item) for item in pages),
        )

    def page(self, page_id: str) -> Page | None:
        for page in self.pages:
            if page.id == page_id:
                return page
        return None

    def section(self, section_id: str) -> Section | None:
        for page in self.pages:
            for section in page.sections:
                if section.id == section_id:
                    return section
        return None

    def find_page(self, query: str) -> Page | None:
        """Resolve `spec/syntax`, `spec/sintaxe.md` and `stdlib/json` spellings."""
        needle = query.strip().removesuffix(".md")
        if not needle:
            return None
        for page in self.pages:
            candidates = {
                page.id,
                page.path,
                page.path.removesuffix(".md"),
                page.path.removeprefix("docs/").removesuffix(".md"),
            }
            if needle in candidates:
                return page
        return None

    def search(self, query: str, *, limit: int = 5) -> tuple[Section, ...]:
        """Deterministic substring/term search over titles and bodies.

        Ranking is intentionally simple (no fuzzy matching, no embeddings): exact
        section id, page id, title match, then body match; ties break by page order
        and source line, so the same query always returns the same sections.
        """
        normalized = " ".join(query.lower().split())
        if not normalized:
            return self._top_level(limit)
        exact = self.section(query.strip())
        if exact is not None:
            return (exact,)
        page = self.find_page(query)
        if page is not None:
            sections = [section for section in page.sections if section.level == 2]
            return tuple((sections or list(page.sections))[: self._clamp(limit)])

        terms = normalized.split()
        scored: list[tuple[int, int, int, Section]] = []
        for page_order, current in enumerate(self.pages):
            page_title = current.title.lower()
            for section in current.sections:
                title = section.title.lower()
                text = section.text.lower()
                haystack = f"{title}\n{page_title}\n{text}"
                if not all(term in haystack for term in terms):
                    continue
                score = 0
                if title == normalized:
                    score = 1000
                elif title.startswith(normalized):
                    score = 700
                elif normalized in title:
                    score = 500
                elif normalized in page_title:
                    score = 300
                elif normalized in text:
                    score = 150
                score += 20 * len(terms)
                scored.append((-score, page_order, section.line_start, section))
        scored.sort(key=lambda item: (item[0], item[1], item[2]))
        return tuple(item[3] for item in scored[: self._clamp(limit)])

    def _top_level(self, limit: int) -> tuple[Section, ...]:
        sections = [
            section for page in self.pages for section in page.sections if section.level == 2
        ]
        return tuple(sections[: self._clamp(limit)])

    @staticmethod
    def _clamp(limit: int) -> int:
        return max(1, min(limit, 20))


@cache
def load_index() -> DocsIndex:
    """Load the packaged index once; raise a clear error when it is missing."""
    resource = resources.files("loxia")
    for part in INDEX_RESOURCE:
        resource = resource.joinpath(part)
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as error:
        raise DocsIndexError(
            "packaged documentation index is missing; run `make docs-sync` (or reinstall the wheel)"
        ) from error
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise DocsIndexError("packaged documentation index is not valid JSON") from error
    return DocsIndex.from_json(payload)


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "DocsIndex",
    "DocsIndexError",
    "Page",
    "Section",
    "load_index",
]
