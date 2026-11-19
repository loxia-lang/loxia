# ADR-0090 — LSP: hospedagem, escopo e fases

> **Atualização (2026-11-19):** o framing `Content-Length`, os envelopes JSON-RPC e o
> `DocumentStore` viraram três módulos de stdlib em Lox puro — `std.framing`,
> `std.jsonrpc` e `std.documents` ([ADR-0113](0113-protocolo-stdio-jsonrpc-framing-documents.md)).
> Eles são primitivas de protocolo, não um servidor LSP em Loxia: a decisão de hospedagem
> abaixo continua valendo, e `std/lsp` só nasce com política de servidor (capabilities,
> diagnóstico, `positionEncoding`).

> **Implementação (2026-11-16; ampliada em 2026-11-18):** LSP-0 em Python
> (`loxia lsp`, JSON-RPC stdio à mão): `initialize`/`shutdown`/`exit`, full sync,
> `publishDiagnostics` e `documentSymbol`. LSP-1 básico: `SymbolIndex`/`Resolver.references`
> e `hover`/`definition` para variáveis, funções, classes, campos, métodos, enums e
> variantes. LSP-2: completion (global, por membro e **herdada** de superclasse/interface),
> signatureHelp (inclusive funções, métodos e construtores **importados/herdados**),
> documentFormatting, semanticTokens/full, `codeAction` (quickfixes de `data.fixes`),
> `rename`/`prepareRename` (locais/parâmetros e top-level cross-file **semântico**),
> `workspace/symbol`, **`inlayHint`** de tipos inferidos, completion com
> escopo/imports/módulos, settings `loxia.inlayHints.enabled`/
> `loxia.completion.inheritedMembers`, teste de paridade com `check --error-format=json`
> e um `SourceIndex` de spans de expressão (agora em
> `loxia_core/frontend/source_index.py`, também consumido pelas `notes` de proveniência do
> checker — [ADR-0099](0099-notas-de-proveniencia.md)). O cliente VS Code vive em
> `loxia-lang/loxia-vscode` (ADR-0109); o servidor continua neste repo.

- **Status:** accepted (implementado; DAP fora de escopo)
- **Data:** 2026-11-15
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0075](0075-diagnosticos-estruturados.md) (modelo de
  diagnóstico), [ADR-0089](0089-stack-trace-de-runtime.md) (trace no diagnóstico),
  [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md) (distribuição e organização),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (custo de superfície),
  [`../../TODO.md`](../../TODO.md) §3.1 e §14.8, [`../../IDEIAS.md`](../../IDEIAS.md) I-4
- **Implementação:** `loxia/lsp.py` (servidor), `loxia/symbols.py` (índice),
  `loxia/cli.py` (`lsp`), `loxia_core/semantics/resolver.py` (`references`),
  `loxia/formatter.py` (formatting) e `tests/test_lsp.py` (transcrições JSON-RPC).
  `codeAction`, `rename` (locais/parâmetros e top-level cross-file) e
  `loxia_core/frontend/source_index.py` e o cliente em `loxia-lang/loxia-vscode` já existem (ADR-0109).

## Contexto

O [ADR-0075](0075-diagnosticos-estruturados.md) entregou um modelo de diagnóstico único,
com código, fase, span, `labels`/`notes`/`help`, trace e renderizadores; o
[ADR-0089](0089-stack-trace-de-runtime.md) acrescentou frames e a posição do `R1015`.
O [TODO §14.8](../../TODO.md) já decidiu que o LSP fica no **repo principal** e que o
diagnóstico do servidor deve ser o mesmo de `loxia check --error-format=json`, com teste
de paridade.

Falta decidir **onde o servidor roda**, **o que ele entrega** e **como** — e responder à
pergunta recorrente: "não dá para escrever o LSP em Loxia?". Não dá, e o motivo não é
rede:

- LSP local fala JSON-RPC por **stdio**, não por socket; o kernel de Loxia exclui rede e
  processo de propósito ([ADR-0072](0072-stdlib-batteries.md) e TODO §13).
- Mesmo com `std.io`, um servidor Loxia não teria como **chamar o parser/checker de
  Loxia** para analisar outro arquivo: não há front-end self-hosted nem API de compilador
  exposta a programas Loxia.
- Depois do self-hosting, um servidor em Loxia seria mais lento, sem file watching/
  cancelamento maduros e sem ganho de produto. LSP é um **host** do compilador, não uma
  feature da linguagem.

