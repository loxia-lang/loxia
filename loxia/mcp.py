# SPDX-License-Identifier: MIT OR Apache-2.0
"""Thin MCP server over the agent-friendly CLI (ADR-0112).

The transport is newline-delimited JSON-RPC 2.0 on stdio, pinned to MCP
``2026-07-28`` (stateless; every request carries ``_meta``). Tools call the CLI in a
subprocess and return its bytes unchanged in ``structuredContent``; the server never
reimplements diagnostics or the language.

The ``run`` tool adds ``--sandbox``: the child CLI denies filesystem and process
primitives, while the parent applies a timeout, a process group and resource limits.
This is a capability profile, not an OS jail; see the ADR for the residual risks.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from loxia import __version__
from loxia.docs_index import DocsIndexError, Section, load_index
from loxia.formatter.edits import (
    EditPosition,
    TextEdit,
    apply_edits,
    edits_json,
    unified_diff,
)
from loxia_core.diagnostics.codes import CODE_DESCRIPTIONS, CODE_PHASE, Code

PROTOCOL_VERSION = "2026-07-28"
SERVER_NAME = "loxia-mcp"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

DEFAULT_TIMEOUT_MS = 10_000
MAX_TIMEOUT_MS = 60_000
MAX_SOURCE_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_ARGS = 64
MAX_ARG_BYTES = 4_096
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_SPEC_TEXT = 20_000
CACHE_TTL_MS = 3_600_000
SANDBOX_AS_BYTES = 512 * 1024 * 1024


class ToolError(Exception):
    """Invalid tool input: returned as a tool execution error, never a crash."""


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True)
class CliResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    truncated: bool


@dataclass(frozen=True)
class ToolResult:
    content: tuple[str, ...]
    structured: dict[str, object]
    is_error: bool = False


def _mapping(value: object, what: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ToolError(f"{what} must be an object.")
    return cast(Mapping[str, object], value)


def _string(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise ToolError(f"{what} must be a string.")
    return value


def _integer(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolError(f"{what} must be an integer.")
    return value


def _string_list(value: object, what: str) -> list[str]:
    if not isinstance(value, list):
        raise ToolError(f"{what} must be an array of strings.")
    items = cast(Sequence[object], value)
    if len(items) > MAX_ARGS:
        raise ToolError(f"{what} has too many items (max {MAX_ARGS}).")
    result: list[str] = []
    for item in items:
        text = _string(item, what)
        if "\x00" in text:
            raise ToolError(f"{what} cannot contain NUL bytes.")
        try:
            size = len(text.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ToolError(f"{what} must be valid UTF-8.") from error
        if size > MAX_ARG_BYTES:
            raise ToolError(f"{what} item is too long.")
        result.append(text)
    return result


def _source(args: Mapping[str, object]) -> str:
    source = _string(args.get("source"), "source")
    try:
        size = len(source.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ToolError("source must be valid UTF-8.") from error
    if size > MAX_SOURCE_BYTES:
        raise ToolError(f"source is too large ({size} > {MAX_SOURCE_BYTES} bytes).")
    return source


def _file_name(args: Mapping[str, object]) -> str:
    value = args.get("file_name", "<stdin>")
    name = _string(value, "file_name")
    if not name or len(name) > 255 or "\x00" in name:
        raise ToolError("file_name must be a short non-empty string.")
    return name


def _boolean(value: object, what: str) -> bool:
    if not isinstance(value, bool):
        raise ToolError(f"{what} must be a boolean.")
    return value


def _normalize_source(text: str) -> str:
    """Mesma normalização do `fmt --stdin` (contrato de spans do texto normalizado)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _format_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        try:
            return Path(os.path.relpath(path.resolve(), Path.cwd().resolve())).as_posix()
        except ValueError:
            return path.name


