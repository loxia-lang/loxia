# Loxia VS Code extension

Syntax highlighting + an **LSP client** for `.lx`. The client is JSON-RPC over stdio with
no npm dependencies: it starts `loxia lsp` (or the configured command) and exposes
diagnostics, hover, definition, completion with scope/imports/modules/inheritance,
signatureHelp, inlay hints (inferred types), formatting, code actions, rename and symbols.

## Run from the checkout

```bash
code --extensionDevelopmentPath="$PWD/editors/vscode" .
```

With the CLI installed (`loxia` on `PATH`), the default works. Without installing it, the
client tries the following automatically, in order: `loxia lsp`,
`python3 -m loxia lsp`, `python -m loxia lsp` and `uv run python -m loxia lsp` (with the
workspace at the repo root). To pin a command:

```json
{
  "loxia.server.path": "python3",
  "loxia.server.args": ["-m", "loxia", "lsp"]
}
```

The `loxia.restartServer` command reloads the process after changing the configuration. If no
command starts, the message shows the error and the **Loxia** channel records each
attempt; an empty `loxia.server.path` means autodetection. The default `cwd` is the
workspace root; open the main repo (or adjust `loxia.server.cwd`).

## Feature settings

- `loxia.inlayHints.enabled` (default `true`): inferred-type hints for `val`/`var`/fields
  without an annotation and for `for` bindings. `editor.inlayHints.enabled` still applies
  on top.
- `loxia.completion.inheritedMembers` (default `true`): include superclass and interface
  members in completion.

Both are sent to the server on `initialize` and on configuration changes; other LSP
clients can send the same `initializationOptions`/`workspace/didChangeConfiguration`.

## Publish (when the repo is split)

The client is self-contained: `extension.js`, `package.json`, `language-configuration.json`,
`syntaxes/` and this README. The grammar is **generated** by `make grammar` in the main repo
and copied at release time; do not edit the JSON by hand. The server is not bundled — the
extension only points at `loxia lsp`, so the editors repo can be versioned separately
without duplicating the compiler.
