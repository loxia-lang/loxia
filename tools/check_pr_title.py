# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validate a pull request title (the squash commit header)."""

from __future__ import annotations

import os
import sys

from tools.conventional import validate


def main(argv: list[str]) -> int:
    title = argv[1] if len(argv) > 1 else os.environ.get("PR_TITLE", "")
    error = validate(title)
    if error is not None:
        print(f"pr-title: {error}", file=sys.stderr)
        print("see CONTRIBUTING.md § Commit messages", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