def _format_path(args: Mapping[str, object]) -> tuple[str, str]:
    raw = _string(args.get("path"), "path")
    if args.get("file_name") is not None:
        raise ToolError("file_name is only valid with source.")
    if "\x00" in raw:
        raise ToolError("path cannot contain NUL bytes.")
    path = Path(raw)
    if path.suffix != ".lx":
        raise ToolError("path must point to a .lx file.")
    try:
        if not path.is_file():
            raise ToolError(f"path is not a file: {raw}")
        size = path.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise ToolError(f"path is too large ({size} > {MAX_SOURCE_BYTES} bytes).")
        data = path.read_bytes()
    except OSError as error:
        raise ToolError(f"could not read path: {error.strerror or error}") from error
    if len(data) > MAX_SOURCE_BYTES:
        raise ToolError(f"path is too large ({len(data)} > {MAX_SOURCE_BYTES} bytes).")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ToolError("path must be valid UTF-8.") from error
    return _normalize_source(text), _format_label(path)


def _format_source(args: Mapping[str, object]) -> tuple[str, str]:
    source_value = args.get("source")
    path_value = args.get("path")
    if (source_value is None) == (path_value is None):
        raise ToolError("provide exactly one of source or path.")
    if source_value is not None:
        return _normalize_source(_source(args)), _file_name(args)
    return _format_path(args)


def _format_width(args: Mapping[str, object]) -> int:
    width = _integer(args.get("max_width", 100), "max_width")
    if not 20 <= width <= 1000:
        raise ToolError("max_width must be between 20 and 1000.")
    return width


def _line_count(source: str) -> int:
    pieces = source.split("\n")
    lines = [piece + "\n" for piece in pieces[:-1]]
    if pieces[-1]:
        lines.append(pieces[-1])
    return max(1, len(lines))


def _format_range(args: Mapping[str, object], line_count: int) -> tuple[int, int] | None:
    range_value = args.get("range")
    lines_value = args.get("lines")
    if range_value is not None and lines_value is not None:
        raise ToolError("range and lines cannot be combined.")
    if range_value is not None:
        mapping = _mapping(range_value, "range")
        if set(mapping) != {"start_line", "end_line"}:
            raise ToolError("range requires start_line and end_line.")
        start = _integer(mapping["start_line"], "range.start_line")
        end = _integer(mapping["end_line"], "range.end_line")
    elif lines_value is not None:
        text = _string(lines_value, "lines").strip()
        match = re.fullmatch(r"([0-9]+)-([0-9]+)", text)
        if match is None:
            raise ToolError("lines must look like 'start-end'.")
        start = int(match.group(1))
        end = int(match.group(2))
    else:
        return None
    if start < 1 or end < start or end > line_count:
        raise ToolError(f"range must be 1..{line_count} with start_line <= end_line.")
    return start, end


def _format_edits(payload: Mapping[str, object]) -> tuple[TextEdit, ...]:
    raw = payload.get("edits")
    if not isinstance(raw, list):
        raise ToolError("formatter returned an invalid edits payload.")
    edits: list[TextEdit] = []
    for item in cast(Sequence[object], raw):
        mapping = _mapping(item, "edit")
        start = _mapping(mapping.get("start"), "edit.start")
        end = _mapping(mapping.get("end"), "edit.end")
        edits.append(
            TextEdit(
                start=EditPosition(
                    line=_integer(start.get("line"), "edit.start.line"),
                    column=_integer(start.get("column"), "edit.start.column"),
                    offset=_integer(start.get("offset"), "edit.start.offset"),
                ),
                end=EditPosition(
                    line=_integer(end.get("line"), "edit.end.line"),
                    column=_integer(end.get("column"), "edit.end.column"),
                    offset=_integer(end.get("offset"), "edit.end.offset"),
                ),
                new_text=_string(mapping.get("newText"), "edit.newText"),
            )
        )
    return tuple(edits)


def _edit_last_line(edit: TextEdit) -> int:
    if edit.end.column > 1:
        return max(edit.start.line, edit.end.line)
    return max(edit.start.line, edit.end.line - 1)


