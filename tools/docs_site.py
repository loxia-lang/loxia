# SPDX-License-Identifier: MIT OR Apache-2.0
"""Generate the Starlight content tree from the repository documentation.

The site is a build of ``docs/`` (ADR-0103). This script maps the normative pages,
generated stdlib pages and authored i18n pages into ``site/src/content/docs``, injects
front matter and freshness metadata, and keeps ADRs/TODO/roadmap out of the site.
"""

from __future__ import annotations

import json
import posixpath
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache, partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SPEC = DOCS / "spec"
STDLIB = DOCS / "stdlib"
I18N = DOCS / "i18n"
VERSIONS = DOCS / "versions"
CONTENT = ROOT / "site" / "src" / "content" / "docs"

REPOSITORY = "https://github.com/loxia-lang/loxia"
DEFAULT_LOCALE = "en"

# (source file, site slug, sidebar order)
SPEC_PAGES: tuple[tuple[str, str, int], ...] = (
    ("lexico.md", "lexicon", 1),
    ("sintaxe.md", "syntax", 2),
    ("semantica.md", "semantics", 3),
    ("erros.md", "errors", 4),
    ("garantias.md", "guarantees", 5),
)
SPEC_SLUGS = {source.removesuffix(".md"): slug for source, slug, _ in SPEC_PAGES}

LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")


@dataclass(frozen=True)
class Document:
    front_matter: str
    body: str


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _split_front_matter(text: str) -> Document:
    if not text.startswith("---\n"):
        return Document("", text)
    end = text.find("\n---", 4)
    if end == -1:
        return Document("", text)
    return Document(text[4:end], text[end + 4 :].lstrip("\n"))


def _front_matter_value(block: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in block.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip().strip("'\"")
    return None


def _sources(block: str) -> tuple[str, ...]:
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


def _title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _strip_h1(body: str) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[index + 1 :]).lstrip("\n")
    return body.lstrip("\n")


def _expand_sources(sources: tuple[str, ...]) -> tuple[str, ...]:
    files: set[str] = set()
    for pattern in sources:
        for path in ROOT.glob(pattern):
            if path.is_file():
                files.add(path.relative_to(ROOT).as_posix())
    return tuple(sorted(files))


@cache
def _source_commit(files: tuple[str, ...], ref: str | None) -> tuple[str, str]:
    if not files:
        return ("unknown", "unknown")
    args = ["log", "-1", "--format=%h%x00%cs", "--", *files]
    if ref is not None:
        args = ["log", "-1", "--format=%h%x00%cs", ref, "--", *files]
    raw = _git(*args)
    short, _, date = raw.partition("\x00")
    return (short or "unknown", date or "unknown")


def _commit_link(commit: str) -> str:
    return f"{REPOSITORY}/commit/{commit}"


def _refresh_for(sources: tuple[str, ...], ref: str | None) -> str:
    files = _expand_sources(sources)
    commit, date = _source_commit(files, ref)
    if commit == "unknown":
        return ""
    return f"> Verified against commit [`{commit}`]({_commit_link(commit)}) on {date}.\n"


def _github_path(target: str, ref: str | None) -> str:
    clean = target.split("#", 1)[0].rstrip("/")
    resolved = posixpath.normpath(posixpath.join("docs/spec", clean))
    if resolved in {"AGENTS.md", "IDEIAS-REDDIT.md"}:
        return REPOSITORY
    ref_name = ref or "main"
    return f"{REPOSITORY}/blob/{ref_name}/{resolved}"


def _spec_link(target: str, slug: str, ref: str | None) -> str:
    if target.startswith(("#", "http://", "https://", "mailto:", "/")):
        return target
    url, _, anchor = target.partition("#")
    clean = url.rstrip("/")
    stem = posixpath.basename(clean).removesuffix(".md")
    if stem in SPEC_SLUGS:
        suffix = f"#{anchor}" if anchor else ""
        return f"../{SPEC_SLUGS[stem]}/{suffix}"
    if not clean:
        return target
    resolved = _github_path(clean, ref)
    suffix = f"#{anchor}" if anchor else ""
    return f"{resolved}{suffix}"


def _rewrite_links(text: str, resolver: Callable[[str], str]) -> str:
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
                lambda match: match.group(1) + resolver(match.group(2)) + match.group(3),
                line,
            )
        )
    return "".join(output)


