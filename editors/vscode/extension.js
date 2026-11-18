// SPDX-License-Identifier: MIT OR Apache-2.0
"use strict";

// Cliente LSP mínimo da Loxia para VS Code, sem dependências de npm.
// O servidor é um processo (`loxia lsp`, configurável) e o protocolo é JSON-RPC
// sobre stdio com framing Content-Length — o mesmo contrato de `loxia lsp`.

const cp = require("child_process");
const path = require("path");
const vscode = require("vscode");

const DIAGNOSTIC_SEVERITY = {
  1: vscode.DiagnosticSeverity.Error,
  2: vscode.DiagnosticSeverity.Warning,
  3: vscode.DiagnosticSeverity.Information,
  4: vscode.DiagnosticSeverity.Hint,
};

// LSP começa em 1; o enum do VS Code começa em 0.
const SYMBOL_KIND = {
  1: vscode.SymbolKind.File,
  2: vscode.SymbolKind.Module,
  3: vscode.SymbolKind.Namespace,
  4: vscode.SymbolKind.Package,
  5: vscode.SymbolKind.Class,
  6: vscode.SymbolKind.Method,
  7: vscode.SymbolKind.Property,
  8: vscode.SymbolKind.Field,
  9: vscode.SymbolKind.Constructor,
  10: vscode.SymbolKind.Enum,
  11: vscode.SymbolKind.Interface,
  12: vscode.SymbolKind.Function,
  13: vscode.SymbolKind.Variable,
  14: vscode.SymbolKind.Constant,
  15: vscode.SymbolKind.String,
  16: vscode.SymbolKind.Number,
  17: vscode.SymbolKind.Boolean,
  18: vscode.SymbolKind.Array,
  19: vscode.SymbolKind.Object,
  20: vscode.SymbolKind.Key,
  21: vscode.SymbolKind.Null,
  22: vscode.SymbolKind.EnumMember,
  23: vscode.SymbolKind.Struct,
  24: vscode.SymbolKind.Event,
  25: vscode.SymbolKind.Operator,
  26: vscode.SymbolKind.TypeParameter,
};

const COMPLETION_KIND = {
  1: vscode.CompletionItemKind.Text,
  2: vscode.CompletionItemKind.Method,
  3: vscode.CompletionItemKind.Function,
  4: vscode.CompletionItemKind.Constructor,
  5: vscode.CompletionItemKind.Field,
  6: vscode.CompletionItemKind.Variable,
  7: vscode.CompletionItemKind.Class,
  8: vscode.CompletionItemKind.Interface,
  9: vscode.CompletionItemKind.Module,
  10: vscode.CompletionItemKind.Property,
  11: vscode.CompletionItemKind.Unit,
  12: vscode.CompletionItemKind.Value,
  13: vscode.CompletionItemKind.Enum,
  14: vscode.CompletionItemKind.Keyword,
  15: vscode.CompletionItemKind.Snippet,
  16: vscode.CompletionItemKind.Color,
  17: vscode.CompletionItemKind.File,
  18: vscode.CompletionItemKind.Reference,
  19: vscode.CompletionItemKind.Folder,
  20: vscode.CompletionItemKind.EnumMember,
  21: vscode.CompletionItemKind.Constant,
  22: vscode.CompletionItemKind.Struct,
  23: vscode.CompletionItemKind.Event,
  24: vscode.CompletionItemKind.Operator,
  25: vscode.CompletionItemKind.TypeParameter,
};

class LspClient {
  constructor(output) {
    this.output = output;
    this.process = null;
    this.buffer = Buffer.alloc(0);
    this.nextId = 1;
    this.pending = new Map();
    this.ready = Promise.resolve();
    this.stopped = false;
  }

