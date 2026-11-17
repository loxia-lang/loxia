# SPDX-License-Identifier: MIT OR Apache-2.0
"""Check internal links in the built Starlight site.

The source link test only knows repository files; this checker walks the generated HTML
and resolves absolute `/loxia/...` and relative links against ``site/dist``.
"""

from __future__ import annotations

import argparse
import posixpath
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "site" / "dist"
BASE = "/loxia/"


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"a", "link"}:
            return
        for name, value in attrs:
            if name == "href" and value:
                self.links.append(value)


def _external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "javascript:", "data:", "//", "#"))


def _resolve(current: str, href: str) -> str | None:
    path = href.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    if path.startswith(BASE):
        relative = path[len(BASE) :]
    elif path.startswith("/"):
        relative = path[1:]
    else:
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(current), path))
    if relative in {"", "."}:
        relative = "index.html"
    elif relative.endswith("/"):
        relative += "index.html"
    elif not posixpath.splitext(relative)[1]:
        relative += "/index.html"
    return relative


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail on broken links")
    args = parser.parse_args(argv[1:])

    if not DIST.is_dir():
        print(f"docs-links: {DIST} does not exist; build the site first", file=sys.stderr)
        return 2

    broken: list[str] = []
    for page in sorted(DIST.rglob("*.html")):
        relative_page = page.relative_to(DIST).as_posix()
        collector = LinkCollector()
        collector.feed(page.read_text(encoding="utf-8"))
        for href in collector.links:
            if _external(href):
                continue
            target = _resolve(relative_page, href)
            if target is None:
                continue
            if not (DIST / target).exists():
                broken.append(f"{relative_page} -> {href} (resolved {target})")

    for item in broken:
        print(f"  broken: {item}", file=sys.stderr)
    print(f"docs-links: {len(broken)} broken internal link(s)")
    return 1 if broken and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
