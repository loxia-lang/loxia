# SPDX-License-Identifier: MIT OR Apache-2.0
"""Mede a construção do `SourceIndex` no corpus (issue #130).

Uso:
    uv run python bench/source_index.py
    uv run python bench/source_index.py --repeat 5 --json
    uv run python bench/source_index.py --update

O parse fica fora da medição: o alvo é o custo de indexar (nós + nomes de
declaração + nomes de tipo) e de responder `at()` no caminho de navegação local.
Não roda no CI; o baseline é local e a regra é `<= 2x` o total/mediana.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.source_index import SourceIndex

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = Path(__file__).resolve().parent / "source_index_baseline.json"
CORPUS_GLOBS = ("std/**/*.lx", "tests/cases/**/*.lx", "examples/**/*.lx")
DEFAULT_REPEAT = 3
TOLERANCE = 2.0


@dataclass(frozen=True)
class FileTiming:
    path: str
    spans: int
    type_spans: int
    name_spans: int
    median_ms: float
    queries: int
    at_ms: float


@dataclass(frozen=True)
class Result:
    files: int
    parsed: int
    skipped: int
    spans: int
    type_spans: int
    name_spans: int
    total_ms: float
    median_ms: float
    p95_ms: float
    at_us: float


def corpus() -> list[Path]:
    files: set[Path] = set()
    for pattern in CORPUS_GLOBS:
        files.update(ROOT.glob(pattern))
    return sorted(files)


def measure_file(path: Path, repeat: int) -> FileTiming | None:
    source = path.read_text(encoding="utf-8")
    reporter = ErrorReporter(max_errors=0)
    parser = Parser(Scanner(source, reporter).scan_tokens(), reporter=reporter)
    statements = parser.parse()
    if statements is None or reporter.had_error:
        return None

    timings: list[float] = []
    index: SourceIndex | None = None
    for _ in range(repeat):
        start = time.perf_counter()
        index = SourceIndex(statements, source, extra_spans=parser.type_spans)
        timings.append(time.perf_counter() - start)
    assert index is not None

    queries = [span for span in index.spans if span.kind in {"name", "type"}]
    query_start = time.perf_counter()
    for query in queries:
        # Mesma forma do LSP: offset local restrito ao arquivo do documento.
        index.at(query.start, file=query.file)
    at_ms = (time.perf_counter() - query_start) * 1000

    return FileTiming(
        path=path.relative_to(ROOT).as_posix(),
        spans=len(index.spans),
        type_spans=sum(1 for span in index.spans if span.kind == "type"),
        name_spans=sum(1 for span in index.spans if span.kind == "name"),
        median_ms=statistics.median(timings) * 1000,
        queries=len(queries),
        at_ms=at_ms,
    )


def measure(repeat: int) -> tuple[Result, list[FileTiming]]:
    paths = corpus()
    per_file: list[FileTiming] = []
    for path in paths:
        timing = measure_file(path, repeat)
        if timing is not None:
            per_file.append(timing)

    medians = sorted(item.median_ms for item in per_file)
    p95 = medians[min(len(medians) - 1, int(len(medians) * 0.95))] if medians else 0.0
    queries = sum(item.queries for item in per_file)
    at_ms = sum(item.at_ms for item in per_file)
    result = Result(
        files=len(paths),
        parsed=len(per_file),
        skipped=len(paths) - len(per_file),
        spans=sum(item.spans for item in per_file),
        type_spans=sum(item.type_spans for item in per_file),
        name_spans=sum(item.name_spans for item in per_file),
        total_ms=sum(medians),
        median_ms=statistics.median(medians) if medians else 0.0,
        p95_ms=p95,
        at_us=(at_ms * 1000 / queries) if queries else 0.0,
    )
    return result, per_file


def _rounded(result: Result) -> dict[str, float | int]:
    payload = asdict(result)
    for key in ("total_ms", "median_ms", "p95_ms", "at_us"):
        payload[key] = round(float(payload[key]), 3)
    return payload


def _print(result: Result) -> None:
    print(
        f"corpus: {result.files} files ({result.parsed} parsed, {result.skipped} skipped)",
    )
    print(
        f"spans: {result.spans} (type {result.type_spans}, name {result.name_spans})",
    )
    print(
        "index: "
        f"total {result.total_ms:.2f} ms, "
        f"median {result.median_ms:.3f} ms/file, "
        f"p95 {result.p95_ms:.3f} ms/file",
    )
    print(f"at(): {result.at_us:.3f} us/query")


def _compare(result: Result) -> bool:
    if not BASELINE_PATH.exists():
        print(f"sem baseline em {BASELINE_PATH.relative_to(ROOT).as_posix()}")
        return True
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    ratios = {
        key: float(current) / float(baseline[key])
        for key, current in (
            ("total_ms", result.total_ms),
            ("median_ms", result.median_ms),
        )
        if current > 0 and baseline.get(key)
    }
    for key, ratio in ratios.items():
        print(f"{key}: x{ratio:.2f} o baseline")
    worst = max(ratios.values(), default=1.0)
    if worst > TOLERANCE:
        print(f"regressão: acima de {TOLERANCE:.1f}x o baseline")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update", action="store_true", help="regrava o baseline")
    args = parser.parse_args()

    result, per_file = measure(max(1, args.repeat))
    payload = _rounded(result)
    if args.json:
        print(
            json.dumps(
                {**payload, "per_file": [asdict(item) for item in per_file]},
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        _print(result)

    if args.update:
        BASELINE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"baseline: {BASELINE_PATH.relative_to(ROOT).as_posix()}")
        return 0
    return 0 if _compare(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
