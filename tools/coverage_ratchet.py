# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ratchet de cobertura Python por arquivo (ADR-0122).

`coverage-baseline.toml` guarda o piso inteiro de cada módulo crítico. O gate falha se
a cobertura medida ficar abaixo do piso; `--update` só sobe o piso, nunca desce.

    uv run coverage json -o .coverage.json
    uv run python tools/coverage_ratchet.py --check
    uv run python tools/coverage_ratchet.py --update
"""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "coverage-baseline.toml"
REPORT = ROOT / ".coverage.json"


def load_baseline() -> dict[str, int]:
    payload = tomllib.loads(BASELINE.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise SystemExit("coverage-baseline.toml: schema_version deve ser 1")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise SystemExit("coverage-baseline.toml: tabela [files] vazia")
    baseline: dict[str, int] = {}
    for path, value in files.items():
        if not isinstance(path, str) or not isinstance(value, int):
            raise SystemExit(f"coverage-baseline.toml: entrada inválida {path!r}")
        baseline[path] = value
    return baseline


def load_report() -> dict[str, float]:
    if not REPORT.is_file():
        raise SystemExit(f"relatório ausente: {REPORT}; rode `make coverage` antes")
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict):
        raise SystemExit("relatório de cobertura sem `files`")
    result: dict[str, float] = {}
    for path, entry in files.items():
        summary = entry.get("summary") if isinstance(entry, dict) else None
        if isinstance(summary, dict) and isinstance(summary.get("percent_covered"), (int, float)):
            result[path] = float(summary["percent_covered"])
    return result


def compare(actual: dict[str, float], baseline: dict[str, int]) -> list[str]:
    problems: list[str] = []
    for path in sorted(baseline):
        if path not in actual:
            problems.append(f"{path}: ausente no relatório")
            continue
        floor = int(actual[path])
        if floor < baseline[path]:
            problems.append(f"{path}: {actual[path]:.1f}% < piso {baseline[path]}%")
    return problems


def update(actual: dict[str, float], baseline: dict[str, int]) -> tuple[dict[str, int], list[str]]:
    changed: list[str] = []
    updated = dict(baseline)
    for path in sorted(baseline):
        if path not in actual:
            continue
        floor = int(actual[path])
        if floor > baseline[path]:
            updated[path] = floor
            changed.append(f"{path}: {baseline[path]}% -> {floor}%")
    return updated, changed


def write_baseline(baseline: dict[str, int]) -> None:
    lines = [
        "schema_version = 1",
        "",
        "# Pisos inteiros de cobertura por arquivo (branch). Só sobem (ADR-0122).",
        "[files]",
    ]
    for path in sorted(baseline):
        lines.append(f'"{path}" = {baseline[path]}')
    BASELINE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.coverage_ratchet")
    parser.add_argument("--check", action="store_true", help="falha abaixo do piso")
    parser.add_argument("--update", action="store_true", help="sobe o piso até o medido")
    args = parser.parse_args(argv)
    baseline = load_baseline()
    actual = load_report()
    problems = compare(actual, baseline)
    if args.update:
        updated, changed = update(actual, baseline)
        if changed:
            write_baseline(updated)
            for line in changed:
                print(f"ratchet: {line}")
        else:
            print("ratchet: nenhum piso para subir")
        return 0
    if problems:
        for problem in problems:
            print(f"ratchet: {problem}")
        print("Rode `make coverage` para ver o relatório; suba o piso só com teste.")
        return 1
    for path in sorted(baseline):
        print(f"ratchet: {path}: {actual[path]:.1f}% (piso {baseline[path]}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
