# ADR-0109 — Cliente de editor em repo próprio e grammar como asset de release

> **Implementação (2026-11-18):** o cliente VS Code saiu de `editors/vscode/` para
> [`loxia-lang/loxia-vscode`](https://github.com/loxia-lang/loxia-vscode) (TypeScript +
> esbuild, testes unitários e smoke de integração, CI, VSIX, Marketplace/Open VSX). A
> grammar gerada passou para `editors/grammar/` (`loxia.tmLanguage.json`, `loxia.mjs`,
> `loxia.ts`); `make grammar` continua sendo a fonte e
> `uv run python editors/build_grammar.py --check` o gate. O release do main ganhou os
> jobs `--check` + `--assets dist-grammar` e anexa os três arquivos + `SHA256SUMS` ao
> GitHub Release. O repo novo pina a release em `grammar.lock.json` (versão + SHA-256) e
> sincroniza com `npm run grammar:sync -- --version X`; o CI valida o hash offline. O
> servidor LSP continua no main (ADR-0090); a extensão o consome como `loxia lsp`.

- **Status:** accepted
- **Data:** 2026-11-18
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (LSP no repo principal),
  [ADR-0078](0078-nome-loxia-extensao-lx.md) (nome/`.lx`),
  [ADR-0102](0102-ingles-na-vitrine-e-docs-pt-br.md) (vitrine em inglês),
  [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md) (distribuição),
  issue [#5](https://github.com/loxia-lang/loxia/issues/5), `docs/roadmap.md` (M9)
- **Implementação:** `editors/build_grammar.py` (`--assets`), `editors/grammar/`,
  `.github/workflows/release.yml`, `loxia-lang/loxia-vscode` (cliente, testes, CI,
  `grammar.lock.json`, `docs/publishing.md`) e `tests/test_editor_grammar.py`.

## Contexto

O cliente VS Code nasceu dentro de `editors/vscode/`: ~700 linhas de JavaScript sem
dependências npm, falando JSON-RPC stdio com `loxia lsp` e cobrindo diagnostics, hover,
definition, completion, signatureHelp, inlay hints, formatting, code actions, rename e
symbols. Ele funciona, mas não tem testes, empacotamento, CI, changelog, licença própria
nem publicação. A grammar TextMate é **gerada** por `editors/build_grammar.py` a partir do
front-end e é usada também pelo Shiki (site) e pelo viewer do harness.

O issue [#5](https://github.com/loxia-lang/loxia/issues/5) pede três coisas que o repo
principal não deve carregar sozinho: publicar o cliente, anexar a grammar ao release e
fazer o repo de editor consumir o asset em vez de uma cópia manual. O ADR-0090 já decidiu
que o **servidor** LSP fica no repo principal e listou gatilhos para separar o cliente
(dependência própria, cadência de release dirigida por editores ou segundo mantenedor).
O issue cita o ADR-0092 por engano — esse é o do formatter; a referência correta é o
ADR-0090.

Duas forças puxam em direções opostas:

- o cliente precisa de uma cadência de release e de ferramentas de editor (VSIX,
  Marketplace, Open VSX, Node) que não pertencem ao interpretador;
- a grammar precisa continuar nascendo das fontes da linguagem, senão highlighting e
  keywords divergem do parser.

## Decisão

### 1. Split total, sem submódulo nem subtree

O cliente vive em **`loxia-lang/loxia-vscode`**. O repo principal **não** contém mais
`editors/vscode/`, **não** aponta submódulo/subtree para o novo repo e **não** depende
dele para build, test ou release. O caminho inverso também vale: o repo novo não importa
código do main; ele consome um **asset versionado**.

O servidor LSP continua no main (ADR-0090). A extensão o chama como `loxia lsp`; o
contrato entre os dois é o protocolo LSP + a CLI, não um pacote compartilhado. Isso
preserva a regra do ADR-0090 (diagnóstico e spans versionam com o compilador) e evita
duplicar o compilador no repo de editor.

### 2. A grammar é um asset de release do main

`editors/grammar/` é a localização canônica dos artefatos **gerados**:

| Arquivo | Consumidor |
| --- | --- |
| `loxia.tmLanguage.json` | VS Code, Sublime Text, TextMate |
| `loxia.mjs` | Shiki (site e harness viewer) |
| `loxia.ts` | viewer do DeepSeek Harness |

`make grammar` (`build_grammar.py --write`) regenera os três; `--check` falha se algum
estiver defasado e roda em `make check`. O novo modo `--assets DIR` grava os três arquivos
e um `SHA256SUMS` determinístico, usado pelo release.

Todo release `vX.Y.Z` do main anexa `loxia.tmLanguage.json`, `loxia.mjs`, `loxia.ts` e
`SHA256SUMS` ao GitHub Release. O arquivo versionado no repo **não** é a fonte para outros
editores: a fonte é o asset, para que o consumidor saiba exatamente de qual release veio.

### 3. O repo de editor pina o asset, não copia à mão

`grammar.lock.json` no repo novo registra:

```json
{
  "languageVersion": "1.1.0",
  "source": "https://github.com/loxia-lang/loxia/releases/download/v1.1.0/loxia.tmLanguage.json",
  "sha256": "…"
}
```

`npm run grammar:sync -- --version X.Y.Z` baixa o asset, verifica o checksum contra o
`SHA256SUMS` do release e grava o JSON + o lock. `npm run grammar:check` recomputa o hash e
valida a estrutura/manifesto **offline**; ambos rodam no CI. O VSIX embute a grammar: não
há download em runtime e a instalação funciona offline. O workflow manual
`sync-grammar.yml` abre o PR de atualização.

A versão da extensão e a versão da linguagem são independentes: o lock diz de qual
release a grammar veio; `package.json` versiona a extensão.

### 4. Distribuição: Marketplace + Open VSX, servidor externo

O primeiro release publicado é **1.1.0** (a versão que o cliente já tinha no main). A
partir daí a extensão segue semver próprio. Publicação:

- VS Code Marketplace (`publisher: loxia-lang`, extensão `loxia-lang.loxia`);
- Open VSX (mesmo namespace);
- VSIX anexado ao GitHub Release do repo novo;
- workflows `ci.yml`, `release.yml` e `sync-grammar.yml`; PATs em `VSCE_PAT`/`OVSX_PAT`.

O servidor **não** é embutido no VSIX na v1. A extensão detecta `loxia`,
`python3 -m loxia`, `python -m loxia` (e `py -3 -m loxia` no Windows), com
`loxia.cli.path`/`loxia.cli.args` como override e mensagem acionável quando não encontra.
Os gatilhos para embutir/baixar um binário do servidor são: usuários sem Python/`uv`,
instalação offline real ou um segundo mantenedor de editores. Até lá, o custo de um VSIX
por plataforma e de um runtime Python empacotado não se paga.

### 5. UX do cliente: play, modos e settings por feature

- Play em `editor/title/run` usa `loxia.run.mode`: `interpreted` (default), `compiled`
  ou `ask` (QuickPick). `compiled` roda `loxia build --emit=exe` em `.loxia/bin/` e
  executa o binário; falhas comuns (`llvmlite`, `libgc`, `cc`, backend gap) viram uma
  mensagem com a correção.
- Comandos explícitos no submenu Run/explorer/paleta: Run (Interpreted), Run (Compiled),
  Run with Arguments, Build, Check, REPL, Restart Server, Show Output.
- Settings por feature (`loxia.features.*`): diagnostics, hover, definition, completion
  (incluindo herdados), signatureHelp, inlayHints, formatting, codeActions, rename,
  documentSymbols, workspaceSymbols; `loxia.lsp.enabled=false` deixa só highlighting.
- `loxia.run.*` cobre args, cwd, debug interpretado, save e outputDir/maxHeap do compilado;
  `loxia.statusBar.enabled` e `loxia.lsp.trace` fecham o ciclo de observabilidade.
- Workspace não confiável: Run/Build/REPL recusam; highlighting e o servidor read-only
  continuam. `loxia.cli.path`/`loxia.cli.args` são restritos em
  `untrustedWorkspaces.restrictedConfigurations`.
- A extensão é `extensionKind: workspace` (precisa do CLI e dos arquivos no lado remoto) e
  declara `virtualWorkspaces`/`untrustedWorkspaces` como `limited`.

### 6. O que fica no main

- `editors/build_grammar.py` e `editors/grammar/` (geração, `--check`, `--assets`);
- `tests/test_editor_grammar.py` (drift, scopes, `//` não é comentário, assets de release);
- `editors/README.md` (geração, asset, Shiki/DSH, limitações; link para o repo novo);
- `make grammar`/`make grammar-assets`;
- release com os assets.

Saem do main: `editors/vscode/` e o teste que verificava o `package.json` da extensão. O
teste equivalente passou para o repo novo (`test/unit/manifest.test.ts`).

## Consequências

### Positivas

- Cada repo tem uma responsabilidade: o main gera a linguagem e a grammar; o repo novo
  entrega o editor. Releases de editor não arrastam PyPI, e releases da linguagem não
  dependem de Node.
- A grammar continua nascendo das fontes (sem cópia divergente) e o consumidor sabe
  exatamente qual release/checksum está usando.
- O cliente ganha testes, CI, VSIX, changelog, licença e publicação sem inflar o repo do
  compilador.
- O servidor continua versionando com o compilador (ADR-0090), sem duplicação.

### Negativas / custos

- Dois repositórios, dois CIs, dois runbooks e um passo explícito de sync de grammar.
- O repo novo precisa de Node 22+ para desenvolver (o bundle roda em Node 18 do VS Code
  1.85).
- A instalação ainda exige o CLI `loxia`; um usuário sem Python/`uv` não tem LSP nem Run.
- O asset de grammar no release do main precisa ser gerado/validado no release; um release
  sem os assets quebra o `grammar:sync` do repo novo (há teste no main).
- O cliente e o servidor podem ficar defasados: é intencional e visível no lock; a
  compatibilidade é o protocolo LSP, não a versão.

### Neutras

- O split não muda a linguagem, I1–I4 nem o formato do diagnóstico.
- A grammar TextMate continua sendo highlighting, não análise semântica.
- O repo novo pode publicar patches sem release da linguagem (e vice-versa).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter o cliente no main e só publicar de lá | O main ganha Node/VSIX/Marketplace e uma cadência que não é a do compilador; foi o gatilho do ADR-0090. |
| Submódulo/subtree `editors/vscode` → repo novo | Acopla o checkout do main ao repo de editor e não resolve a posse da cadência; o asset já dá o contrato. |
| Copiar a grammar à mão no repo novo | Divergência silenciosa; o gerador e o teste de drift não alcançam a cópia. |
| Baixar a grammar em runtime | Instalação offline quebra, I3/segurança pioram e o VSIX deixa de ser reproduzível. |
| Embutir um servidor Python/binário no VSIX | VSIX por plataforma, runtime empacotado e CI pesado antes de existir demanda; gatilhos acima. |
| Publicar só no Marketplace | Open VSX é o canal de VSCodium/Codium e de vários usuários Linux; o custo é um secret e um passo. |
| Um repo `loxia-editors` com VS Code + Sublime + Shiki | O cliente VS Code é o produto com release próprio; a grammar já é o asset compartilhado. Shiki/DSH continuam no main. |

## Como verificar

- `make grammar` + `make check` no main: `tests/test_editor_grammar.py` cobre drift,
  keywords/scopes, `//`, includes, Shiki e o asset de release.
- `make grammar-assets` e `uv run python editors/build_grammar.py --assets /tmp/g`:
  três arquivos + `SHA256SUMS` reproduzíveis.
- Release do main: o job anexa `loxia.tmLanguage.json`, `loxia.mjs`, `loxia.ts` e
  `SHA256SUMS` (teste `test_release_anexa_os_assets_da_grammar`).
- `npm run verify` e `npm run test:integration` no repo novo; `npm run package` gera o
  VSIX e `npx vsce ls --tree` mostra o allowlist.
- `npm run grammar:sync -- --version X` + `npm run grammar:check`: checksum do release
  confere e o CI falha se o JSON for editado à mão.
- Critério para revisitar: usuários sem Python/`uv`, necessidade de servidor embutido,
  segundo mantenedor de editores ou uma feature de editor que exija código compartilhado
  com o compilador.

## Referências

- issue [#5](https://github.com/loxia-lang/loxia/issues/5) — publicar cliente + asset.
- [`../roadmap.md`](../roadmap.md) — M9 (ecossistema).
- [`../../editors/README.md`](../../editors/README.md) — geração, assets e limitações.
- [`../../.github/workflows/release.yml`](../../.github/workflows/release.yml) — assets.
- `loxia-vscode/docs/publishing.md` — runbook de Marketplace/Open VSX.
