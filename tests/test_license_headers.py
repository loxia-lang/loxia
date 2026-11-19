# SPDX-License-Identifier: MIT OR Apache-2.0
"""Every distributed source file declares the SPDX license expression."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPDX = "SPDX-License-Identifier: MIT OR Apache-2.0"

# Fixtures and third-party files keep their own licensing or must preserve error line
# numbers; generated files carry a generated header instead.
EXCLUDED_PREFIXES = (
    "tests/cases/",
    "tests/official/",
    "bench/cases/",
    "examples/",
)
EXCLUDED_FILES = {
    "runtime/kernel_gen.h",
    "editors/grammar/loxia.ts",
    "editors/grammar/loxia.mjs",
}
SOURCE_SUFFIXES = {".py", ".c", ".h", ".lx", ".mjs", ".ts", ".css"}
# O cliente VS Code agora vive em loxia-lang/loxia-vscode (ADR-0109).
EXTRA_SOURCES: set[str] = set()


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def covered(path: str) -> bool:
    if path in EXCLUDED_FILES or path.startswith(EXCLUDED_PREFIXES):
        return False
    if path in EXTRA_SOURCES:
        return True
    return Path(path).suffix in SOURCE_SUFFIXES


def test_sources_declare_the_spdx_expression() -> None:
    missing = [
        path
        for path in tracked_files()
        if covered(path)
        and SPDX not in "\n".join((ROOT / path).read_text(encoding="utf-8").splitlines()[:2])
    ]

    assert missing == [], "fontes sem SPDX: " + ", ".join(missing)