def _select_range_edits(
    edits: Sequence[TextEdit], start: int, end: int, line_count: int
) -> tuple[tuple[TextEdit, ...], int, int]:
    selected = tuple(
        edit for edit in edits if edit.start.line <= end and _edit_last_line(edit) >= start
    )
    if not selected:
        return (), start, end
    effective_start = min(start, *(edit.start.line for edit in selected))
    effective_end = min(line_count, max(end, *(_edit_last_line(edit) for edit in selected)))
    return selected, effective_start, effective_end


def _timeout(args: Mapping[str, object]) -> int:
    value = args.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    timeout = _integer(value, "timeout_ms")
    if not 1 <= timeout <= MAX_TIMEOUT_MS:
        raise ToolError(f"timeout_ms must be between 1 and {MAX_TIMEOUT_MS}.")
    return timeout


def _limit(args: Mapping[str, object]) -> int:
    value = args.get("limit", 5)
    limit = _integer(value, "limit")
    if not 1 <= limit <= 10:
        raise ToolError("limit must be between 1 and 10.")
    return limit


def _tool_schema(
    properties: Mapping[str, object], required: Sequence[str] = ()
) -> dict[str, object]:
    schema: dict[str, object] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


_SOURCE = {"type": "string", "description": "Loxia source code (UTF-8, at most 1 MiB)."}
_FILE_NAME = {
    "type": "string",
    "description": "Display name and module root hint (default `<stdin>`).",
}
_TIMEOUT = {
    "type": "integer",
    "minimum": 1,
    "maximum": MAX_TIMEOUT_MS,
    "description": "Wall-clock limit in milliseconds (default 10000, max 60000).",
}
_READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
_RUN_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

_FORMAT_PATH = {
    "type": "string",
    "description": "Read-only path to a .lx file (absolute or relative, at most 1 MiB).",
}
_FORMAT_RANGE = {
    "type": "object",
    "properties": {
        "start_line": {"type": "integer", "minimum": 1},
        "end_line": {"type": "integer", "minimum": 1},
    },
    "required": ["start_line", "end_line"],
    "additionalProperties": False,
}
_FORMAT_LINES = {
    "type": "string",
    "pattern": "^[0-9]+-[0-9]+$",
    "description": "Line range as 'start-end' (1-based inclusive).",
}
_FORMAT_CHECK = {
    "type": "boolean",
    "description": "Dry-run hint; loxia_format never writes.",
}
_FORMAT_DIFF = {
    "type": "boolean",
    "description": "Include the unified diff in structuredContent and as a second content block.",
}
_FORMAT_MAX_WIDTH = {
    "type": "integer",
    "minimum": 20,
    "maximum": 1000,
    "default": 100,
    "description": "Maximum code width in columns (20..1000, default 100).",
}


def _format_schema() -> dict[str, object]:
    schema = _tool_schema(
        {
            "source": _SOURCE,
            "path": _FORMAT_PATH,
            "file_name": _FILE_NAME,
            "range": _FORMAT_RANGE,
            "lines": _FORMAT_LINES,
            "check": _FORMAT_CHECK,
            "diff": _FORMAT_DIFF,
            "max_width": _FORMAT_MAX_WIDTH,
            "timeout_ms": _TIMEOUT,
        }
    )
    schema["oneOf"] = [{"required": ["source"]}, {"required": ["path"]}]
    return schema


