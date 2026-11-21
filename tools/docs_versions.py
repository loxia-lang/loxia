# SPDX-License-Identifier: MIT OR Apache-2.0
"""Freeze a reference snapshot from a release tag for the documentation site.

Usage:
    uv run python tools/docs_versions.py --version 1.0 --tag v1.0.0

The snapshot is committed under ``docs/versions/<version>/reference``; links are normalized
once (internal spec links become relative, ADR/roadmap links point at the tag on GitHub).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.docs_common import SPEC_PAGES, VERSIONS  # noqa: E402
from tools.docs_site import (  # noqa: E402
    _rewrite_links,
    _spec_link,
    _split_front_matter,
    _strip_h1,
    _title,
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.rstrip("\n")


def _show(tag: str, path: str) -> str:
    return _git("show", f"{tag}:{path}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="1.0")
    parser.add_argument("--tag", default="v1.0.0")
    args = parser.parse_args(argv[1:])

    tag = args.tag
    commit = _git("rev-parse", "--short", f"{tag}^{{}}")
    date = _git("log", "-1", "--format=%cs", f"{tag}^{{}}")
    out = VERSIONS / args.version / "reference"
    out.mkdir(parents=True, exist_ok=True)

    pages: dict[str, dict[str, str]] = {}
    for source, slug, _ in SPEC_PAGES:
        path = f"docs/spec/{source}"
        text = _show(tag, path)
        document = _split_front_matter(text)
        title = _title(document.body, slug)
        body = _strip_h1(document.body)
        body = _rewrite_links(body, partial(_spec_link, slug=source.removesuffix(".md"), ref=tag))
        sources = []
        for line in document.front_matter.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                sources.append(stripped[2:].strip())
        front = [
            "---",
            f"title: {json.dumps(title, ensure_ascii=False)}",
            "sources:",
            *[f"  - {item}" for item in sources],
            "---",
            "",
        ]
        (out / f"{slug}.md").write_text("\n".join(front) + body + "\n", encoding="utf-8")
        pages[slug] = {"source": path, "title": title}

    manifest = {
        "version": args.version,
        "tag": tag,
        "commit": commit,
        "date": date,
        "pages": pages,
    }
    (VERSIONS / args.version / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"docs-version: wrote {len(pages)} page(s) for {args.version} from {tag} ({commit})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
