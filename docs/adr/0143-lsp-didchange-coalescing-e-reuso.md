# ADR-0143 — LSP: coalescing de `didChange` e reuso de parse de módulos

- **Status:** accepted (fases 0–5 implementadas em 2026-11-25)
- **Data:** 2026-11-25
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0090](0090-lsp-escopo-e-hospedagem.md),
  [ADR-0114](0114-ast-recuperada-para-tooling.md), #191, #187, #113, #193, #194, #199, #201
- **Implementação:** `loxia/lsp.py` (loop, análise e publicação), `loxia/engine.py`
  (`check(module_cache=)`), `loxia_core/loader/loader.py` (`ModuleLoader(cache=)`),
  `loxia_core/loader/module_cache.py` (novo), `loxia/rename.py` (cache compartilhado),
  `bench/lsp.py`, `tests/test_lsp.py`, `tests/test_lsp_navigation.py`,
  `tests/test_module_cache.py`

## Contexto

Cada `textDocument/didChange` refazia a análise inteira de forma síncrona: parse da
entrada, `ModuleLoader` relendo e reparseando todo o closure de imports, resolver, checker,
`SymbolIndex` e `publishDiagnostics` full-file. O loop era bloqueante e não havia
coalescência: N teclas viravam N análises serializadas, e a próxima request do editor
esperava atrás de todas.

Medidas de 2026-11-25 nesta máquina (mediana de 5 sessões, `make bench-lsp`, workspace de
~50 arquivos):

| Métrica | Antes |
| --- | ---: |
| `startup` | 87,3 ms |
| `did_open` | 37,1 ms |
| `did_change` | 34,2 ms |
| `did_change_large` (~650 linhas, `import std.lists`) | 75,5 ms |
| `did_change_burst` (5 changes num único write) | 172,9 ms |
| `references_cold` | 105,8 ms |
| `references_after_change` | 102,4 ms |

Depois das fases 1–4, mesmas condições (o baseline final do bench):

| Métrica | Antes | Depois |
| --- | ---: | ---: |
| `did_change` | 34,2 ms | **10,1 ms** |
| `did_change_burst` (5 changes) | 172,9 ms | **10,1 ms** |
| `did_change_large` (~650 linhas) | 75,5 ms | **48,5 ms** |

`startup`, `did_open` e `references_cold`/`references_after_change` ficaram na mesma faixa
(87–94 ms, 34–37 ms, 106–112 ms); a diferença é ruído de máquina. O cache de módulos só
aparece quando vários arquivos do workspace importam std, o que não é o caso do workspace
do bench.

O `did_change_burst` era exatamente 5× o `did_change`: a amplificação é o pior sintoma
visível, independente do custo unitário. Medições em processo isolam três custos:

| Arquivo | `check` | `_diagnostics` |
| --- | ---: | ---: |
| 3 linhas, importa `std.lists` | 31,2 ms | 33,2 ms |
| 163 linhas, importa `std.lists` | 39,4 ms | 43,2 ms |
| 643 linhas, importa `std.lists` | 66,7 ms | 75,7 ms |
| 2.000 linhas, sem std | 372,8 ms | 403,1 ms |
| 5.000 linhas, sem std | 1.310,6 ms | 1.329,9 ms |

1. **Custo fixo (~30 ms/edição):** reparse dos módulos `std.*`, que não mudam durante a
   sessão. Em 3 linhas sem std o `check` custa 0,7 ms; com `std.lists`, 31,2 ms.
2. **Custo que cresce com o arquivo:** parse da entrada (~0,04 ms/linha), checker e
   `SymbolIndex` (no arquivo de 643 linhas: 25,9 ms de parse, ~8 ms de checker, 8,9 ms de
   índice).
3. **Amplificação:** o loop bloqueante enfileira uma análise por tecla.

O `ModuleLoader` parseia cada módulo do closure a cada análise; o `TextDocumentSyncKind`
era `1` (full) e `_change` usava só `changes[0]`, ignorando `range`.

## Decisão

1. **Coalescing com flush preguiçoso, sem timer.** Uma thread leitora enfileira mensagens
   JSON-RPC; a thread principal aplica **todas** as mudanças de texto (em ordem, já
   aceitando `range`) e marca o documento sujo. A análise roda uma vez, quando a fila
   esvazia ou antes de servir qualquer request. Não há janela em que um request leia um
   índice construído para outro texto.
2. **Publish só da última versão.** `publishDiagnostics` continua full-file e carrega a
   versão analisada; versões intermediárias podem ser puladas. Para documento assentado o
   conteúdo e a ordem dos diagnósticos são idênticos aos de hoje, inclusive o diagnóstico
   cross-file que aparece no importador.
3. **Cache de parse de módulos opt-in e endereçado por conteúdo.** O LSP mantém um
   `ModuleCache` (LRU limitado) compartilhado entre `_diagnostics` e a análise de
   workspace de `rename`/`references`. A entrada é a **entrada do arquivo**; a chave é
   `(path resolvido, blake2b(texto))`. Só parse bem-sucedido e sem diagnóstico é
   cacheado; módulo com erro é sempre reparseado.
4. **`SymbolIndex` lazy.** O diagnóstico limpo não constrói o índice; ele nasce na
   primeira navegação do documento e é invalidado com o documento. O `Analysis` guarda os
   insumos (statements, checker, resolver, fonte e versão) para não repetir a análise.