O que existe hoje de editor é a grammar TextMate/VS Code (`editors/`, gerada de
`loxia_core/frontend`) — highlighting, sem semântica. O LSP é o próximo salto, mas
**hover/definition/completion exigem informação que o compilador ainda não publica**:
spans de expressão e um índice de símbolos (nome → declaração, tipo, doc). Esse é o mesmo
pré-requisito das `notes` de proveniência (fechadas no
[ADR-0099](0099-notas-de-proveniencia.md)).

## Decisão

### 1. Hospedagem: Python no repo principal, JSON-RPC à mão

O servidor é um processo **Python**, no repo principal, exposto como `loxia lsp` (e,
opcionalmente, entry point `loxia-lsp`). Ele reusa `Parser`, `Resolver`, `Checker`,
`SourceMap`, `Diagnostic` e o `Loxia` pipeline; não reimplementa regra de diagnóstico.

- Transporte: **stdio**, JSON-RPC 2.0, framing `Content-Length`/`Content-Type`, escrito à
  mão. **Sem dependência de runtime** (`pygls`/`lsprotocol` ficam de fora); logs só em
  stderr, nunca stdout.
- O núcleo não ganha dependência; o subcomando existe sempre que o pacote está instalado.
- Testes são **transcrições JSON-RPC** (stdin → stdout byte a byte), não testes de editor.
- Separar em repo próprio não agora: o servidor consome spans/códigos que versionam com
  o compilador (TODO §14.8). Gatilhos para separar: dependência própria, cadência de
  release dirigida por clientes de editor, ou segundo mantenedor.

### 2. Fases

| Fase | Entrega | Pré-requisito |
| --- | --- | --- |
| **LSP-0** | `initialize`/`shutdown`/`exit`, `didOpen`/`didChange`/`didSave`/`didClose` com **full sync**, `publishDiagnostics`, `documentSymbol` | `Diagnostic` atual; sem spans de expressão |
| **LSP-1** | `hover` (tipo + doc), `textDocument/definition` | spans de expressão + `SymbolIndex` + mapa uso→declaração |
| **LSP-2** | `completion` (com herança e imports), `signatureHelp` (funções/métodos/construtores importados e herdados), `inlayHint` (tipos inferidos), `documentFormatting` (formatter), `codeAction` (fixes), `semanticTokens`, `rename` (local e cross-file semântico), `workspace/symbol`, settings | formatter, `fixes[]`, `SourceIndex`/índice de escopos |

LSP-0 é barato e já resolve o problema real (erros no editor). LSP-1 é o que dá a sensação
de "linguagem de verdade", mas depende de:

- **spans de expressão** (ou um `SourceIndex` posição→nó);
- **`SymbolIndex`** construído por resolver/checker: declarações, referências, tipo de cada
  uso, doc (`///`, ADR-0091), contêiner (módulo/classe/função);
- exposição pública de `type_at(offset)`/`symbol_at(offset)` sem duplicar inferência.

Esse índice também serve às `notes` de proveniência (ADR-0099) e ao `loxia doc`; é trabalho de
compilador, não de LSP.

LSP-2 é incremental e não é prometido junto do MVP. `codeAction`/fixes e `rename`
entraram (2026-11-16); o rename cross-file semântico fechou em 2026-11-18. Ele usa a AST
resolvida pelo `ModuleLoader` (tokens ``mod$nome`` preservam a posição original) e a
edição cirúrgica de `import`/`from ... import`: nomes homônimos locais em outros arquivos
ficam intocados, aliases são preservados e `mod.nome` é atualizado. O escopo é top-level
de módulo (funções, classes, enums, interfaces, type aliases e `val`/`var`); métodos,
campos e globais do arquivo de entrada continuam no caminho conservador/recusado. Para
editar anotações de tipo com precisão, `ClassTy` ganhou um `token` opcional de parser
(`compare=False`), sem mudar igualdade, hash ou semântica de tipos. `workspace/symbol` e
`inlayHint` entraram em 2026-11-18; DAP fica fora por enquanto. As duas features novas
têm settings (`loxia.inlayHints.enabled` e `loxia.completion.inheritedMembers`), enviadas
pelo cliente em `initializationOptions` e `workspace/didChangeConfiguration`; os defaults
são `true`. O teste de paridade `publishDiagnostics` × `check --error-format=json` passou
a existir em `tests/test_lsp.py`.

### 3. Mapeamento do diagnóstico

| `Diagnostic` | LSP |
| --- | --- |
| `span` (arquivo/linha/coluna) | `range` + URI do arquivo; colunas convertidas de code points para **UTF-16** |
| `code` | `Diagnostic.code` |
| `severity` | `Diagnostic.severity` (`Error`/`Warning`; warnings chegam com ADR-0093) |
| `message` | `Diagnostic.message` |
| `labels` | `DiagnosticRelatedInformation` navegável |
| `notes`, `help`, `trace` | `Diagnostic.data` (`{"schema_version":1,...}`); trace não vira link, porque a posição do frame é o call site |
| fase | `source: "loxia"` e `data.phase` |

