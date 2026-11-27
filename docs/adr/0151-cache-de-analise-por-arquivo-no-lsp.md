# ADR-0151 — LSP: cache de análise por arquivo e módulos fora do root

- **Status:** accepted (implementado em 2026-11-26)
- **Data:** 2026-11-26
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0090](0090-lsp-escopo-e-hospedagem.md),
  [ADR-0143](0143-lsp-didchange-coalescing-e-reuso.md), #192, #193, #194, #195
- **Implementação:** `loxia/rename.py` (workspace, cache e política), `loxia/lsp.py`
  (`_disk_text`, `_semantic_target`, `load_text`), `bench/lsp.py` +
  `bench/lsp_baseline.json`, `tests/test_rename_workspace.py`,
  `tests/test_lsp_navigation.py`, `docs/tech/arquitetura.md`

## Contexto

O #199 já tinha resolvido a descoberta do workspace: `os.walk` com poda de diretórios
ocultos/`node_modules`, cache de leitura por `mtime`/`ctime`/inode/tamanho e fingerprint
por hash. Medido nesta máquina em 2026-11-26:

| Cenário | Custo |
| --- | ---: |
| `_workspace_files()` no repo (555 `.lx`), quente | 8,2 ms (o issue citava 270–285 ms de `rglob`, antes do #199) |
| fingerprint (555 textos, 0,4 MB) | 0,7 ms |
| workspace sintético de 5.000 arquivos, quente | 49,2 ms |

Restavam dois problemas — e um terceiro que o issue não via.

1. **Símbolo de módulo fora do root derrubava o servidor.** `_token_file` adivinhava o
   caminho do módulo pelo display path (`lib.lx`, `std/lists.lx`) contra `cwd`, `root` e
   `fallback.parent`; token de módulo fora do root virava `root/lib.lx`, que não estava
   em `workspace.files`, e `_occurrence_offsets` estourava `KeyError`. Reprodução com
   processo real (`main.py lsp`, projeto com `import std.lists`): `prepareRename` devolvia
   range (o editor oferecia o rename), `rename`/`references` matavam o processo com
   **exit 1**. Nenhum teste cobria: a suíte de navegação não importa `std`.

2. **O fingerprint não cobria os insumos de resolução fora de `files`**: módulos
   externos (`std`, `[modules].paths`, checkouts de dependência), `loxia.toml` e o lock.
   Editar um deles podia deixar rename/references stale — e, com o item 1, o caminho nem
   chegava lá.

3. **O custo dominante não era I/O, era a análise.** `_build_workspace` roda
   `Loxia.check` por arquivo e descartava tudo a cada edição. Medido: 51 arquivos
   importando `std.lists` → **2,3 s** frio (o mesmo de `std/` com 30 arquivos, ~1,5 s);
   rebuild depois de editar → os mesmos 2,3 s, porque o cache era um só e
   `_invalidate`/`clear` o jogava fora. O fixture do bench escondia o custo: os 48
   módulos não importavam nada.

## Decisão

### 1. Caminho real do módulo, vindo do loader

Cada `_analyze_file` monta `module_map` com `display_path(entrada)` e
`lox.module_files` (display → arquivo real). O token é atribuído pelo mapa, não por
tentativa; o texto do closure externo entra em `workspace.files` antes dos offsets. Os
insumos de resolução vêm de `lox.watched_files` (módulos, manifest e lock), que passa a
ser a lista de inputs da análise.

### 2. Referências atravessam o root; rename não

- `semantic_references` inclui ocorrências em módulos fora do root (inclusive a
  declaração) — "find usages" de `std` funciona.
- `rename` recusa com mensagem quando a edição tocaria arquivo fora do root
  (`Can't rename 'sum': the change would touch lists.lx, outside the workspace root.`);
  o LSP entrega a mensagem como erro `-32602`, que o editor mostra.
- `prepareRename` devolve `null` para declaração fora do root: o editor não oferece um
  rename que o servidor vai recusar.
- `std`, `.loxia/` (dependências) e qualquer checkout não são reescritos.

### 3. Fingerprint com os insumos de resolução

A chave do workspace é `(root, todos os textos de files)` mais o digest de cada insumo
fora de `files` (módulos externos, manifest, lock). Editar o `loxia.toml`, o lock ou um
módulo de dependência invalida o workspace na próxima request, sem `didChangeWatchedFiles`
(depender do cliente seria uma fonte de stale silencioso). O lock passou a ser reportado
por `watched_files`: o `_parse` o adicionava antes do loader e depois substituía o set,
então nem o watch nem o fingerprint o viam (corrigido em `loxia/engine.py`, com
`test_watched_files_incluem_manifest_lock_e_modulos`).

### 4. Cache em três camadas, endereçado por conteúdo

| Camada | Chave | Reaproveita |
| --- | --- | --- |
| workspace | root + textos + digest dos insumos | ASTs, checker, índices, offsets |
| arquivo | texto do arquivo + digest dos insumos | análise própria e contribuição do arquivo como entry |
| módulo | `(arquivo real, nome lógico)` | contribuição do arquivo **como módulo importado**, compartilhada entre importadores |

A contribuição de um módulo é a mesma em qualquer importador (o prefixo `mod$` vem do
nome lógico, não de quem importa), então é guardada uma vez e mesclada uma vez por
workspace. Guardá-la por arquivo — como a primeira versão desta implementação fazia —
duplicava o closure em cada entrada (`arquivos * closure`) e o cache cresceria de forma
inaceitável: 50 arquivos importando `std` retinham 31 MB.

Invariantes: a contribuição de um módulo depende só do texto dele e do nome lógico (o
prefixo `mod$` não vem do importador), e a validade é garantida pelo closure da entry, que
inclui todos os `watched_files` do `check` — mudar o módulo ou algo que ele importa
invalida quem o importa. O mesmo arquivo alcançado por dois nomes lógicos gera duas
contribuições (prefixos de mangling diferentes), por desenho. Entradas de insumo vêm do
loader ou dos overrides; um insumo ilegível já falha a análise antes de virar cache.

`WorkspaceCache.clear()` (chamado em todo `didChange`) descarta **só** o workspace; as
camadas por conteúdo continuam válidas. Editar um arquivo refaz a análise dele e mescla
as outras prontas.

### 5. Orçamento: uma workspace por vez, com degradação declarada

- Arquivos: **≤ 2048**; módulos: **≤ 512**; tokens em contribuições de módulo:
  **≤ 200 000**.
- Acima do orçamento de arquivos o workspace é servido, mas **nada novo é retido** (o
  rebuild depois de editar paga a análise inteira). Reter metade dos arquivos foi testado e
  é pior: com 500 arquivos e LRU de 256, cada rebuild reanalisava os despejados e voltava
  aos 25 s. O ramo grande também **não descarta** a última workspace que cabia: os tetos de
  módulos/tokens já foram aplicados por `_retain` no build anterior, e um vaivém
  pequeno→grande→pequeno não deve reanalisar arquivos inalterados.
- Retenção medida (workspace de arquivos pequenos importando `std.lists`): 50 arquivos →
  **4,1 MB** (pico 10,1 MB); 500 → **33,8 MB** (pico 43,1 MB); rebuild depois de editar:
  **55 ms** e **160 ms** respectivamente (contra ~2,45 s e ~24,5 s do build frio, que
  analisa todos os arquivos). `std/` sozinho (30 arquivos grandes) retém **19,7 MB**.
  Números reproduzíveis com `uv run python bench/lsp_workspace.py --memory`.

## Consequências

### Positivas

- `references`/`rename`/`prepareRename` em símbolo de `std` ou de `[modules].paths`
  deixam de derrubar o servidor; o rename fora do root é recusado com mensagem.
- Edição externa (fora do root, manifest ou lock) invalida de verdade.
- Depois de uma tecla, references custa **1 análise** em vez da workspace inteira:
  bench de ~50 arquivos, `references_after_change` **82,8 ms** (com o fixture realista,
  que agora importa `std`; era 86 ms com módulos sem imports).
- `workspace_scan` e `workspace_build` ficam medidos separadamente no bench. A baseline do
`bench/lsp.py` **não é comparável** à anterior: o fixture passou a importar `std.lists`
(o `references_cold` antigo de ~92 ms era o mesmo build com módulos sem imports); por
isso `references_cold` e `workspace_build` só se comparam a partir desta baseline.

### Negativas / custos

- O custo **frio** continua O(arquivos × closure): ~49 ms/arquivo com `std` importado
  (2,45 s para 50 arquivos; 24,5 s para 500). É o preço do `check` por arquivo, não do I/O;
  sair disso exige o loader publicar a AST reescrita por módulo (follow-up).
- Workspaces acima de 2048 arquivos não retêm análise por arquivo; nesse tamanho a
  primeira consulta já custa dezenas de segundos.
- Um arquivo com erro de sintaxe no workspace ainda aborta references/rename inteiros
  (comportamento anterior a este ADR; candidato a follow-up).

### Neutras

- O `WorkspaceCache` fica no `loxia/rename.py` (tooling), não no engine.
- `didChangeWatchedFiles` continua fora: o stat/fingerprint cobre o caso sem depender do
  cliente.
- Listagem de diretórios por mtime (sugerida na #195) foi considerada e não entrou: o
  `os.walk` quente custa 8,2 ms em 555 arquivos e 49,2 ms em 5.000, o fingerprint 0,7 ms
  e o build domina o custo frio; a poda de diretórios já está no #199.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| LRU global de entradas com teto pequeno (ex.: 256) | Com 500 arquivos, cada rebuild reanalisava metade: 25 s de novo. Thrash é pior que não reter. |
| Guardar a AST mesclada por arquivo | Duplica o closure em cada entrada; foi a primeira medição (13 MB para 20 arquivos). |
| Contribuição por arquivo incluindo o closure | Cresce `arquivos * closure`; 50 arquivos → 31 MB só de tokens. |
| Rename editando fora do root | Reescreveria `std` e checkouts de dependência — dano difícil de desfazer. |
| `workspace/didChangeWatchedFiles` como gatilho | Cliente pode não registrar/suportar; o fingerprint por stat funciona com qualquer cliente. |
| Só corrigir o `KeyError` e não mexer no cache | Mantém os segundos por references depois de cada tecla, que é a dor do "large repository". |

## Como verificar

```bash
uv run pytest tests/test_rename_workspace.py tests/test_lsp_navigation.py -q
uv run python bench/lsp.py --repeat 5            # compara com bench/lsp_baseline.json
uv run python bench/lsp_workspace.py --memory    # scan/build/rebuild/retenção
```

Testes que policiam a decisão:

- `test_references_reach_module_outside_the_root`, `test_rename_refuses_declaration_outside_the_root`
  e `test_rename_inside_the_root_still_edits_cross_file` (unidade).
- `test_lsp_references_module_outside_root_returns_locations`,
  `test_lsp_prepare_rename_refuses_module_outside_root`,
  `test_lsp_rename_module_outside_root_returns_message` e
  `test_lsp_references_see_external_module_edit` (end-to-end, in-process).
- `test_lsp_rename_outside_root_keeps_the_server_alive` (processo real: resposta de erro,
  servidor vivo).
- `test_watched_files_incluem_manifest_lock_e_modulos` (o lock entra nos insumos).
- `test_workspace_cache_reanalyzes_only_the_changed_file`,
  `test_workspace_cache_shares_module_contributions`,
  `test_workspace_cache_invalidates_external_module_edit`,
  `test_workspace_cache_keeps_only_the_current_workspace`,
  `test_workspace_above_the_budget_is_not_retained`,
  `test_workspace_above_the_budget_keeps_the_previous_cache`,
  `test_workspace_cache_clear_keeps_file_analyses` e
  `test_workspace_failure_is_not_memoized`.

Revisitar quando: o loader expuser a AST reescrita por módulo (custo frio), o parse
incremental (#113) mudar o custo por arquivo, ou o workspace típico passar de 2048
arquivos (orçamento).

## Referências

- #195 (este trabalho), #192/#193/#194/#199/#201 (cache anterior), #113 (parse incremental).
- [ADR-0143](0143-lsp-didchange-coalescing-e-reuso.md) (coalescing e `ModuleCache`).
- [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (escopo do LSP).
