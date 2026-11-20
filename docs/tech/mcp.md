---
sources:
  - loxia/mcp.py
  - loxia/cli_args.py
  - loxia/cli_commands.py
  - loxia_core/execution/primitives.py
  - loxia_core/execution/interpreter.py
  - tests/test_mcp.py
  - server.json
  - pyproject.toml
---

# MCP server

`loxia-mcp` (or `loxia mcp`) exposes a thin [Model Context Protocol](https://modelcontextprotocol.io/)
server over the agent-friendly CLI. It is **modern-only**: MCP `2026-07-28`, stateless,
newline-delimited JSON-RPC 2.0 on stdio. There is no SDK dependency; the transport is
written by hand, like the LSP. The decision is in [ADR-0112](../adr/0112-mcp-servidor-stdio.md).

## Configure a client

```json
{
  "mcpServers": {
    "loxia": {
      "command": "loxia",
      "args": ["mcp"]
    }
  }
}
```

The `loxia-mcp` console script is equivalent. The process writes only MCP messages to
stdout; diagnostics and internal errors go to stderr.

## Protocol

- Every request must carry `_meta` with
  `io.modelcontextprotocol/protocolVersion: "2026-07-28"` and
  `io.modelcontextprotocol/clientCapabilities: {}`.
- `server/discover` returns `supportedVersions`, `capabilities.tools`, `instructions`,
  `ttlMs`, `cacheScope` and `_meta.serverInfo`.
- `tools/list` is deterministic and cacheable; `tools/call` returns
  `resultType: "complete"`, `content`, `structuredContent`, `isError` and
  `_meta.serverInfo`.
- There is no `initialize` handshake. A version mismatch returns `-32022` with
  `supported: ["2026-07-28"]`; an unknown method returns `-32601`.
- Invalid tool input is a **tool execution error** (`isError: true`), so the model can
  correct it; an unknown tool is a protocol error (`-32602`).

## Tools

| Tool | Input | Output |
| --- | --- | --- |
| `loxia_check` | `source`, optional `file_name`, `timeout_ms` | exact `check --stdin --json` stdout; parsed envelope in `structuredContent.result` |
| `loxia_run` | `source`, optional `args`, `file_name`, `timeout_ms` | exact stdout/stderr/exit code from `run --stdin --json --sandbox -- ...` |
| `loxia_ast` | `source`, optional `file_name` | exact S-expression from `ast --stdin --json` |
| `loxia_spec` | optional `query`, `limit` | section id/page id/free text searched over `loxia/_spec/index.json` (ADR-0111) |
| `loxia_explain` | `code` | code, phase, severity, description and doc URL |
| `loxia_version` | none | Loxia version, MCP protocol and docs index version |

For `loxia_check`, `loxia_run` and `loxia_ast`, `structuredContent` preserves the exact
CLI bytes and the process exit code; the tests compare them with the CLI invocation. The
server never reimplements parsing, checking or diagnostics.

## Sandbox and limits

`loxia_run` always adds `--sandbox`:

- `io.readFile`, `io.writeFile`, `fs.exists`, `fs.listDir` and every `process.*` call
  raise a runtime error (`R1000`);
- stdin/stdout, `io.write`, `io.writeErr` and the pure standard library remain available;
- the language has no network primitives, and `process.*` is denied;
- module imports are resolved by the loader from the project directory, not by the
  program;
- the CLI runs in a subprocess with `cwd` at the server directory, a process group,
  timeout (default 10 s, max 60 s), `RLIMIT_AS` 512 MiB, `RLIMIT_CPU`, `RLIMIT_FSIZE`
  and an 8 MiB cap per stream. `build`/`--emit=exe` are not exposed.

This is a capability profile, not an OS jail: without bwrap/namespaces the host can still
read whatever the loader reads. The residual risk is documented in the ADR.

## Packaging and registry

The server ships in the `loxia` wheel; there is no separate MCP download:

```bash
uvx --from loxia loxia-mcp     # fetch from PyPI and run
pip install loxia               # then use `loxia mcp` or `loxia-mcp`
```

`server.json` at the repository root is the MCP Registry manifest:

- name: `io.github.loxia-lang/loxia`;
- package: PyPI `loxia`, stdio transport;
- runtime: `uvx`, with the positional argument `mcp` (so the client runs `loxia mcp`);
- version must match `pyproject.toml`.

The README carries the matching `<!-- mcp-name: io.github.loxia-lang/loxia -->` marker,
which is what the registry uses to verify PyPI ownership. Publishing is an explicit
release step: the registry preview requires its publisher CLI and the PyPI release must
already exist.

### MCP Inspector

Inspector defaults to the legacy handshake. Loxia is modern-only (`2026-07-28`), so select
**Protocol era: modern** (or pass `--protocol-era modern`) and use `server/discover`, not
`initialize`. For a local checkout, the command is the absolute path to
`.venv/bin/loxia-mcp` with no arguments; `--from loxia loxia-mcp` belongs to `uvx`, not to
`loxia-mcp`.

## What is intentionally out of scope

- HTTP/SSE transport, OAuth and remote hosting.
- Legacy `initialize` handshake / dual-era.
- Concurrent tool calls and cancellation (the server is sequential).
- Prompts/resources; the server exposes tools only.