O `span.file` é caminho de exibição relativo; o servidor resolve para `file://` a partir
do workspace root e dos módulos carregados. O texto de hover/mensagem não pode conter
caminho absoluto, timestamp, PID ou endereço (I3); URIs absolutas são do protocolo, não da
mensagem ao usuário.

### 4. Sincronização e ciclo de vida

- **Full sync** (`TextDocumentSyncKind.Full`): o parser precisa do texto inteiro; sem
  incremental no MVP.
- Um workspace root por processo; módulos lidos do disco pelo loader. Mudanças em módulos
  importados só são refletidas quando o documento aberto muda (limitação declarada); file
  watching de módulos fica para depois.
- Recheck síncrono no `didOpen`/`didChange`/`didSave`; sem threads no MVP; cancelamento por
  `$/cancelRequest` só quando houver trabalho assíncrono.
- `shutdown` limpa cache de documentos e responde; `exit` encerra. Sem rede, sem telemetria.
- Diagnósticos são republicados com `version` do documento; documento fechado limpa os
  diagnósticos daquele URI.

### 5. Paridade e testes

- O resultado de `publishDiagnostics` para um snapshot tem que ser **igual** ao de
  `loxia check --error-format=json` para o mesmo texto/arquivo (mesmo código, span,
  mensagem; a conversão de posição é a única diferença permitida). Teste de paridade,
  como o MCP do TODO §14.3.
- Transcrições de protocolo cobrem: initialize, didOpen com erro, didChange que corrige,
  labels/help/trace, módulo com erro, documento fechado, shutdown.
- Um teste garante que o servidor **não escreve em stdout** fora do framing JSON-RPC.

## Consequências

### Positivas

- Erros de compilação e runtime aparecem no editor com span, código, labels e trace, sem
  um segundo modelo de diagnóstico.
- O custo de LSP-0 é baixo; LSP-1 força a infraestrutura de símbolos que também melhora
  checker/docs/agente.
- Sem dependência nova no núcleo; um único processo local, sem rede.

### Negativas / custos

- Um processo e um protocolo a manter; erros de posição UTF-16 × code points são fáceis de
  errar e precisam de teste.
- LSP-1 é trabalho de compilador (spans + índice + referências), não só de servidor.
- Full sync e recheck do documento inteiro ficam mais lentos em arquivos grandes; medir
  antes de otimizar.
- Módulos alterados fora do documento aberto não atualizam até o próximo `didChange`.
- O repo ganha uma superfície (subcomando) que não pode quebrar o CLI/JSON.

### Neutras

- A grammar TextMate continua útil para highlighting; tree-sitter é complemento, não
  substituto.
- O LSP não muda a linguagem nem o I1: é consumidor do diagnóstico.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| LSP em Loxia | Sem processo/servidor nem front-end self-hosted acessível ao programa Loxia. |
| Python em repo separado | Duplica versão de span/código; TODO §14.8 quer o diagnóstico junto. |
| `pygls`/`lsprotocol` | Menos código de framing, mas dependência extra e versões a acompanhar; o protocolo mínimo é pequeno. |
| Extensão VS Code só com `loxia check --json` | Bom interino (S), mas não dá hover/definition/completion; não é LSP. |
| Só tree-sitter | Syntax highlighting/seleção sem tipos; não resolve erro de tipo. |
| LSP-2 inteiro no MVP | Sem spans/índice confiáveis, completion e code actions seriam frágeis. |
| Incremental desde o início | Parser atual é batch; complexidade desnecessária antes de medir. |

## Como verificar

- `uv run pytest tests/test_lsp.py` — transcrições JSON-RPC e paridade com
  `check --error-format=json`.
- Teste manual no VS Code com o repo `loxia-vscode` (cliente LSP) em um projeto com módulos.
- `uv run main.py --check --error-format=json` como oráculo; divergência é bug.
- `make check`; nenhum stdout fora do framing; nenhum caminho absoluto em mensagem.
- Critério para revisitar: LSP-0/LSP-1 em uso real; necessidade de incremental, file
  watching de módulos, `rename` ou DAP.

## Referências

- LSP 3.17 — <https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/>
- JSON-RPC 2.0 — <https://www.jsonrpc.org/specification>
- [`../spec/erros.md`](../spec/erros.md) — catálogo e formato atual.
- [`../../TODO.md`](../../TODO.md) §3.1 (proveniência), §14.3 (MCP), §14.8 (repos).
