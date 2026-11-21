# SPDX-License-Identifier: MIT OR Apache-2.0
"""Check the Developer Certificate of Origin sign-off on pull request commits."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loxia_core.loader.gitenv import git_env


def has_signoff(message: str) -> bool:
    """True when at least one Signed-off-by trailer has a non-empty value."""
    for line in message.splitlines():
        if line.lower().startswith("signed-off-by:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return True
    return False


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        env=git_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def missing_signoffs(base: str, head: str) -> list[str]:
    missing: list[str] = []
    for sha in _git("rev-list", f"{base}..{head}").splitlines():
        parents = _git("show", "-s", "--format=%P", sha).split()
        if len(parents) > 1:
            continue  # merge commits are not authored through the DCO flow
        author = _git("show", "-s", "--format=%an <%ae>", sha)
        if "[bot]" in author:
            continue  # Dependabot and GitHub Actions cannot sign off manually
        if not has_signoff(_git("show", "-s", "--format=%B", sha)):
            missing.append(sha)
    return missing


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("BASE_SHA", ""))
    parser.add_argument("--head", default=os.environ.get("HEAD_SHA", "HEAD"))
    args = parser.parse_args(argv[1:])

    if not args.base:
        print("dco: --base (or BASE_SHA) is required", file=sys.stderr)
        return 2

    try:
        missing = missing_signoffs(args.base, args.head)
    except RuntimeError as error:
        print(f"dco: {error}", file=sys.stderr)
        return 2

    if missing:
        print("dco: commits without Signed-off-by:", file=sys.stderr)
        for sha in missing:
            print(f"  {sha}", file=sys.stderr)
        print(
            "run `git commit -s` or add the trailer with `git rebase --signoff`.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
