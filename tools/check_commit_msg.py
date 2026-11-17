# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validate the message file passed by the commit-msg hook."""

from __future__ import annotations

import sys
from pathlib import Path

from tools.conventional import validate


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_commit_msg.py <commit-message-file>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    try:
        message = path.read_text(encoding="utf-8")
    except OSError as read_error:
        print(f"commit-msg: cannot read {path}: {read_error}", file=sys.stderr)
        return 2

    problem = validate(message)
    if problem is not None:
        print(f"commit-msg: {problem}", file=sys.stderr)
        print("see CONTRIBUTING.md § Commit messages", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