def _front_matter(title: str, description: str, order: int | None = None) -> str:
    lines = ["---", f"title: {json.dumps(title, ensure_ascii=False)}"]
    lines.append(f"description: {json.dumps(description, ensure_ascii=False)}")
    if order is not None:
        lines.extend(["sidebar:", f"  order: {order}"])
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _write_spec_current() -> int:
    count = 0
    for source, slug, order in SPEC_PAGES:
        path = SPEC / source
        document = _split_front_matter(path.read_text(encoding="utf-8"))
        title = _title(document.body, path.stem)
        body = _strip_h1(document.body)
        body = _rewrite_links(body, partial(_spec_link, slug=slug, ref=None))
        # Relative on purpose: the same page is served again as an i18n fallback at
        # /pt/reference/<slug>/. From /reference/<slug>/ this hits the /1.0/reference/<slug>
        # redirect; from /pt/reference/<slug>/ it lands on /pt/1.0/reference/<slug>/.
        banner = f"> **1.1 (current).** [1.0 archive](../../1.0/reference/{slug}/)\n"
        freshness = _refresh_for(_sources(document.front_matter), None)
        text = (
            _front_matter(title, "Normative reference for the Loxia language (1.1).", order)
            + banner
            + "\n"
            + body
            + "\n\n"
            + freshness
        )
        target = CONTENT / "reference" / f"{slug}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.rstrip() + "\n", encoding="utf-8")
        count += 1
    return count


def _write_spec_archive(version: str) -> int:
    root = VERSIONS / version / "reference"
    manifest_path = VERSIONS / version / "manifest.json"
    if not root.exists() or not manifest_path.exists():
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tag = str(manifest["tag"])
    commit = str(manifest.get("commit", ""))
    date = str(manifest.get("date", ""))
    count = 0
    for _, slug, order in SPEC_PAGES:
        path = root / f"{slug}.md"
        if not path.exists():
            continue
        document = _split_front_matter(path.read_text(encoding="utf-8"))
        title = _front_matter_value(document.front_matter, "title") or _title(
            document.body, path.stem
        )
        body = _strip_h1(document.body)
        banner = f"> **1.0 (arquivado).** [Ver 1.1](../../../../reference/{slug}/)\n"
        if commit:
            freshness = (
                f"> Congelado de [`{tag}`]({REPOSITORY}/releases/tag/{tag}) "
                f"(commit [`{commit}`]({_commit_link(commit)})) em {date}.\n"
            )
        else:
            freshness = f"> Congelado de `{tag}`.\n"
        text = (
            _front_matter(title, "Referência arquivada da linguagem Loxia (1.0).", order)
            + banner
            + "\n"
            + body
            + "\n\n"
            + freshness
        )
        target = CONTENT / "pt" / version / "reference" / f"{slug}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.rstrip() + "\n", encoding="utf-8")
        count += 1
    return count


def _stdlib_link(target: str, page: str) -> str:
    if target.startswith(("#", "http://", "https://", "mailto:", "/")):
        return target
    url, _, anchor = target.partition("#")
    clean = url.rstrip("/")
    if not clean.endswith(".md"):
        return target
    name = posixpath.basename(clean).removesuffix(".md")
    prefix = "" if page == "index" else "../"
    suffix = f"#{anchor}" if anchor else ""
    return f"{prefix}{name}/{suffix}"


def _write_stdlib() -> int:
    count = 0
    for path in sorted(STDLIB.glob("*.md")):
        page = path.stem
        document = _split_front_matter(path.read_text(encoding="utf-8"))
        title = _front_matter_value(document.front_matter, "title") or _title(document.body, page)
        if page == "builtins":
            title = "Builtins and kernel"
        body = _strip_h1(document.body)
        body = _rewrite_links(body, partial(_stdlib_link, page=page))
        freshness = _refresh_for(_sources(document.front_matter), None)
        text = (
            _front_matter(title, "Standard library reference.", 0 if page == "index" else None)
            + body
            + "\n\n"
            + freshness
        )
        target = CONTENT / "stdlib" / f"{page}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.rstrip() + "\n", encoding="utf-8")
        count += 1
    return count


def _strip_front_matter_keys(text: str, keys: tuple[str, ...]) -> str:
    document = _split_front_matter(text)
    if not document.front_matter:
        return text
    kept: list[str] = []
    skipping = False
    for line in document.front_matter.splitlines():
        if any(line.startswith(f"{key}:") for key in keys):
            skipping = True
            continue
        if skipping and line.startswith((" ", "\t", "- ")):
            continue
        skipping = False
        kept.append(line)
    return "---\n" + "\n".join(kept) + "\n---\n\n" + document.body


def _copy_i18n() -> int:
    count = 0
    for locale in ("en", "pt"):
        source_root = I18N / locale
        if not source_root.exists():
            continue
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".mdx"}:
                continue
            relative = path.relative_to(source_root)
            target = CONTENT / ("" if locale == "en" else locale) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            text = _strip_front_matter_keys(
                path.read_text(encoding="utf-8"), ("sources", "translated_from")
            )
            target.write_text(text, encoding="utf-8")
            count += 1
    return count


def build() -> None:
    if CONTENT.exists():
        shutil.rmtree(CONTENT)
    CONTENT.mkdir(parents=True, exist_ok=True)

    authored = _copy_i18n()
    stdlib = _write_stdlib()
    current = _write_spec_current()
    archive = _write_spec_archive("1.0")
    print(
        f"docs-site: {authored} authored page(s), {stdlib} stdlib page(s), "
        f"{current} current reference page(s), {archive} archived page(s)"
    )


if __name__ == "__main__":
    build()