  async start() {
    const config = vscode.workspace.getConfiguration("loxia");
    const explicit = String(config.get("server.path", "")).trim();
    const cwd =
      String(config.get("server.cwd", "")).trim() ||
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const candidates = explicit
      ? [[explicit, config.get("server.args", ["lsp"])]]
      : [
          ["loxia", ["lsp"]],
          ["python3", ["-m", "loxia", "lsp"]],
          ["python", ["-m", "loxia", "lsp"]],
          ["uv", ["run", "python", "-m", "loxia", "lsp"]],
        ];
    let lastError = null;
    for (const [command, args] of candidates) {
      try {
        this.output.appendLine(`[lsp] tentando: ${command} ${args.join(" ")}`);
        await this._spawnProcess(command, args, cwd);
        break;
      } catch (error) {
        lastError = error;
        this.output.appendLine(`[lsp] falhou: ${error.message}`);
        this._stopProcess();
      }
    }
    if (!this.process) {
      const detail = lastError ? ` (${lastError.message})` : "";
      vscode.window.showErrorMessage(
        `Loxia LSP não iniciou${detail}. Configure "loxia.server.path" e ` +
          '"loxia.server.args"; no checkout use python3 + ["-m","loxia","lsp"].'
      );
      this.ready = Promise.reject(lastError || new Error("LSP indisponível"));
      this.ready.catch(() => {});
      return;
    }
    this.ready = this._initialize().catch((error) => {
      this.output.appendLine(`[lsp] initialize falhou: ${error.message}`);
      throw error;
    });
    try {
      await this.ready;
    } catch (error) {
      this.output.appendLine(`[lsp] servidor não respondeu: ${error.message}`);
    }
  }

