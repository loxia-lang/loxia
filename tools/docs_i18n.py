# SPDX-License-Identifier: MIT OR Apache-2.0
"""Check translated documentation pages against the source commit they came from.

A translated page declares:

    ---
    translated_from: 1a2b3c4
    source: docs/spec/semantica.md
    ---

`make docs-i18n-check` reports pages whose source changed after `translated_from`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from loxia_core.loader.gitenv import git_env

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "docs" / "i18n"


def _front_matter(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    return text[4:end] if end != -1 else ""


def _value(block: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in block.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip().strip("'\"")
    return None


def _commit(path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%h", "--", path],
        capture_output=True,
        text=True,
        check=False,
        env=git_env(),
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail on stale translations")
    args = parser.parse_args(argv[1:])

    translated = 0
    malformed: list[str] = []
    stale: list[str] = []

    for path in sorted(I18N.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".mdx"}:
            continue
        block = _front_matter(path.read_text(encoding="utf-8"))
        translated_from = _value(block, "translated_from")
        if not translated_from:
            continue
        translated += 1
        source = _value(block, "source")
        if not source:
            malformed.append(f"{path.relative_to(ROOT)}: translated_from without source")
            continue
        current = _commit(source)
        if not current:
            malformed.append(f"{path.relative_to(ROOT)}: source {source!r} not found")
            continue
        if not current.startswith(translated_from) and not translated_from.startswith(current):
            stale.append(
                f"{path.relative_to(ROOT)}: translated from {translated_from}, "
                f"source is at {current}"
            )

    print(f"docs-i18n: {translated} translated page(s)")
    for problem in malformed:
        print(f"  error: {problem}", file=sys.stderr)
    for problem in stale:
        print(f"  stale: {problem}", file=sys.stderr)

    if malformed:
        return 1
    if stale and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