TOOLS: tuple[dict[str, object], ...] = (
    {
        "name": "loxia_check",
        "title": "Check Loxia source",
        "description": "Type-check a Loxia program without executing it; returns the CLI JSON diagnostics.",
        "inputSchema": _tool_schema(
            {"source": _SOURCE, "file_name": _FILE_NAME, "timeout_ms": _TIMEOUT},
            ("source",),
        ),
        "annotations": _READ_ONLY,
    },
    {
        "name": "loxia_run",
        "title": "Run Loxia source",
        "description": (
            "Execute a Loxia program in the sandbox profile: no filesystem or process "
            "primitives, with timeout and resource limits."
        ),
        "inputSchema": _tool_schema(
            {
                "source": _SOURCE,
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Program arguments exposed through args().",
                },
                "file_name": _FILE_NAME,
                "timeout_ms": _TIMEOUT,
            },
            ("source",),
        ),
        "annotations": _RUN_ANNOTATIONS,
    },
    {
        "name": "loxia_ast",
        "title": "Loxia AST",
        "description": "Parse Loxia source and return the S-expression AST; does not execute.",
        "inputSchema": _tool_schema(
            {"source": _SOURCE, "file_name": _FILE_NAME},
            ("source",),
        ),
        "annotations": _READ_ONLY,
    },
    {
        "name": "loxia_format",
        "title": "Format Loxia source",
        "description": (
            "Format source or a read-only .lx path and return the formatted text plus "
            "exact TextEdit[] spans; optional 1-based line range, dry-run check and diff. "
            "Never writes a file."
        ),
        "inputSchema": _format_schema(),
        "annotations": _READ_ONLY,
    },
    {
        "name": "loxia_spec",
        "title": "Loxia specification",
        "description": (
            "Search the packaged spec and standard library index. Pass a section id "
            "(`spec/syntax#optional-semicolon`), a page id (`spec/syntax`), or free text."
        ),
        "inputSchema": _tool_schema(
            {
                "query": {
                    "type": "string",
                    "description": "Section id, page id or search terms; empty lists pages.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Maximum number of sections (default 5).",
                },
            }
        ),
        "annotations": _READ_ONLY,
    },
    {
        "name": "loxia_explain",
        "title": "Explain a diagnostic",
        "description": "Explain a stable diagnostic code such as E2001 or W1001.",
        "inputSchema": _tool_schema(
            {"code": {"type": "string", "description": "Diagnostic code, e.g. E2001."}},
            ("code",),
        ),
        "annotations": _READ_ONLY,
    },
    {
        "name": "loxia_version",
        "title": "Loxia version",
        "description": "Return the Loxia version, MCP protocol version and docs index version.",
        "inputSchema": _tool_schema({}),
        "annotations": _READ_ONLY,
    },
)

TOOL_NAMES = tuple(cast(str, tool["name"]) for tool in TOOLS)


def _cli_argv(
    command: str,
    *,
    file_name: str,
    timeout_ms: int,
    sandbox: bool,
    script_args: Sequence[str],
    extra_args: Sequence[str] = (),
) -> list[str]:
    argv = [
        sys.executable,
        "-m",
        "loxia",
        command,
        "--stdin",
        "--file-name",
        file_name,
        "--json",
        *extra_args,
    ]
    if command in {"run", "check"}:
        argv.extend(["--timeout", str(timeout_ms)])
    if command == "run":
        if sandbox:
            argv.append("--sandbox")
        argv.append("--")
        argv.extend(script_args)
    return argv


def _pythonpath() -> str:
    return str(Path(__file__).resolve().parent.parent)


def _child_env() -> dict[str, str]:
    temp = tempfile.gettempdir()
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": os.environ.get("HOME", temp),
        "TMPDIR": os.environ.get("TMPDIR", temp),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": _pythonpath(),
        "NO_COLOR": "1",
    }
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        env["TEMP"] = temp
        env["TMP"] = temp
    return env


def _limits(timeout_ms: int) -> Callable[[], None] | None:
    if os.name != "posix":
        return None
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return None

    cpu = max(1, math.ceil(timeout_ms / 1000) + 1)
    limits = (
        (resource.RLIMIT_CPU, (cpu, cpu)),
        (resource.RLIMIT_AS, (SANDBOX_AS_BYTES, SANDBOX_AS_BYTES)),
        (resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES + 1, MAX_OUTPUT_BYTES + 1)),
        (resource.RLIMIT_CORE, (0, 0)),
        (resource.RLIMIT_NOFILE, (64, 64)),
    )

    def apply() -> None:
        for key, value in limits:
            with contextlib.suppress(OSError, ValueError):
                resource.setrlimit(key, value)

    return apply