5. **Orçamento (medido, não prometido):** `did_change` ≤ 12 ms no workspace do bench
   (10,1 ms) e ~0,06 ms por linha acima disso — 163 linhas ~20 ms, 323 ~30 ms, 643 ~49 ms
   (mediana in-process com cache quente). Acima de ~1000 linhas fica **fora** até o parse
   incremental (#113); o piso do arquivo grande é o parse da entrada (~27 ms) mais a
   reescrita de imports (~7 ms), que o #191 não toca.

### Regras de invalidação

1. O texto do buffer aberto é a verdade; `module_overrides` (path resolvido → texto) é o
   único canal de overlay, e o loader vê os mesmos bytes que o editor.
2. O cache de parse não depende de `mtime`: mudança de conteúdo invalida, restauração de
   mtime não serve texto velho. Cachear a falha é proibido; a entrada (arquivo editado)
   nunca é cacheada.
3. Cada documento tem no máximo uma análise corrente; `_invalidate` descarta a análise e o
   `SymbolIndex` do documento antes de marcá-lo sujo.
4. Ordem de publicação: documento editado primeiro, depois os importadores abertos, uma vez
   por lote coalescido.
5. O cache é do LSP. `run`, `check`, `build` e o REPL não o usam (`module_cache=None`).

### Fora de escopo

- Parse incremental do arquivo editado (#113): é o que ataca o custo 2.
- Análise em thread separada: requests continuam esperando a análise corrente (curta).
- Uma análise única para N importadores: mudaria a atribuição de diagnóstico hoje
  contratada pelo teste de overlay não salvo.
- `TextDocumentSyncKind.Incremental`: o `_change` já aplica `range`, mas anunciar `2` é
  uma mudança de protocolo separada, sem ganho de recheck.

## Consequências

### Positivas

- Rajada de N teclas deixa de custar N análises; o pior caso vira uma.
- O custo fixo de `std.*` desaparece do caminho quente; em workspaces onde vários arquivos
  importam std, a análise de `references`/rename paga o parse uma vez (no workspace do
  bench o ganho ficou dentro do ruído).
- Navegação nunca observa índice de outro texto, sem lock e sem thread de análise.
- O contrato de diagnóstico para documento assentado não muda.

### Negativas / custos

- Uma thread leitora a mais (daemon) e uma fila; o servidor deixa de ser estritamente
  single-thread.
- Coalescing é *best-effort*: a fila pode esvaziar entre duas leituras, então duas edições
  rápidas podem gerar duas análises. A garantia é não acumular backlog, não "1 publish por
  rajada".
- O cache segura ASTs de módulos não editados: memória limitada por LRU (256 entradas /
  8 MiB de fonte), mas acima do que o processo usava antes.
- O diagnóstico de um documento pode pular versões intermediárias; ferramentas que contem
  publishes por edição deixam de valer.
- Arquivos acima de ~1000 linhas continuam caros; o ADR não promete o contrário.

### Neutras

- `textDocumentSync` continua `1` (full) nesta decisão.
- O `SymbolIndex` passa a existir só quando alguém navega; o primeiro hover pós-edição paga
  a construção.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `select()` sem thread | `select` em pipe não é portátil (Windows); a thread leitora funciona em qualquer plataforma |
| Debounce por timer (~50 ms) | Acrescenta latência fixa e testes sensíveis a tempo; o flush preguiçoso já colapsa o backlog que importa |
| Cache por `mtime`/inode | Já mordeu no #201 (`rsync -t`, `cp -p`); conteúdo é a chave correta e cobre overlay sem tocar o disco |
| Cachear também o arquivo de entrada | Cada tecla muda o texto; só ajudaria undo/save, ao custo de segurar uma AST por versão |
| Cachear resultado do checker por módulo | O checker é de programa inteiro; refatorar em check por módulo é o #113 e arrisca divergência de diagnóstico |
| Incremental sync (kind 2) agora | Reduz IPC, não recheck; o ganho local é ~1 ms contra um `check` de 30 ms |
| Análise em thread | Ordem de `publishDiagnostics`, estado compartilhado e testes de transcrição; fica para quando o custo 2 doer de verdade |

## Como verificar

- `bench/lsp.py` compara `did_change`, `did_change_burst` e `did_change_large` com
  [`bench/lsp_baseline.json`](../../bench/lsp_baseline.json) (tolerância 1,5×; baseline
  regravado intencionalmente na fase 0 com os números "antes" e na fase 5 com os "depois").
- `tests/test_lsp.py` cobre a rajada (estado final correto, nenhum publish velho depois de
  um novo) e o caminho de diagnóstico.
- `tests/test_lsp_navigation.py::test_lsp_unsaved_module_text_feeds_importers` continua
  sendo o contrato de overlay e recheck de importador.
- `tests/test_module_cache.py` prova AST idêntica com e sem cache, invalidação por
  conteúdo, falha não cacheada e limite LRU.
- Critério para revisitar: `did_change` acima de 12 ms no workspace do bench, arquivo
  ≤ 700 linhas acima de ~50 ms, ou memória do servidor crescendo sem teto; nesse caso o
  próximo passo é o parse incremental do #113, não afrouxar o orçamento.

## Referências

- Issue #191 (origem), #187 (bench end-to-end), #113 (parse incremental)
- [ADR-0090](0090-lsp-escopo-e-hospedagem.md), [ADR-0114](0114-ast-recuperada-para-tooling.md)
- `docs/tech/arquitetura.md` (orçamento do LSP), `bench/README.md`
