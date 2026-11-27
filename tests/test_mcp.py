# SPDX-License-Identifier: MIT OR Apache-2.0
"""MCP stdio transcript and CLI-parity tests (ADR-0112)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from loxia import __version__
from loxia import mcp as mcp_module
from loxia.docs_index import DocsIndexError
from loxia.formatter.edits import EditPosition, TextEdit, apply_edits

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}


def start(root: Path = ROOT) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(root / "main.py"), "mcp"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def send(process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    process.stdin.flush()


def receive(process: subprocess.Popen[str]) -> dict[str, Any]:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line, "MCP server closed stdout without a response"
    return cast(dict[str, Any], json.loads(line))


def request(
    process: subprocess.Popen[str],
    request_id: int,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    meta: dict[str, Any] | None = None,
    include_meta: bool = True,
) -> dict[str, Any]:
    body = dict(params or {})
    if include_meta:
        body["_meta"] = meta if meta is not None else META
    send(process, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": body})
    return receive(process)


def call(
    process: subprocess.Popen[str],
    request_id: int,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return request(process, request_id, "tools/call", {"name": name, "arguments": arguments})


def closed(process: subprocess.Popen[str]) -> None:
    assert process.stdin is not None
    process.stdin.close()
    assert process.wait(timeout=10) == 0


def run_cli(*args: str, source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=ROOT,
        input=source,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def edits_from_payload(payload: dict[str, Any]) -> tuple[TextEdit, ...]:
    return tuple(
        TextEdit(
            start=EditPosition(**cast(dict[str, int], item["start"])),
            end=EditPosition(**cast(dict[str, int], item["end"])),
            new_text=cast(str, item["newText"]),
        )
        for item in cast(list[dict[str, Any]], payload["edits"])
    )


def test_discover_and_tools_list_are_modern_and_deterministic() -> None:
    process = start()
    try:
        discovered = request(process, 1, "server/discover")
        result = discovered["result"]
        assert result["resultType"] == "complete"
        assert result["supportedVersions"] == ["2026-07-28"]
        assert result["capabilities"] == {"tools": {}}
        assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "loxia-mcp"

        listed = request(process, 2, "tools/list")["result"]
        names = [tool["name"] for tool in listed["tools"]]
        assert names == [
            "loxia_check",
            "loxia_run",
            "loxia_ast",
            "loxia_format",
            "loxia_spec",
            "loxia_explain",
            "loxia_version",
        ]
        assert listed["ttlMs"] == 3_600_000
        assert listed["cacheScope"] == "public"
        assert all(tool["inputSchema"]["type"] == "object" for tool in listed["tools"])
        formatter = next(tool for tool in listed["tools"] if tool["name"] == "loxia_format")
        assert formatter["annotations"]["readOnlyHint"] is True
        assert formatter["inputSchema"]["oneOf"] == [
            {"required": ["source"]},
            {"required": ["path"]},
        ]
        assert "timeout_ms" in cast(dict[str, Any], formatter["inputSchema"]["properties"])
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_check_result_is_byte_identical_to_cli() -> None:
    source = 'var x: Int = "a"\n'
    process = start()
    try:
        result = call(process, 1, "loxia_check", {"source": source})["result"]
        assert result["isError"] is True
        assert (
            result["content"][0]["text"]
            == run_cli("check", "--stdin", "--json", source=source).stdout
        )
        assert result["structuredContent"]["exit_code"] == 65
        assert result["structuredContent"]["result"]["diagnostics"][0]["code"] == "E3001"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_run_result_and_args_are_byte_identical_to_cli() -> None:
    source = "print(args())\n"
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_run",
            {"source": source, "args": ["alpha", "beta"], "timeout_ms": 10_000},
        )["result"]
        cli = run_cli(
            "run",
            "--stdin",
            "--json",
            "--sandbox",
            "--timeout",
            "10000",
            "--",
            "alpha",
            "beta",
            source=source,
        )
        assert result["isError"] is False
        assert result["structuredContent"]["stdout"] == cli.stdout
        assert result["structuredContent"]["stderr"] == cli.stderr
        assert result["structuredContent"]["exit_code"] == cli.returncode
        assert result["content"][0]["text"] == cli.stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_ast_result_is_byte_identical_to_cli() -> None:
    source = "print(1 + 2)\n"
    process = start()
    try:
        result = call(process, 1, "loxia_ast", {"source": source})["result"]
        cli = run_cli("ast", "--stdin", "--json", source=source)
        assert result["structuredContent"]["stdout"] == cli.stdout
        assert result["content"][0]["text"] == cli.stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_run_sandbox_denies_filesystem_and_process() -> None:
    process = start()
    try:
        for request_id, source, message in (
            (
                1,
                'io.writeFile("mcp-denied.txt", "x")\n',
                "io.writeFile() is not available in sandbox mode.",
            ),
            (2, 'io.readFile("README.md")\n', "io.readFile() is not available in sandbox mode."),
            (3, 'process.spawn(["true"])\n', "process.spawn() is not available in sandbox mode."),
        ):
            result = call(process, request_id, "loxia_run", {"source": source})["result"]
            assert result["isError"] is True
            assert result["structuredContent"]["exit_code"] == 70
            assert message in result["structuredContent"]["stderr"]
        assert not (ROOT / "mcp-denied.txt").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_run_timeout_returns_exit_124() -> None:
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_run",
            {"source": "while (true) {}\n", "timeout_ms": 100},
        )["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["exit_code"] == 124
        assert result["structuredContent"]["timed_out"] is True
        assert "C0001" in result["structuredContent"]["stderr"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_modern_requires_meta_and_supported_version() -> None:
    process = start()
    try:
        missing = request(process, 1, "tools/list", include_meta=False)
        assert missing["error"]["code"] == -32602

        old = request(
            process,
            2,
            "server/discover",
            meta={
                "io.modelcontextprotocol/protocolVersion": "2025-11-25",
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        )
        assert old["error"]["code"] == -32022
        assert old["error"]["data"]["supported"] == ["2026-07-28"]

        legacy = request(process, 3, "initialize", include_meta=False)
        assert legacy["error"]["code"] in {-32601, -32602}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_unknown_tool_is_a_protocol_error_and_bad_input_is_a_tool_error() -> None:
    process = start()
    try:
        unknown = call(process, 1, "nope", {})
        assert unknown["error"]["code"] == -32602

        invalid = call(process, 2, "loxia_check", {"source": 42})["result"]
        assert invalid["isError"] is True
        assert "source must be a string" in invalid["content"][0]["text"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_returns_text_and_edits_with_comments() -> None:
    source = "val xs=[1, # one\n 2]\n"
    process = start()
    try:
        result = call(process, 1, "loxia_format", {"source": source})["result"]
        assert result["isError"] is False
        data = result["structuredContent"]
        assert data["changed"] is True
        assert "# one" in data["formatted"]
        assert data["file"] == "<stdin>"
        edits = edits_from_payload(cast(dict[str, Any], data))
        assert apply_edits(source, edits) == data["formatted"]
        assert result["content"][0]["text"] == data["formatted"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_normalizes_crlf_and_uses_file_name() -> None:
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_format",
            {"source": "val x=1\r\n", "file_name": "demo.lx"},
        )["result"]
        assert result["isError"] is False
        data = result["structuredContent"]
        assert data["file"] == "demo.lx"
        assert data["formatted"] == "val x = 1\n"
        assert data["changed"] is True
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_path_is_read_only_and_diff_is_optional(tmp_path: Path) -> None:
    script = tmp_path / "a.lx"
    source = "fn f( a:Int ){return a;}\n"
    script.write_text(source, encoding="utf-8")
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_format",
            {"path": str(script), "diff": True, "check": True},
        )["result"]
        assert result["isError"] is False
        data = result["structuredContent"]
        assert data["file"].endswith("a.lx")
        assert not data["file"].startswith("/")
        assert data["check"] is True
        assert data["formatted"] == "fn f(a: Int) {\n  return a\n}\n"
        assert "a.lx" in data["diff"]
        assert len(result["content"]) == 2
        assert script.read_text(encoding="utf-8") == source
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_range_limits_edits_and_reports_effective_range() -> None:
    source = "val a=1\n\n\n\nval b=2\n"
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_format",
            {"source": source, "range": {"start_line": 1, "end_line": 1}},
        )["result"]
        assert result["isError"] is False
        data = result["structuredContent"]
        assert data["range"] == {"start_line": 1, "end_line": 1}
        assert data["formatted"] == "val a = 1\n\n\n\nval b=2\n"
        assert "val b=2" in data["formatted"]
        assert (
            apply_edits(source, edits_from_payload(cast(dict[str, Any], data))) == data["formatted"]
        )

        expanded = call(
            process,
            2,
            "loxia_format",
            {"source": "val xs=[\n1,\n2\n]\n", "lines": "2-2"},
        )["result"]
        assert expanded["isError"] is False
        expanded_data = expanded["structuredContent"]
        assert expanded_data["range"] == {"start_line": 1, "end_line": 4}
        assert expanded_data["formatted"] == "val xs = [1, 2]\n"

        commented = call(
            process,
            3,
            "loxia_format",
            {"source": "val xs=[1, # keep\n 2]\n", "range": {"start_line": 1, "end_line": 1}},
        )["result"]
        assert commented["isError"] is False
        commented_data = commented["structuredContent"]
        assert "# keep" in commented_data["formatted"]
        assert (
            apply_edits(
                "val xs=[1, # keep\n 2]\n",
                edits_from_payload(cast(dict[str, Any], commented_data)),
            )
            == commented_data["formatted"]
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_rejects_invalid_ranges_and_inputs() -> None:
    process = start()
    cases: tuple[dict[str, Any], ...] = (
        {"source": "val x = 1\n", "range": {"start_line": 2, "end_line": 1}},
        {"source": "val x = 1\n", "range": {"start_line": 1, "end_line": 9}},
        {"source": "val x = 1\n", "range": {"start_line": 2, "end_line": 2}},
        {
            "source": "val x = 1\n",
            "range": {"start_line": 1, "end_line": 1},
            "lines": "1-1",
        },
        {"source": "val x = 1\n", "path": "a.lx"},
        {},
        {"source": "val x = 1\n", "max_width": 10},
        {"path": "missing.lx"},
        {"path": "a.txt"},
    )
    try:
        for request_id, arguments in enumerate(cases, 1):
            result = call(process, request_id, "loxia_format", arguments)["result"]
            assert result["isError"] is True
            assert result["content"][0]["text"]

        invalid = call(process, 20, "loxia_format", {"source": "val =\n"})["result"]
        assert invalid["isError"] is True
        assert invalid["structuredContent"]["exit_code"] == 65
        assert invalid["structuredContent"]["result"]["diagnostics"][0]["code"] == "E1001"
        assert "E1001" in invalid["content"][0]["text"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_honors_max_width() -> None:
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_format",
            {"source": "fn f(a: Int, bbbb: Int) -> Int { return a }\n", "max_width": 20},
        )["result"]
        assert result["isError"] is False
        assert "fn f(\n" in result["structuredContent"]["formatted"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_range_includes_eof_hunk_without_final_newline() -> None:
    source = "val a = 1\nval xs=[\n1,\n2\n]"
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_format",
            {"source": source, "range": {"start_line": 5, "end_line": 5}},
        )["result"]
        assert result["isError"] is False
        data = result["structuredContent"]
        assert data["changed"] is True
        assert data["edits"]
        assert data["range"] == {"start_line": 2, "end_line": 5}
        assert (
            apply_edits(source, edits_from_payload(cast(dict[str, Any], data))) == data["formatted"]
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_rejects_path_guards(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.lx"
    invalid.write_bytes(b"val x = \xff\n")
    too_large = tmp_path / "large.lx"
    too_large.write_bytes(b"x" * (1_048_576 + 1))
    valid = tmp_path / "ok.lx"
    valid.write_text("val x = 1\n", encoding="utf-8")
    process = start()
    try:
        for request_id, arguments in enumerate(
            (
                {"path": str(invalid)},
                {"path": str(too_large)},
                {"path": str(valid), "file_name": "ok.lx"},
            ),
            1,
        ):
            result = call(process, request_id, "loxia_format", arguments)["result"]
            assert result["isError"] is True
            assert result["content"][0]["text"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_label_disambiguates_paths_outside_cwd(tmp_path: Path) -> None:
    first = tmp_path / "one" / "same.lx"
    second = tmp_path / "two" / "same.lx"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("val a=1\n", encoding="utf-8")
    second.write_text("val b=2\n", encoding="utf-8")
    process = start()
    try:
        one = call(process, 1, "loxia_format", {"path": str(first)})["result"]
        two = call(process, 2, "loxia_format", {"path": str(second)})["result"]
        assert one["structuredContent"]["file"] != two["structuredContent"]["file"]
        assert one["structuredContent"]["file"].endswith("one/same.lx")
        assert two["structuredContent"]["file"].endswith("two/same.lx")
        assert not one["structuredContent"]["file"].startswith("/")
        assert not two["structuredContent"]["file"].startswith("/")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_format_reports_terminated_process(monkeypatch: Any) -> None:
    def fake(*args: object, **kwargs: object) -> mcp_module.CliResult:
        return mcp_module.CliResult(
            stdout="", stderr="", exit_code=-9, timed_out=False, truncated=False
        )

    monkeypatch.setattr(mcp_module, "_run_cli", fake)
    result = mcp_module.tool_format({"source": "val x=1\n", "timeout_ms": 1})

    assert result.is_error is True
    assert "did not finish" in result.content[0]
    assert result.structured["error"] == "formatter did not finish within 1 ms."


def test_run_stderr_json_is_not_parsed_as_diagnostics() -> None:
    process = start()
    try:
        result = call(
            process,
            1,
            "loxia_run",
            {"source": 'io.writeErr("{\\"x\\":1}")\n'},
        )["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["exit_code"] == 0
        assert "result" not in result["structuredContent"]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_spec_explain_and_version() -> None:
    process = start()
    try:
        spec = call(
            process,
            1,
            "loxia_spec",
            {"query": "spec/syntax#optional-semicolon"},
        )["result"]
        assert spec["structuredContent"]["results"][0]["id"] == "spec/syntax#optional-semicolon"
        assert (
            "https://loxia-lang.github.io/loxia/reference/syntax/#optional-semicolon"
            in spec["content"][0]["text"]
        )

        explained = call(process, 2, "loxia_explain", {"code": "E2001"})["result"]
        assert explained["structuredContent"]["code"] == "E2001"
        assert explained["structuredContent"]["phase"] == "resolver"

        cli = run_cli("explain", "E2001", "--json", source="")
        assert cli.returncode == 0
        cli_payload = cast(dict[str, Any], json.loads(cli.stdout))
        for key in ("code", "phase", "severity", "description", "doc"):
            assert explained["structuredContent"][key] == cli_payload[key]

        version = call(process, 3, "loxia_version", {})["result"]
        assert version["structuredContent"]["protocol_version"] == "2026-07-28"
        assert version["structuredContent"]["tools"][0] == "loxia_check"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _copy_checkout(destination: Path) -> Path:
    """Minimal checkout a test can upgrade while the server keeps running."""
    destination.mkdir()
    shutil.copy2(ROOT / "main.py", destination / "main.py")
    for package in ("loxia", "loxia_core"):
        shutil.copytree(
            ROOT / package,
            destination / package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    return destination


def _upgrade_index(root: Path, *, code: str, description: str, version: str) -> None:
    """Rewrite the on-disk index as if `make docs-sync` ran under the live server."""
    path = root / "loxia" / "_spec" / "index.json"
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    payload["loxia_version"] = version
    catalog = cast(list[dict[str, str]], payload.setdefault("codes", []))
    catalog.append({"code": code, "phase": "checker", "description": description})
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_explain_resolves_codes_added_after_the_server_starts(tmp_path: Path) -> None:
    """Issue #218: the long-lived server must not be stuck with the enum it imported."""
    root = _copy_checkout(tmp_path / "checkout")
    process = start(root)
    try:
        before = call(process, 1, "loxia_explain", {"code": "E9500"})["result"]
        assert before["isError"] is True

        _upgrade_index(root, code="E9500", description="simulated upgrade", version="9.9.9")

        after = call(process, 2, "loxia_explain", {"code": "E9500"})["result"]
        assert after["isError"] is False
        assert after["structuredContent"] == {
            "code": "E9500",
            "phase": "checker",
            "severity": "error",
            "description": "simulated upgrade",
            "doc": "docs/spec/erros.md",
            "doc_url": "https://loxia-lang.github.io/loxia/reference/errors/",
        }

        version = call(process, 3, "loxia_version", {})["result"]
        assert version["structuredContent"]["docs_version"] == "9.9.9"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_explain_unknown_code_reports_server_version_and_restart_hint() -> None:
    process = start()
    try:
        result = call(process, 1, "loxia_explain", {"code": "E9999"})["result"]
        assert result["isError"] is True
        message = result["content"][0]["text"]
        assert "unknown diagnostic code: E9999" in message
        assert f"server loxia {__version__}" in message
        assert "restart the MCP server after upgrading loxia" in message
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_explain_falls_back_to_the_enum_without_a_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_index() -> None:
        raise DocsIndexError("packaged documentation index is missing")

    monkeypatch.setattr(mcp_module, "load_index", no_index)
    result = mcp_module.tool_explain({"code": "E2001"})
    assert result.structured["code"] == "E2001"
    assert result.structured["phase"] == "resolver"
    assert result.structured["description"] == "duplicate variable in scope"


def test_notifications_are_ignored_and_eof_exits_cleanly() -> None:
    process = start()
    try:
        send(
            process,
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 99},
            },
        )
        discovered = request(process, 1, "server/discover")
        assert discovered["result"]["supportedVersions"] == ["2026-07-28"]
    finally:
        closed(process)