  _spawnProcess(command, args, cwd) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const child = cp.spawn(command, args, {
        cwd,
        stdio: ["pipe", "pipe", "pipe"],
      });
      this.process = child;
      this.buffer = Buffer.alloc(0);
      child.stdout.on("data", (chunk) => this._onData(chunk));
      child.stderr.on("data", (chunk) =>
        this.output.append(chunk.toString("utf8"))
      );
      child.once("error", (error) => {
        if (!settled) {
          settled = true;
          reject(error);
        }
      });
      child.once("spawn", () => {
        settled = true;
        resolve();
      });
      child.on("exit", (code) => {
        this.output.appendLine(`[lsp] encerrou (${code})`);
        if (!this.stopped) {
          this._failPending(new Error(`LSP encerrou com código ${code}`));
        }
      });
    });
  }

  _initialize() {
    const root = vscode.workspace.workspaceFolders?.[0]?.uri;
    return this.request("initialize", {
      processId: process.pid,
      rootUri: root ? root.toString() : null,
      workspaceFolders:
        vscode.workspace.workspaceFolders?.map((folder) => ({
          uri: folder.uri.toString(),
          name: folder.name,
        })) || null,
      initializationOptions: loxiaSettings(),
      capabilities: {
        workspace: { configuration: false, workspaceFolders: true },
        textDocument: {
          synchronization: { dynamicRegistration: false },
          completion: { completionItem: { snippetSupport: false } },
          hover: { contentFormat: ["markdown", "plaintext"] },
          definition: {},
          rename: { prepareSupport: true },
          codeAction: {
            codeActionLiteralSupport: {
              codeActionKind: { valueSet: ["quickfix"] },
            },
          },
          documentSymbol: { hierarchicalDocumentSymbolSupport: true },
        },
      },
    }).then(() => {
      this.notify("initialized", {});
      for (const document of vscode.workspace.textDocuments) {
        if (document.languageId === "loxia") {
          this.didOpen(document);
        }
      }
    });
  }

  _stopProcess() {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
  }

  didOpen(document) {
    this.notify("textDocument/didOpen", {
      textDocument: {
        uri: document.uri.toString(),
        languageId: "loxia",
        version: document.version,
        text: document.getText(),
      },
    });
  }

  didChange(document) {
    this.notify("textDocument/didChange", {
      textDocument: { uri: document.uri.toString(), version: document.version },
      contentChanges: [{ text: document.getText() }],
    });
  }

  didClose(document) {
    this.notify("textDocument/didClose", {
      textDocument: { uri: document.uri.toString() },
    });
  }

  didSave(document) {
    this.notify("textDocument/didSave", {
      textDocument: { uri: document.uri.toString() },
    });
  }

  request(method, params, timeoutMs = 10000) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`timeout em ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this._send({ jsonrpc: "2.0", id, method, params });
    });
  }

  notify(method, params) {
    this._send({ jsonrpc: "2.0", method, params });
  }

  _send(payload) {
    if (!this.process || !this.process.stdin || !this.process.stdin.writable) {
      return;
    }
    const body = Buffer.from(JSON.stringify(payload), "utf8");
    this.process.stdin.write(`Content-Length: ${body.length}\r\n\r\n`);
    this.process.stdin.write(body);
  }

  _onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      const separator = this.buffer.indexOf("\r\n\r\n");
      if (separator < 0) {
        return;
      }
      const headers = this.buffer.slice(0, separator).toString("ascii");
      const match = /Content-Length:\s*(\d+)/i.exec(headers);
      if (!match) {
        this.buffer = this.buffer.slice(separator + 4);
        continue;
      }
      const length = Number.parseInt(match[1], 10);
      if (this.buffer.length < separator + 4 + length) {
        return;
      }
      const body = this.buffer.slice(
        separator + 4,
        separator + 4 + length
      );
      this.buffer = this.buffer.slice(separator + 4 + length);
      let message;
      try {
        message = JSON.parse(body.toString("utf8"));
      } catch (error) {
        this.output.appendLine(`[lsp] JSON inválido: ${error.message}`);
        continue;
      }
      this._handle(message);
    }
  }

  _handle(message) {
    if (message.id !== undefined && message.method) {
      // O servidor não usa requests do cliente hoje; responde null para não travar.
      this._send({ jsonrpc: "2.0", id: message.id, result: null });
      return;
    }
    if (message.id !== undefined) {
      const pending = this.pending.get(message.id);
      if (!pending) {
        return;
      }
      this.pending.delete(message.id);
      if (pending.timer) {
        clearTimeout(pending.timer);
      }
      if (message.error) {
        pending.reject(new Error(message.error.message || "erro LSP"));
      } else {
        pending.resolve(message.result);
      }
      return;
    }
    if (message.method === "textDocument/publishDiagnostics") {
      this.onDiagnostics?.(message.params);
    } else if (message.method === "window/showMessage") {
      vscode.window.showInformationMessage(message.params?.message || "");
    } else if (message.method === "window/logMessage") {
      this.output.appendLine(message.params?.message || "");
    }
  }

  _failPending(error) {
    for (const { reject, timer } of this.pending.values()) {
      if (timer) {
        clearTimeout(timer);
      }
      reject(error);
    }
    this.pending.clear();
  }

  stop() {
    this.stopped = true;
    this._stopProcess();
  }
}

function loxiaSettings() {
  const config = vscode.workspace.getConfiguration("loxia");
  return {
    inlayHints: { enabled: config.get("inlayHints.enabled", true) },
    completion: { inheritedMembers: config.get("completion.inheritedMembers", true) },
  };
}

function toRange(range) {
  return new vscode.Range(
    range.start.line,
    range.start.character,
    range.end.line,
    range.end.character
  );
}

function toLocation(location) {
  if (location.targetUri) {
    return new vscode.Location(
      vscode.Uri.parse(location.targetUri),
      toRange(location.targetRange)
    );
  }
  return new vscode.Location(
    vscode.Uri.parse(location.uri),
    toRange(location.range)
  );
}

function toTextEdits(edits) {
  return (edits || []).map(
    (edit) => new vscode.TextEdit(toRange(edit.range), edit.newText)
  );
}

function toWorkspaceEdit(edit) {
  if (!edit) {
    return undefined;
  }
  const result = new vscode.WorkspaceEdit();
  const changes = edit.changes || {};
  for (const [uri, edits] of Object.entries(changes)) {
    result.set(vscode.Uri.parse(uri), toTextEdits(edits));
  }
  return result;
}

function toMarkdown(contents) {
  if (!contents) {
    return undefined;
  }
  if (typeof contents === "string") {
    return new vscode.MarkdownString(contents);
  }
  if (Array.isArray(contents)) {
    return new vscode.MarkdownString(contents.map((item) => item.value).join("\n\n"));
  }
  const markdown = new vscode.MarkdownString(contents.value || "");
  markdown.isTrusted = false;
  return markdown;
}

function toDiagnostic(item) {
  const diagnostic = new vscode.Diagnostic(
    toRange(item.range),
    item.message,
    DIAGNOSTIC_SEVERITY[item.severity] || vscode.DiagnosticSeverity.Error
  );
  diagnostic.code = item.code;
  diagnostic.source = item.source || "loxia";
  if (Array.isArray(item.relatedInformation)) {
    diagnostic.relatedInformation = item.relatedInformation.map((related) => {
      const location = toLocation(related.location);
      return new vscode.DiagnosticRelatedInformation(location, related.message);
    });
  }
  return diagnostic;
}

async function activate(context) {
  const output = vscode.window.createOutputChannel("Loxia");
  const diagnostics = vscode.languages.createDiagnosticCollection("loxia");
  const rawDiagnostics = new Map();
  let client = new LspClient(output);

  client.onDiagnostics = (params) => {
    const uri = vscode.Uri.parse(params.uri);
    const items = params.diagnostics || [];
    rawDiagnostics.set(params.uri, items);
    diagnostics.set(uri, items.map(toDiagnostic));
  };

  const send = async (method, params) => {
    try {
      await client.ready;
      return await client.request(method, params);
    } catch (error) {
      output.appendLine(`[lsp] ${method}: ${error.message}`);
      return undefined;
    }
  };
  const documentOf = (document) => ({
    textDocument: { uri: document.uri.toString() },
  });

  context.subscriptions.push(
    output,
    diagnostics,
    vscode.workspace.onDidOpenTextDocument((document) => {
      if (document.languageId === "loxia") {
        client.ready.then(() => client.didOpen(document));
      }
    }),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.languageId === "loxia") {
        client.ready.then(() => client.didChange(event.document));
      }
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (document.languageId === "loxia") {
        client.didSave(document);
      }
    }),
    vscode.workspace.onDidCloseTextDocument((document) => {
      if (document.languageId === "loxia") {
        client.didClose(document);
        rawDiagnostics.delete(document.uri.toString());
      }
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (
        event.affectsConfiguration("loxia.inlayHints") ||
        event.affectsConfiguration("loxia.completion")
      ) {
        client.ready.then(() =>
          client.notify("workspace/didChangeConfiguration", {
            settings: loxiaSettings(),
          })
        );
      }
    }),
    vscode.commands.registerCommand("loxia.restartServer", async () => {
      client.stop();
      diagnostics.clear();
      rawDiagnostics.clear();
      client = new LspClient(output);
      client.onDiagnostics = (params) => {
        const uri = vscode.Uri.parse(params.uri);
        const items = params.diagnostics || [];
        rawDiagnostics.set(params.uri, items);
        diagnostics.set(uri, items.map(toDiagnostic));
      };
      await client.start();
    }),
    vscode.languages.registerDocumentFormattingEditProvider("loxia", {
      provideDocumentFormattingEdits: async (document) => {
        const edits = await send("textDocument/formatting", {
          ...documentOf(document),
          options: { tabSize: 2, insertSpaces: true },
        });
        return toTextEdits(edits);
      },
    }),
    vscode.languages.registerHoverProvider("loxia", {
      provideHover: async (document, position) => {
        const hover = await send("textDocument/hover", {
          ...documentOf(document),
          position,
        });
        if (!hover) {
          return undefined;
        }
        const range = hover.range
          ? toRange(hover.range)
          : new vscode.Range(position, position);
        return new vscode.Hover(toMarkdown(hover.contents), range);
      },
    }),
    vscode.languages.registerDefinitionProvider("loxia", {
      provideDefinition: async (document, position) => {
        const result = await send("textDocument/definition", {
          ...documentOf(document),
          position,
        });
        const items = Array.isArray(result) ? result : result ? [result] : [];
        return items.map(toLocation);
      },
    }),
    vscode.languages.registerCompletionItemProvider("loxia", {
      provideCompletionItems: async (document, position) => {
        const result = await send("textDocument/completion", {
          ...documentOf(document),
          position,
        });
        const items = Array.isArray(result) ? result : result?.items || [];
        const range = new vscode.Range(position, position);
        return items.map((item) => {
          const completion = new vscode.CompletionItem(
            item.label,
            COMPLETION_KIND[item.kind] || vscode.CompletionItemKind.Text
          );
          completion.detail = item.detail;
          completion.documentation = toMarkdown(item.documentation);
          completion.insertText = item.insertText;
          completion.sortText = item.sortText;
          completion.filterText = item.filterText;
          completion.range = range;
          return completion;
        });
      },
    }),
    vscode.languages.registerInlayHintsProvider("loxia", {
      provideInlayHints: async (document, range) => {
        const result = await send("textDocument/inlayHint", {
          ...documentOf(document),
          range: {
            start: { line: range.start.line, character: range.start.character },
            end: { line: range.end.line, character: range.end.character },
          },
        });
        return (result || []).map((item) => {
          const hint = new vscode.InlayHint(
            new vscode.Position(item.position.line, item.position.character),
            item.label,
            item.kind === 1
              ? vscode.InlayHintKind.Type
              : vscode.InlayHintKind.Parameter
          );
          hint.paddingLeft = Boolean(item.paddingLeft);
          hint.paddingRight = Boolean(item.paddingRight);
          return hint;
        });
      },
    }),
    vscode.languages.registerSignatureHelpProvider("loxia", {
      provideSignatureHelp: async (document, position) => {
        const result = await send("textDocument/signatureHelp", {
          ...documentOf(document),
          position,
        });
        if (!result) {
          return undefined;
        }
        const help = new vscode.SignatureHelp();
        help.signatures = (result.signatures || []).map((signature) => {
          const item = new vscode.SignatureInformation(
            signature.label,
            toMarkdown(signature.documentation)
          );
          item.parameters = (signature.parameters || []).map(
            (parameter) =>
              new vscode.ParameterInformation(
                parameter.label,
                toMarkdown(parameter.documentation)
              )
          );
          return item;
        });
        help.activeSignature = result.activeSignature || 0;
        help.activeParameter = result.activeParameter || 0;
        return help;
      },
    }),
    vscode.languages.registerCodeActionsProvider(
      "loxia",
      {
        provideCodeActions: async (document, _range, context) => {
          const uri = document.uri.toString();
          const actions = await send("textDocument/codeAction", {
            ...documentOf(document),
            range: _range,
            context: {
              diagnostics: rawDiagnostics.get(uri) || [],
              only: context.only ? [context.only.value] : undefined,
            },
          });
          return (actions || []).map((action) => {
            const item = new vscode.CodeAction(action.title, action.kind);
            item.isPreferred = Boolean(action.isPreferred);
            item.edit = toWorkspaceEdit(action.edit);
            return item;
          });
        },
      },
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    ),
    vscode.languages.registerRenameProvider("loxia", {
      prepareRename: async (document, position) => {
        const result = await send("textDocument/prepareRename", {
          ...documentOf(document),
          position,
        });
        if (!result) {
          throw new Error("Loxia: renomear só é suportado para símbolos.");
        }
        return { range: toRange(result.range), placeholder: result.placeholder };
      },
      provideRenameEdits: async (document, position, newName) => {
        const result = await send("textDocument/rename", {
          ...documentOf(document),
          position,
          newName,
        });
        return toWorkspaceEdit(result);
      },
    }),
    vscode.languages.registerDocumentSymbolProvider("loxia", {
      provideDocumentSymbols: async (document) => {
        const result = await send("textDocument/documentSymbol", {
          ...documentOf(document),
        });
        return (result || []).map(
          (item) =>
            new vscode.DocumentSymbol(
              item.name,
              item.detail || "",
              SYMBOL_KIND[item.kind] || vscode.SymbolKind.Variable,
              toRange(item.range),
              toRange(item.selectionRange)
            )
        );
      },
    }),
    vscode.languages.registerWorkspaceSymbolProvider({
      provideWorkspaceSymbols: async (query) => {
        const result = await send("workspace/symbol", { query });
        return (result || []).map(
          (item) =>
            new vscode.SymbolInformation(
              item.name,
              SYMBOL_KIND[item.kind] || vscode.SymbolKind.Variable,
              item.containerName || "",
              toLocation(item.location)
            )
        );
      },
    })
  );

  await client.start();

  context.subscriptions.push({
    dispose: () => {
      client.stop();
      diagnostics.dispose();
    },
  });
}

function deactivate() {}

module.exports = { activate, deactivate };
