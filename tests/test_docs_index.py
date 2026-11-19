# SPDX-License-Identifier: MIT OR Apache-2.0
"""Drift gates for the agent-facing documentation index (ADR-0111).

The index is generated, shipped in the wheel and consumed by the future MCP
`loxia_spec` tool. These tests prove that it is in sync with the Markdown sources, uses
the same anchors/URLs as the Starlight site and is deterministic.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from loxia import __version__
from loxia.docs_index import load_index
from tools.docs_common import (
    SITE_BASE,
    SPEC_PAGES,
    STDLIB,
    slugify,
    spec_url,
    stdlib_url,
)

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "loxia" / "_spec" / "index.json"
LLMS = ROOT / "site" / "public" / "llms.txt"
DIST = ROOT / "site" / "dist"
LINK = re.compile(r"\]\(([^)\s]+)\)")
HTML_ID = re.compile(r'id="([^"]+)"')


def _raw() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(INDEX.read_text(encoding="utf-8")))


def test_generated_index_and_llms_are_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "docs_index.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_index_shape_order_and_unique_ids() -> None:
    raw = _raw()
    assert raw["schema_version"] == 1
    assert raw["loxia_version"] == __version__
    pages = cast(list[dict[str, Any]], raw["pages"])

    page_ids = [page["id"] for page in pages]
    assert len(page_ids) == len(set(page_ids))
    assert page_ids[: len(SPEC_PAGES)] == [f"spec/{slug}" for _, slug, _ in SPEC_PAGES]
    stdlib_ids = page_ids[len(SPEC_PAGES) :]
    assert stdlib_ids[0] == "stdlib/index"
    assert stdlib_ids == ["stdlib/index", *sorted(stdlib_ids[1:])]

    section_ids: list[str] = []
    for page in pages:
        assert page["kind"] in {"spec", "stdlib"}
        assert page["path"].endswith(".md")
        assert not Path(page["path"]).is_absolute()
        assert (ROOT / page["path"]).is_file()
        assert page["url"].startswith(f"{SITE_BASE}/")
        for section in cast(list[dict[str, Any]], page["sections"]):
            section_ids.append(section["id"])
            assert section["line_start"] >= 1
            assert section["line_end"] > section["line_start"]
            assert section["url"] == f"{page['url']}#{section['anchor']}"
    assert len(section_ids) == len(set(section_ids))


def test_line_numbers_point_at_the_heading() -> None:
    for page in cast(list[dict[str, Any]], _raw()["pages"]):
        path = ROOT / page["path"]
        lines = path.read_text(encoding="utf-8").splitlines()
        for section in cast(list[dict[str, Any]], page["sections"]):
            heading = lines[section["line_start"] - 1]
            assert heading.startswith("#" * section["level"]), (page["id"], section["id"], heading)
            title = heading.lstrip("#").strip()
            if title.startswith("`") and title.endswith("`"):
                title = title[1:-1].strip()
            else:
                title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
                title = title.replace("`", "").strip()
            assert title.startswith(section["title"][:20]), (section["id"], title)


def test_urls_and_anchors_match_the_site_routes() -> None:
    for source, slug, _ in SPEC_PAGES:
        assert spec_url(source) == f"{SITE_BASE}/reference/{slug}/"
    assert stdlib_url("index") == f"{SITE_BASE}/stdlib/"
    assert stdlib_url("json") == f"{SITE_BASE}/stdlib/json/"

    raw = _raw()
    page_urls = {page["id"]: page["url"] for page in cast(list[dict[str, Any]], raw["pages"])}
    assert page_urls["spec/syntax"] == f"{SITE_BASE}/reference/syntax/"
    assert page_urls["stdlib/json"] == f"{SITE_BASE}/stdlib/json/"


def test_anchor_algorithm_matches_starlight() -> None:
    assert slugify("Grammar (EBNF)") == "grammar-ebnf"
    assert slugify("Type checker (`--check`)") == "type-checker---check"
    assert slugify("Equality (`==`, `!=`)") == "equality--"
    assert slugify("I1 — Executable equivalence") == "i1--executable-equivalence"

    anchors = {
        section["id"]
        for page in cast(list[dict[str, Any]], _raw()["pages"])
        for section in cast(list[dict[str, Any]], page["sections"])
    }
    assert "spec/errors#syntax-1" in anchors
    assert "stdlib/lists#fn-mapt-uxs-listt-f-fnt---u---listu" in anchors


def test_anchors_match_the_built_site_when_available() -> None:
    if not (DIST / "reference").is_dir():
        return
    for page in cast(list[dict[str, Any]], _raw()["pages"]):
        if page["kind"] == "spec":
            slug = cast(str, page["url"]).rstrip("/").rsplit("/", 1)[-1]
            html = DIST / "reference" / slug / "index.html"
        else:
            name = (
                "index"
                if page["id"] == "stdlib/index"
                else page["url"].rstrip("/").rsplit("/", 1)[-1]
            )
            html = DIST / "stdlib" / name / "index.html"
        if not html.is_file():
            continue
        ids = set(HTML_ID.findall(html.read_text(encoding="utf-8")))
        for section in cast(list[dict[str, Any]], page["sections"]):
            assert section["anchor"] in ids, (section["id"], html.relative_to(ROOT))


def test_links_are_canonical_and_never_relative_markdown() -> None:
    for page in cast(list[dict[str, Any]], _raw()["pages"]):
        for section in cast(list[dict[str, Any]], page["sections"]):
            for target in LINK.findall(section["text"]):
                assert target.startswith(("http://", "https://", "mailto:", "#", "/", "data:")), (
                    section["id"],
                    target,
                )
                if target.endswith(".md"):
                    assert target.startswith("https://github.com/loxia-lang/loxia/"), (
                        section["id"],
                        target,
                    )


def test_index_has_no_volatile_data() -> None:
    text = INDEX.read_text(encoding="utf-8")
    raw = _raw()
    assert set(raw) == {"schema_version", "loxia_version", "pages"}
    assert str(ROOT) not in text
    assert "generated_at" not in raw


def test_llms_txt_lists_every_page_and_uses_canonical_urls() -> None:
    text = LLMS.read_text(encoding="utf-8")
    assert text.startswith("# Loxia\n")
    assert "## Language reference" in text
    assert "## Standard library" in text
    for page in cast(list[dict[str, Any]], _raw()["pages"]):
        assert page["url"] in text, page["id"]
    assert text.index("## Language reference") < text.index("## Standard library")
    for target in LINK.findall(text):
        assert target.startswith(("http://", "https://")), target


def test_runtime_index_matches_the_artifact_and_search_is_stable() -> None:
    index = load_index()
    assert index.to_json() == _raw()

    exact = index.section("spec/syntax#optional-semicolon")
    assert exact is not None and exact.title == "Optional semicolon"
    assert index.search("spec/syntax#optional-semicolon") == (exact,)
    assert index.search("optional semicolon")[0].id == "spec/syntax#optional-semicolon"
    assert index.search("optional semicolon") == index.search("optional semicolon")
    assert index.find_page("spec/sintaxe.md") is not None
    assert index.find_page("stdlib/json.md") is not None

    top = index.search("", limit=3)
    assert len(top) == 3
    assert all(section.level == 2 for section in top)


def test_every_reference_page_is_indexed() -> None:
    ids = {page.id for page in load_index().pages}
    for source, slug, _ in SPEC_PAGES:
        assert f"spec/{slug}" in ids
        assert source
    for path in STDLIB.glob("*.md"):
        page = "index" if path.stem == "index" else path.stem
        assert f"stdlib/{page}" in ids