def _kill(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name != "posix":
        with contextlib.suppress(OSError):
            process.kill()
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        with contextlib.suppress(OSError):
            process.kill()


def _read_capped(path: Path) -> tuple[str, bool]:
    with path.open("rb") as file:
        data = file.read(MAX_OUTPUT_BYTES + 1)
    truncated = len(data) > MAX_OUTPUT_BYTES
    if truncated:
        data = data[:MAX_OUTPUT_BYTES]
    return data.decode("utf-8", errors="replace"), truncated


def _run_cli(
    command: str,
    source: str,
    *,
    file_name: str,
    timeout_ms: int,
    sandbox: bool = False,
    script_args: Sequence[str] = (),
    extra_args: Sequence[str] = (),
) -> CliResult:
    argv = _cli_argv(
        command,
        file_name=file_name,
        timeout_ms=timeout_ms,
        sandbox=sandbox,
        script_args=script_args,
        extra_args=extra_args,
    )
    with tempfile.TemporaryDirectory(prefix="loxia-mcp-") as directory:
        out_path = Path(directory) / "stdout"
        err_path = Path(directory) / "stderr"
        with out_path.open("wb") as stdout, err_path.open("wb") as stderr:
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=Path.cwd(),
                    env=_child_env(),
                    stdin=subprocess.PIPE,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=os.name == "posix",
                    preexec_fn=_limits(timeout_ms),
                )
            except OSError as error:
                raise ToolError(f"could not start loxia: {error}") from error

            timed_out = False
            try:
                process.communicate(
                    input=source.encode("utf-8"),
                    timeout=timeout_ms / 1000 + 2,
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill(process)
                process.communicate()
        stdout_text, stdout_truncated = _read_capped(out_path)
        stderr_text, stderr_truncated = _read_capped(err_path)

    exit_code = 124 if timed_out else cast(int, process.returncode)
    return CliResult(
        stdout=stdout_text,
        stderr=stderr_text,
        exit_code=exit_code,
        timed_out=timed_out,
        truncated=stdout_truncated or stderr_truncated,
    )


def _structured_cli(
    result: CliResult, command: str, *, parse_stderr: bool = False
) -> dict[str, object]:
    payload: dict[str, object] = {
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out or result.exit_code == 124,
        "truncated": result.truncated,
    }
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        if not parse_stderr:
            return payload
        try:
            envelope = json.loads(result.stderr)
        except json.JSONDecodeError:
            return payload
    if isinstance(envelope, dict):
        payload["result"] = cast(dict[str, object], envelope)
    return payload


def _content_for(result: CliResult, command: str) -> tuple[str, ...]:
    primary = result.stdout or result.stderr
    if primary:
        return (primary,)
    return ("",)


def tool_check(args: Mapping[str, object]) -> ToolResult:
    source = _source(args)
    result = _run_cli(
        "check",
        source,
        file_name=_file_name(args),
        timeout_ms=_timeout(args),
    )
    return ToolResult(
        content=_content_for(result, "check"),
        structured=_structured_cli(result, "check"),
        is_error=result.exit_code != 0,
    )


def tool_run(args: Mapping[str, object]) -> ToolResult:
    source = _source(args)
    script_args = _string_list(args.get("args", []), "args")
    result = _run_cli(
        "run",
        source,
        file_name=_file_name(args),
        timeout_ms=_timeout(args),
        sandbox=True,
        script_args=script_args,
    )
    content = tuple(part for part in (result.stdout, result.stderr) if part)
    return ToolResult(
        content=content or ("",),
        structured=_structured_cli(result, "run"),
        is_error=result.exit_code != 0,
    )


def tool_ast(args: Mapping[str, object]) -> ToolResult:
    source = _source(args)
    result = _run_cli(
        "ast",
        source,
        file_name=_file_name(args),
        timeout_ms=DEFAULT_TIMEOUT_MS,
    )
    return ToolResult(
        content=_content_for(result, "ast"),
        structured=_structured_cli(result, "ast"),
        is_error=result.exit_code != 0,
    )


def tool_format(args: Mapping[str, object]) -> ToolResult:
    source, label = _format_source(args)
    width = _format_width(args)
    timeout_ms = _timeout(args)
    check = _boolean(args.get("check", False), "check")
    want_diff = _boolean(args.get("diff", False), "diff")
    line_count = _line_count(source)
    span = _format_range(args, line_count)

    result = _run_cli(
        "fmt",
        source,
        file_name=label,
        timeout_ms=timeout_ms,
        extra_args=("--check", "--edits=json", "--max-width", str(width)),
    )
    if result.exit_code not in (0, 1):
        error_structured = _structured_cli(result, "fmt", parse_stderr=True)
        if result.exit_code < 0 or result.exit_code == 124 or result.timed_out:
            message = f"formatter did not finish within {timeout_ms} ms."
            error_structured["error"] = message
            return ToolResult(content=(message,), structured=error_structured, is_error=True)
        return ToolResult(
            content=_content_for(result, "fmt"),
            structured=error_structured,
            is_error=True,
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ToolError("formatter returned invalid JSON.") from error
    if not isinstance(payload, dict):
        raise ToolError("formatter returned an invalid payload.")
    text = _string(payload.get("text"), "formatter text")
    edits = _format_edits(payload)

    structured: dict[str, object] = {
        "file": label,
        "changed": False,
        "max_width": width,
        "formatted": text,
        "edits": edits_json(edits),
        "check": check,
    }
    formatted = text
    if span is not None:
        selected, effective_start, effective_end = _select_range_edits(
            edits, span[0], span[1], line_count
        )
        formatted = apply_edits(source, selected)
        structured["edits"] = edits_json(selected)
        structured["range"] = {
            "start_line": effective_start,
            "end_line": effective_end,
        }
    elif apply_edits(source, edits) != text:
        raise ToolError("formatter returned inconsistent edits.")

    structured["formatted"] = formatted
    structured["changed"] = formatted != source

    content: tuple[str, ...] = (formatted,)
    if want_diff:
        diff_text = unified_diff(label, source, formatted)
        structured["diff"] = diff_text
        content = (formatted, diff_text)
    return ToolResult(content=content, structured=structured)


def _section_payload(section: Section) -> dict[str, object]:
    return {
        "id": section.id,
        "title": section.title,
        "level": section.level,
        "url": section.url,
        "text": section.text[:4_000],
    }


def _render_sections(query: str, sections: Sequence[Section]) -> str:
    if not sections:
        return f'No documentation sections matched "{query}".'
    blocks: list[str] = []
    for section in sections:
        blocks.append(f"{section.url}\n\n{section.text.strip()}")
    text = "\n\n".join(blocks)
    if len(text) > MAX_SPEC_TEXT:
        text = text[:MAX_SPEC_TEXT].rstrip() + "\n\n[truncated]"
    return text


def tool_spec(args: Mapping[str, object]) -> ToolResult:
    raw_query = args.get("query", "")
    query = _string(raw_query, "query").strip()
    if len(query) > 512:
        raise ToolError("query is too long (max 512 characters).")
    limit = _limit(args)
    try:
        index = load_index()
    except DocsIndexError as error:
        raise ToolError(str(error)) from error

    if not query:
        pages = index.pages
        text = "\n".join(
            f"- [{page.title}]({page.url})" + (f": {page.summary}" if page.summary else "")
            for page in pages
        )
        return ToolResult(
            content=(f"# Loxia documentation\n\n{text}",),
            structured={
                "query": "",
                "pages": [
                    {
                        "id": page.id,
                        "title": page.title,
                        "url": page.url,
                        "summary": page.summary,
                    }
                    for page in pages
                ],
            },
        )

    sections = index.search(query, limit=limit)
    return ToolResult(
        content=(_render_sections(query, sections),),
        structured={
            "query": query,
            "results": [_section_payload(section) for section in sections],
        },
    )


def tool_explain(args: Mapping[str, object]) -> ToolResult:
    raw_code = _string(args.get("code"), "code").strip().upper()
    try:
        index = load_index()
    except DocsIndexError:
        index = None
    entry = index.code(raw_code) if index is not None else None
    if entry is None:
        # The index may predate the catalog (or not know this code yet): fall back to
        # the enum this process imported, which still covers an un-synced workspace.
        try:
            code = Code(raw_code)
        except ValueError:
            docs_version = index.loxia_version if index is not None else "missing"
            raise ToolError(
                f"unknown diagnostic code: {raw_code} "
                f"(server loxia {__version__}, docs index {docs_version}); "
                "restart the MCP server after upgrading loxia"
            ) from None
        code_value = code.value
        phase = CODE_PHASE[code].value
        description = CODE_DESCRIPTIONS[code]
    else:
        code_value = entry.code
        phase = entry.phase
        description = entry.description
    severity = "warning" if code_value.startswith("W") else "error"
    doc_url = "https://loxia-lang.github.io/loxia/reference/errors/"
    structured: dict[str, object] = {
        "code": code_value,
        "phase": phase,
        "severity": severity,
        "description": description,
        "doc": "docs/spec/erros.md",
        "doc_url": doc_url,
    }
    text = f"{code_value} ({phase}): {description}\nSee {doc_url}"
    return ToolResult(content=(text,), structured=structured)


def tool_version(args: Mapping[str, object]) -> ToolResult:
    try:
        index = load_index()
        pages = [
            {
                "id": page.id,
                "title": page.title,
                "url": page.url,
            }
            for page in index.pages
        ]
        docs_version = index.loxia_version
    except DocsIndexError:
        pages = []
        docs_version = "missing"
    structured: dict[str, object] = {
        "version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "docs_version": docs_version,
        "docs_pages": len(pages),
        "tools": list(TOOL_NAMES),
    }
    text = (
        f"loxia {__version__}\n"
        f"MCP protocol {PROTOCOL_VERSION}\n"
        f"documentation index {docs_version} ({len(pages)} pages)"
    )
    return ToolResult(content=(text,), structured=structured)


TOOL_HANDLERS: dict[str, Callable[[Mapping[str, object]], ToolResult]] = {
    "loxia_check": tool_check,
    "loxia_run": tool_run,
    "loxia_ast": tool_ast,
    "loxia_format": tool_format,
    "loxia_spec": tool_spec,
    "loxia_explain": tool_explain,
    "loxia_version": tool_version,
}


def _server_info() -> dict[str, object]:
    return {"name": SERVER_NAME, "version": __version__}


def _result_meta() -> dict[str, object]:
    return {META_SERVER_INFO: _server_info()}


class Server:
    """Stateless MCP 2026-07-28 dispatcher; one request in, at most one response out."""

    def handle(self, payload: object) -> dict[str, object] | None:
        if not isinstance(payload, dict):
            return self._error(None, -32600, "Invalid Request: expected an object.")
        request = cast(Mapping[str, object], payload)
        if request.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "Invalid Request: jsonrpc must be '2.0'.")
        method = request.get("method")
        if not isinstance(method, str):
            return self._error(None, -32600, "Invalid Request: missing method.")
        if "id" not in request:
            self._notification(method)
            return None
        request_id = request.get("id")
        if (
            request_id is None
            or isinstance(request_id, bool)
            or not isinstance(request_id, (str, int))
        ):
            return self._error(None, -32600, "Invalid Request: id must be a string or integer.")
        try:
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise RpcError(-32602, "Invalid params: expected an object.")
            result = self._dispatch(method, cast(Mapping[str, object], params))
        except RpcError as error:
            return self._error(request_id, error.code, error.message, error.data)
        except Exception as error:
            print(f"loxia-mcp: internal error: {error}", file=sys.stderr, flush=True)
            return self._error(request_id, -32603, "Internal error.")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _notification(self, method: str) -> None:
        # Cancellation/progress are request-scoped in the protocol; this server is
        # sequential and has no background work to cancel. Ignore all notifications.
        _ = method

    def _validate_meta(self, params: Mapping[str, object]) -> None:
        meta = params.get("_meta")
        if not isinstance(meta, dict):
            raise RpcError(
                -32602,
                "Invalid params: _meta with protocolVersion and clientCapabilities is required.",
            )
        meta_map = cast(Mapping[str, object], meta)
        requested = meta_map.get(META_VERSION)
        if requested != PROTOCOL_VERSION:
            raise RpcError(
                -32022,
                "Unsupported protocol version",
                {
                    "supported": [PROTOCOL_VERSION],
                    "requested": requested,
                },
            )
        capabilities = meta_map.get(META_CAPABILITIES)
        if not isinstance(capabilities, dict):
            raise RpcError(
                -32602,
                "Invalid params: _meta requires io.modelcontextprotocol/clientCapabilities.",
            )

    def _dispatch(self, method: str, params: Mapping[str, object]) -> dict[str, object]:
        if method == "initialize":
            raise RpcError(
                -32601,
                "Unknown method 'initialize'; this server speaks MCP 2026-07-28; "
                "use server/discover.",
                {"supported": [PROTOCOL_VERSION]},
            )
        self._validate_meta(params)
        if method == "server/discover":
            return {
                "resultType": "complete",
                "supportedVersions": [PROTOCOL_VERSION],
                "capabilities": {"tools": {}},
                "_meta": _result_meta(),
                "instructions": (
                    "Loxia tools. loxia_check, loxia_ast and loxia_format are read-only; "
                    "loxia_format returns formatted text and TextEdit[] and never writes; "
                    "loxia_run executes in the sandbox profile (no filesystem or process "
                    "primitives, 10s default timeout, 60s maximum); loxia_spec searches the "
                    "packaged language reference."
                ),
                "ttlMs": CACHE_TTL_MS,
                "cacheScope": "public",
            }
        if method == "tools/list":
            return {
                "resultType": "complete",
                "tools": list(TOOLS),
                "ttlMs": CACHE_TTL_MS,
                "cacheScope": "public",
                "_meta": _result_meta(),
            }
        if method == "tools/call":
            return self._call(params)
        raise RpcError(-32601, f"Unknown method: {method}")

    def _call(self, params: Mapping[str, object]) -> dict[str, object]:
        name = params.get("name")
        if not isinstance(name, str):
            raise RpcError(-32602, "Invalid params: tools/call requires a tool name.")
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            raise RpcError(-32602, f"Unknown tool: {name}")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise RpcError(-32602, "Invalid params: arguments must be an object.")
        try:
            result = handler(cast(Mapping[str, object], arguments))
        except ToolError as error:
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": str(error)}],
                "isError": True,
                "_meta": _result_meta(),
            }
        content = [{"type": "text", "text": text} for text in result.content]
        return {
            "resultType": "complete",
            "content": content,
            "structuredContent": result.structured,
            "isError": result.is_error,
            "_meta": _result_meta(),
        }

    @staticmethod
    def _error(
        request_id: object,
        code: int,
        message: str,
        data: object | None = None,
    ) -> dict[str, object]:
        error: dict[str, object] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _write(payload: dict[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(text.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    server = Server()
    try:
        for raw in sys.stdin.buffer:
            if not raw.strip():
                continue
            if len(raw) > MAX_LINE_BYTES:
                _write(Server._error(None, -32700, "Parse error: message too large."))
                continue
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                _write(Server._error(None, -32700, "Parse error."))
                continue
            response = server.handle(payload)
            if response is not None:
                _write(response)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
