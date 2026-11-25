# SPDX-License-Identifier: MIT OR Apache-2.0
"""Guard determinístico do `SourceIndex` no corpus (issue #130).

Não mede tempo (CI-safe): verifica que todo arquivo parseável tem spans únicos,
que toda anotação de tipo é coberta por ao menos um `NodeSpan(kind="type")` e
que o inventário não encolheu em relação ao baseline local.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path

from loxia_core.diagnostics.diagnostic import Span
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.source_index import SourceIndex

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "bench" / "source_index_baseline.json"
CORPUS_GLOBS = ("std/**/*.lx", "tests/cases/**/*.lx", "examples/**/*.lx")


def _corpus() -> list[Path]:
    files: set[Path] = set()
    for pattern in CORPUS_GLOBS:
        files.update(ROOT.glob(pattern))
    return sorted(files)


def _annotations(value: object) -> list[Span]:
    found: list[Span] = []
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            child = getattr(value, item.name)
            if item.name in {"type_span", "return_type_span"} and isinstance(child, Span):
                found.append(child)
            elif item.name == "payload_spans" and isinstance(child, list):
                found.extend(item for item in child if isinstance(item, Span))
            else:
                found.extend(_annotations(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_annotations(child))
    return found


def test_source_index_corpus_inventory() -> None:
    files = _corpus()
    parsed = 0
    spans = 0
    type_spans = 0
    name_spans = 0
    annotations = 0

    for path in files:
        source = path.read_text(encoding="utf-8")
        reporter = ErrorReporter(max_errors=0)
        parser = Parser(Scanner(source, reporter).scan_tokens(), reporter=reporter)
        statements = parser.parse()
        if statements is None or reporter.had_error:
            # Casos de erro de sintaxe não produzem índice (o LSP cai no token).
            continue
        parsed += 1
        index = SourceIndex(statements, source, extra_spans=parser.type_spans)
        keys = [(span.start, span.end, span.file) for span in index.spans]
        assert len(keys) == len(set(keys)), path

        data = source.encode("utf-8")
        for span in index.spans:
            assert 0 <= span.start < span.end <= len(data), (path, span)
            text = index.text_of(span)
            assert text is not None and text.strip() == text and text, (path, span)
            if span.kind in {"type", "name"}:
                assert text.isidentifier(), (path, span, text)

        for annotation in _annotations(statements):
            annotations += 1
            start = annotation.start.offset or 0
            end = annotation.end.offset or 0
            covered = any(
                span.kind == "type" and start <= span.start < span.end <= end
                for span in index.spans
            )
            assert covered, (path, start, end, source.encode("utf-8")[start:end])

        spans += len(index.spans)
        type_spans += sum(1 for span in index.spans if span.kind == "type")
        name_spans += sum(1 for span in index.spans if span.kind == "name")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert len(files) >= baseline["files"]
    assert parsed >= baseline["parsed"]
    assert spans >= baseline["spans"]
    assert type_spans >= baseline["type_spans"]
    assert name_spans >= baseline["name_spans"]
    assert annotations >= 1500
    assert type_spans >= 2000
    assert name_spans >= 2500
