# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validation helpers for Conventional Commits and pull request titles."""

from __future__ import annotations

import re

TYPES = frozenset(
    {
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
    }
)

# <type>(<scope>)!: <subject>; scope is optional, breaking marker is optional.
PATTERN = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9][a-z0-9-]*)\))?(?P<breaking>!)?: "
    r"(?P<subject>\S.*)$"
)

# Local history helpers that must not be blocked while rebasing or merging.
SKIP_PREFIXES = ("Merge ", "fixup! ", "squash! ", "amend! ")

MAX_HEADER = 100


def first_line(message: str) -> str:
    """First non-empty, non-comment line of a commit message or PR title."""
    for line in message.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def validate(message: str) -> str | None:
    """Return an error message, or ``None`` when the header is conventional."""
    header = first_line(message)
    if not header:
        return "empty message"
    if header.startswith(SKIP_PREFIXES):
        return None

    match = PATTERN.fullmatch(header)
    if match is None:
        return "expected '<type>(<scope>): <subject>' (scope and ! are optional)"

    kind = match.group("type")
    if kind not in TYPES:
        allowed = ", ".join(sorted(TYPES))
        return f"unknown type '{kind}'; allowed: {allowed}"

    subject = match.group("subject").strip()
    if not subject:
        return "empty subject"
    if subject.endswith("."):
        return "subject must not end with a period"
    if len(header) > MAX_HEADER:
        return f"header is {len(header)} characters; keep it under {MAX_HEADER}"

    return None
