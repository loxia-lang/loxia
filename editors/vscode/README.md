# Extensão VS Code da Loxia

Destaque de sintaxe + **cliente LSP** para `.lx`. O cliente é JSON-RPC sobre stdio, sem
dependências de npm: ele inicia `loxia lsp` (ou o comando configurado) e expõe
diagnósticos, hover, definição, completion com escopo/imports/módulos, signatureHelp,
formatação, code actions, rename e símbolos.

## Rodar do checkout

```bash
code --extensionDevelopmentPath="$PWD/editors/vscode" .
```

Com o CLI instalado (`loxia` no `PATH`), o padrão já funciona. Sem instalar, o cliente
tenta automaticamente, nesta ordem: `loxia lsp`, `python3 -m loxia lsp`,
`python -m loxia lsp` e `uv run python -m loxia lsp` (com o workspace na raiz do repo).
Para fixar um comando:

```json
{
  "loxia.server.path": "python3",
  "loxia.server.args": ["-m", "loxia", "lsp"]
}
```

`Loxia: reiniciar servidor LSP` recarrega o processo depois de mudar a configuração.
Se nenhum comando iniciar, a mensagem mostra o erro e o canal **Loxia** registra cada
 tentativa; `loxia.server.path` vazio significa autodetecção. O `cwd` padrão é a raiz do
workspace; abra o repo principal (ou ajuste `loxia.server.cwd`).

## Publicar (quando separar o repo)

O cliente é autocontido: `extension.js`, `package.json`, `language-configuration.json`,
`syntaxes/` e este README. A grammar é **gerada** por `make grammar` no repo principal e
copiada no release; não edite o JSON à mão. O servidor não é embutido — a extensão só
aponta para `loxia lsp`, então o repo de editores pode versionar separado sem duplicar o
compilador.
