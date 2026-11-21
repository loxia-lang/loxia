# SPDX-License-Identifier: MIT OR Apache-2.0
"""Property-based tests for the test runner's report/protocol boundaries."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from loxia.test_runner import (
    FileRun,
    Location,
    _json_lines,
    _junit,
    _parse_events,
    _parse_tap,
    _payload,
    _tap_text,
)
from loxia.test_runner import (
    TestResult as RunnerResult,
)

PATH = Path("tests/property_test.lx")
TOKEN = "##property-token##"
TEXT = st.text(max_size=60)
STATUS = st.sampled_from(["pass", "fail", "skip"])
KIND = st.sampled_from(["", "assertion", "exception", "hook", "crash", "timeout", "skip"])
LOCATION = st.none() | st.builds(
    Location,
    st.text(max_size=20),
    st.integers(min_value=0, max_value=10**6),
    st.integers(min_value=0, max_value=10**6),
)
RESULT = st.builds(
    RunnerResult,
    file=TEXT,
    name=TEXT,
    status=STATUS,
    message=TEXT,
    kind=KIND,
    location=LOCATION,
    output=TEXT,
)
RUNS = st.lists(
    st.builds(FileRun, path=st.just(PATH), results=st.lists(RESULT, max_size=5)),
    max_size=4,
)


@settings(max_examples=40)
@given(st.lists(TEXT, max_size=30))
def test_tap_parser_accepts_arbitrary_lines(lines: list[str]) -> None:
    results = _parse_tap(PATH, "\n".join(lines), 0)
    assert isinstance(results, list)


@settings(max_examples=50)
@given(TEXT)
def test_tap_text_never_creates_a_directive(value: str) -> None:
    escaped = _tap_text(value)
    assert "\n" not in escaped
    assert "\r" not in escaped
    assert " # SKIP " not in escaped


@settings(max_examples=40)
@given(st.lists(TEXT, max_size=20))
def test_protocol_ignores_user_lines_without_the_token(lines: list[str]) -> None:
    assume(all(not line.startswith(TOKEN) for line in lines))
    results = _parse_events(PATH, "\n".join(lines), 0, TOKEN)
    assert results == []


@settings(max_examples=60)
@given(name=TEXT, message=TEXT, status=STATUS)
def test_protocol_roundtrips_result_fields(name: str, message: str, status: str) -> None:
    start = TOKEN + json.dumps({"event": "start", "name": name})
    result = TOKEN + json.dumps(
        {
            "event": "result",
            "name": name,
            "status": status,
            "kind": "assertion",
            "message": message,
        }
    )
    results = _parse_events(PATH, f"{start}\nuser output\n{result}", 0, TOKEN)

    assert len(results) == 1
    parsed = results[0]
    assert parsed.name == name
    assert parsed.message == message
    assert parsed.status == status
    assert parsed.output == "user output"


@settings(max_examples=50, deadline=None)
@given(RUNS, st.booleans(), st.sampled_from([0, 1]))
def test_json_payload_is_serializable_and_counts_are_consistent(
    runs: list[FileRun], capture: bool, exit_code: int
) -> None:
    payload = _payload(runs, exit_code=exit_code, capture=capture)
    encoded = json.dumps(payload, ensure_ascii=False)
    assert json.loads(encoded) == payload

    tests = payload["tests"]
    summary = payload["summary"]
    assert isinstance(tests, list)
    assert isinstance(summary, dict)
    assert summary["tests"] == len(tests)
    assert summary["files"] == len(runs)
    assert summary["pass"] + summary["fail"] + summary["skip"] == summary["tests"]


@settings(max_examples=40, deadline=None)
@given(RUNS, st.booleans(), st.sampled_from([0, 1]))
def test_json_lines_are_one_object_per_line(
    runs: list[FileRun], capture: bool, exit_code: int
) -> None:
    lines = _json_lines(runs, exit_code=exit_code, capture=capture).splitlines()
    assert lines
    parsed = [json.loads(line) for line in lines]
    assert all(isinstance(line, dict) for line in parsed)
    assert parsed[-1]["type"] == "summary"
    assert parsed[-1]["tests"] == len(parsed) - 1


@settings(max_examples=40, deadline=None)
@given(RUNS)
def test_junit_is_always_well_formed_xml(runs: list[FileRun]) -> None:
    xml = _junit(runs)
    root = ET.fromstring(xml)
    assert root.tag == "testsuites"
    assert root.attrib["tests"] == str(sum(len(run.results) for run in runs))


def test_json_lines_escapes_unicode_line_separators() -> None:
    result = RunnerResult("f", "nome\x85quebrado", "pass", kind="pass")
    lines = _json_lines([FileRun(PATH, [result])], exit_code=0).splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "nome\x85quebrado"
    assert json.loads(lines[1])["type"] == "summary"
