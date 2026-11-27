# SPDX-License-Identifier: MIT OR Apache-2.0
"""Generate the deterministic documentation index used by agents and the site.

The index is a projection of `docs/spec/*.md` and `docs/stdlib/*.md`:

- page ids and URLs match the Starlight routes (`spec/syntax`, `/reference/syntax/`);
- section anchors use the same `github-slugger` algorithm as Starlight;
- every Markdown link is rewritten to a canonical site or GitHub URL;
- the result has no timestamps, absolute paths or git state.

It also writes `site/public/llms.txt`, so the human site and agent-facing artifacts share
one catalog. Run with `--check` in tests/CI and `--write` via `make docs-index`.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loxia import __version__  # noqa: E402
from loxia.docs_index import (  # noqa: E402
    INDEX_SCHEMA_VERSION,
    CodeEntry,
    DocsIndex,
    Page,
    Section,
)
from loxia_core.diagnostics.codes import (  # noqa: E402
    CODE_DESCRIPTIONS,
    CODE_PHASE,
    Code,
)
from tools.docs_common import (  # noqa: E402
    REPOSITORY,
    ROOT,
    SITE_BASE,
    SPEC,
    SPEC_PAGES,
    SPEC_SLUGS,
    STDLIB,
    STDLIB_TITLES,
    front_matter_value,
    repo_blob,
    rewrite_links,
    slugify,
    sources,
    spec_url,
    split_front_matter,
    stdlib_url,
    title,
)

INDEX_PATH = ROOT / "loxia" / "_spec" / "index.json"
LLMS_PATH = ROOT / "site" / "public" / "llms.txt"

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")
_LINK_LABEL = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_EMPHASIS = re.compile(r"\*\*([^*]+)\*\*|\*([^*]+)\*")


@dataclass(frozen=True)
class Heading:
    index: int
    level: int
    title: str
    line: int


def _headings(lines: list[str]) -> list[Heading]:
    found: list[Heading] = []
    fenced = False
    for index, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = _HEADING.match(line)
        if match is None:
            continue
        found.append(
            Heading(
                index=index,
                level=len(match.group(1)),
                title=match.group(2).strip(),
                line=index + 1,
            )
        )
    return found


def _plain_heading(heading: str) -> str:
    """Rendered heading text: link labels, without code ticks or URL syntax.

    Code spans are protected before link parsing: `fn f[T](actual: T, ...)` is not a
    Markdown link, even though its parameter list looks like one.
    """
    code: list[str] = []

    def protect(match: re.Match[str]) -> str:
        code.append(match.group(0)[1:-1])
        return f"\x00{len(code) - 1}\x00"

    text = re.sub(r"`[^`]*`", protect, heading)
    text = _LINK_LABEL.sub(r"\1", text)
    for index, value in enumerate(code):
        text = text.replace(f"\x00{index}\x00", value)
    return text.strip()


def _anchors(headings: list[Heading]) -> dict[int, str]:
    seen: dict[str, int] = {}
    anchors: dict[int, str] = {}
    for heading in headings:
        if heading.level < 2:
            continue
        base = slugify(_plain_heading(heading.title)) or "section"
        count = seen.get(base, 0)
        anchors[heading.index] = base if count == 0 else f"{base}-{count}"
        seen[base] = count + 1
    return anchors


def _sections(
    lines: list[str],
    headings: list[Heading],
    page_id: str,
    page_url: str,
    resolver: Callable[[str], str],
    line_offset: int,
) -> tuple[Section, ...]:
    anchors = _anchors(headings)
    sections: list[Section] = []
    for position, heading in enumerate(headings):
        if heading.level < 2:
            continue
        end = len(lines)
        for following in headings[position + 1 :]:
            if following.level <= heading.level:
                end = following.index
                break
        section_text = "\n".join(lines[heading.index : end]).rstrip() + "\n"
        anchor = anchors[heading.index]
        sections.append(
            Section(
                id=f"{page_id}#{anchor}",
                anchor=anchor,
                title=_plain_heading(heading.title),
                level=heading.level,
                line_start=line_offset + heading.line,
                line_end=line_offset + end + 1,
                url=f"{page_url}#{anchor}",
                text=rewrite_links(section_text, resolver),
            )
        )
    return tuple(sections)


def _resolver(page_path: str, page_url: str) -> Callable[[str], str]:
    base = posixpath.dirname(page_path)

    def resolve(target: str) -> str:
        if target.startswith("#"):
            return f"{page_url}{target}"
        if target.startswith(("http://", "https://", "mailto:", "/", "data:")):
            return target
        url, separator, anchor = target.partition("#")
        if not url:
            return page_url + (f"#{anchor}" if separator else "")
        clean = url.split("?", 1)[0].rstrip("/")
        resolved = posixpath.normpath(posixpath.join(base, clean))
        suffix = f"#{anchor}" if separator else ""
        stem = posixpath.basename(resolved).removesuffix(".md")
        if resolved.startswith("docs/spec/") and stem in SPEC_SLUGS:
            return f"{spec_url(stem)}{suffix}"
        if resolved.startswith("docs/stdlib/") and stem:
            return f"{stdlib_url(stem)}{suffix}"
        return f"{repo_blob(resolved)}{suffix}"

    return resolve


def _summary(body: str) -> str:
    lines = body.splitlines()
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("# "):
            start = index + 1
            break
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("#"):
            end = index
            break
    paragraph: list[str] = []
    for line in lines[start:end]:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith(("```", "~~~", "|", ">", "- ", "* ", "1.")):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    text = " ".join(paragraph)
    text = _LINK_LABEL.sub(r"\1", text)
    text = _EMPHASIS.sub(lambda match: match.group(1) or match.group(2) or "", text)
    text = " ".join(text.replace("`", "").split())
    if len(text) <= 240:
        return text
    sentence = text.find(". ", 20)
    if 20 <= sentence <= 240:
        return text[: sentence + 1]
    return text[:237].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."


def _page(source: Path, *, kind: str, page_id: str, page_url: str) -> Page:
    text = source.read_text(encoding="utf-8")
    document = split_front_matter(text)
    lines = document.body.splitlines()
    line_offset = text[: text.find(document.body)].count("\n") if document.body else 0
    headings = _headings(lines)
    page_title = front_matter_value(document.front_matter, "title") or _plain_heading(
        title(document.body, source.stem)
    )
    if kind == "stdlib":
        page_title = STDLIB_TITLES.get(source.stem, page_title)
    resolver = _resolver(source.relative_to(ROOT).as_posix(), page_url)
    rewritten = rewrite_links(document.body, resolver)
    return Page(
        id=page_id,
        kind=kind,
        title=page_title,
        path=source.relative_to(ROOT).as_posix(),
        url=page_url,
        summary=_summary(rewritten),
        sources=sources(document.front_matter),
        sections=_sections(lines, headings, page_id, page_url, resolver, line_offset),
    )


def _spec_pages() -> list[Page]:
    pages: list[Page] = []
    for source_name, slug, _ in SPEC_PAGES:
        source = SPEC / source_name
        pages.append(
            _page(
                source,
                kind="spec",
                page_id=f"spec/{slug}",
                page_url=f"{SITE_BASE}/reference/{slug}/",
            )
        )
    return pages


def _stdlib_pages() -> list[Page]:
    paths = sorted(STDLIB.glob("*.md"), key=lambda path: (path.stem != "index", path.name))
    pages: list[Page] = []
    for source in paths:
        page = "index" if source.stem == "index" else source.stem
        pages.append(
            _page(
                source,
                kind="stdlib",
                page_id=f"stdlib/{page}",
                page_url=stdlib_url(page),
            )
        )
    return pages


def _codes() -> tuple[CodeEntry, ...]:
    """The diagnostic catalog, in code order (the same table as docs/spec/erros.md)."""
    return tuple(
        CodeEntry(
            code=code.value,
            phase=CODE_PHASE[code].value,
            description=CODE_DESCRIPTIONS[code],
        )
        for code in sorted(Code, key=lambda item: item.value)
    )


def build() -> DocsIndex:
    return DocsIndex(
        schema_version=INDEX_SCHEMA_VERSION,
        loxia_version=__version__,
        pages=tuple([*_spec_pages(), *_stdlib_pages()]),
        codes=_codes(),
    )


def render_index(index: DocsIndex) -> str:
    return json.dumps(index.to_json(), ensure_ascii=False, indent=2) + "\n"


def _llms_entry(page: Page) -> str:
    suffix = f": {page.summary}" if page.summary else ""
    return f"- [{page.title}]({page.url}){suffix}"


def render_llms(index: DocsIndex) -> str:
    spec = [page for page in index.pages if page.kind == "spec"]
    stdlib = [page for page in index.pages if page.kind == "stdlib"]
    lines = [
        "# Loxia",
        "",
        "> Loxia is a small, statically checked Lox dialect with a tree-walk interpreter "
        "and an optional LLVM backend.",
        "",
        "## Language reference",
        "",
        *[_llms_entry(page) for page in spec],
        "",
        "## Standard library",
        "",
        *[_llms_entry(page) for page in stdlib],
        "",
        "## Optional",
        "",
        f"- [Architecture]({repo_blob('docs/tech/arquitetura.md')})",
        f"- [ADRs]({REPOSITORY}/tree/main/docs/adr)",
        f"- [Changelog]({repo_blob('CHANGELOG.md')})",
        f"- [Repository]({REPOSITORY})",
        "",
    ]
    return "\n".join(lines)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _check(path: Path, text: str) -> bool:
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    return current == text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write the artifacts")
    mode.add_argument("--check", action="store_true", help="fail if the artifacts are stale")
    args = parser.parse_args(argv)

    index = build()
    index_text = render_index(index)
    llms_text = render_llms(index)
    outputs = ((INDEX_PATH, index_text), (LLMS_PATH, llms_text))
    stale = [(path, text) for path, text in outputs if not _check(path, text)]

    if args.write:
        for path, text in outputs:
            _write(path, text)
        print(
            f"docs-index: wrote {len(index.pages)} page(s), "
            f"{sum(len(page.sections) for page in index.pages)} section(s)"
        )
        return 0

    for path, _ in stale:
        print(f"docs-index: stale {path.relative_to(ROOT)}", file=sys.stderr)
    if stale:
        print("docs-index: run `make docs-index` (or `make docs-sync`)", file=sys.stderr)
        return 1
    print(
        f"docs-index: up to date ({len(index.pages)} page(s), "
        f"{sum(len(page.sections) for page in index.pages)} section(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
