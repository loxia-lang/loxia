# SPDX-License-Identifier: MIT OR Apache-2.0
"""Baseline local de parse e formatação do front-end (ADR-0129).

Mede o corpus inteiro (std/, tests/cases/, examples/) com o mesmo Scanner/Parser que o
oráculo usa, sem subprocesso. Não é gate de CI: serve para comparar antes/depois da fase A
e para dimensionar o dogfood. A memória é `tracemalloc` do Python, não o heap nativo do
backend.

Uso:
    uv run python tools/frontend_bench.py
    uv run python tools/frontend_bench.py --repeat 7
"""

from __future__ import annotations

import argparse
import statistics
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path

from loxia.formatter import format_source
from loxia.formatter.printer import Printer
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner

ROOT = Path(__file__).resolve().parents[1]
CORPUS_GLOBS = ("std/**/*.lx", "tests/cases/**/*.lx", "examples/**/*.lx")


def corpus() -> list[Path]:
    files: set[Path] = set()
    for pattern in CORPUS_GLOBS:
        files.update(ROOT.glob(pattern))
    return sorted(files)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_pass(files: list[Path]) -> tuple[int, int, int]:
    tokens = 0
    statements = 0
    parsed = 0
    for path in files:
        reporter = ErrorReporter(max_errors=0)
        scanned = Scanner(_read(path), reporter).scan_tokens()
        tokens += len(scanned)
        tree = Parser(scanned, reporter=reporter).parse()
        if tree is not None and not reporter.had_error:
            parsed += 1
            statements += len(tree)
    return parsed, tokens, statements


def format_pass(files: list[Path]) -> int:
    formatted = 0
    for path in files:
        if format_source(_read(path)) is not None:
            formatted += 1
    return formatted


def breakdown_pass(files: list[Path]) -> dict[str, float]:
    totals = {"scan": 0.0, "parse": 0.0, "print": 0.0}
    for path in files:
        source = _read(path)
        reporter = ErrorReporter(max_errors=0)

        start = time.perf_counter()
        scanner = Scanner(source, reporter)
        tokens = scanner.scan_tokens()
        totals["scan"] += (time.perf_counter() - start) * 1000
        if reporter.had_error:
            continue

        start = time.perf_counter()
        tree = Parser(tokens, reporter=reporter).parse()
        totals["parse"] += (time.perf_counter() - start) * 1000
        if tree is None or reporter.had_error:
            continue

        start = time.perf_counter()
        Printer(source=source, trivia=scanner.trivia, width=100).format(tree)
        totals["print"] += (time.perf_counter() - start) * 1000
    return totals


def _measure_breakdown(files: list[Path], repeat: int) -> None:
    samples: dict[str, list[float]] = {key: [] for key in ("scan", "parse", "print")}
    for _ in range(repeat):
        result = breakdown_pass(files)
        for key, value in result.items():
            samples[key].append(value)
    for key in ("scan", "parse", "print"):
        print(
            f"  {key}: median {statistics.median(samples[key]):.1f} ms, "
            f"min {min(samples[key]):.1f} ms"
        )


def _measure(label: str, call: Callable[[], object], repeat: int) -> tuple[float, float]:
    samples: list[float] = []
    for _ in range(repeat):
        start = time.perf_counter()
        call()
        samples.append((time.perf_counter() - start) * 1000)
    print(f"{label}: median {statistics.median(samples):.1f} ms, min {min(samples):.1f} ms")
    return statistics.median(samples), min(samples)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5, help="amostras por operação")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be positive")

    files = corpus()
    parsed, tokens, statements = parse_pass(files)
    formatted = format_pass(files)
    print(
        f"frontend: {len(files)} files, {parsed} parsed, {formatted} formatted, "
        f"{tokens} tokens, {statements} statements"
    )

    _measure("parse", lambda: parse_pass(files), args.repeat)
    _measure("format", lambda: format_pass(files), args.repeat)
    print("format breakdown (formatter pipeline):")
    _measure_breakdown(files, args.repeat)

    tracemalloc.start()
    parse_pass(files)
    format_pass(files)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"peak (tracemalloc, parse+format): {peak / 1024**2:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
