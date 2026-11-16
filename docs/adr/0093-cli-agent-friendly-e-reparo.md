# ADR-0093 — CLI agent-friendly: subcomandos, JSONL/watch, timeout, warnings e reparo

- **Status:** accepted (plano; implementação pendente)
- **Data:** 2026-11-15
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0075](0075-diagnosticos-estruturados.md) (diagnóstico e JSON),
  [ADR-0089](0089-stack-trace-de-runtime.md) (trace), [ADR-0090](0090-lsp-escopo-e-hospedagem.md)
  (LSP consome o mesmo diagnóstico), [ADR-0091](0091-doc-comments-e-geracao-de-docs.md)
  (`lox doc`), [ADR-0092](0092-estilo-e-formatter.md) (`lox fmt`),
  [`../../IDEIAS.md`](../../IDEIAS.md) I-4, [`../../TODO.md`](../../TODO.md) §6.9, §7,
  §14.3 e §14.7
- **Implementação (a criar):** `loxia/cli.py` (subcomandos, flags, timeout, watch, JSONL),
  `loxia_core/diagnostics/codes.py` (`C0001`, `W1001`/`W1002`), `ErrorReporter` (warning/
  `-Werror`), `loxia/fix.py` (`lox fix`, depois), `tests/test_cli.py` e transcrições de
  JSONL/watch. Nada implementado neste ADR.

## Contexto

O CLI atual é `argparse` com flags (`--check`, `--emit`, `--dump-ast`, `--error-format`,
`--max-errors`, `--max-heap`, `--debug`) e `main.py` como shim. O
[ADR-0075](0075-diagnosticos-estruturados.md) entregou o envelope JSON v1 e os exit codes
65/70/66/2; o [IDEIAS I-4](../../IDEIAS.md) definiu o checklist agent-friendly e o
protocolo de reparo (`check --json` → aplicar `fixes` → reexecutar → progresso); o
TODO §14.3 quer um MCP que seja camada fina sobre o CLI; o §14.7 já planeja
`lox run|check|build` como subcomandos.

Faltam decisões de contrato: como adicionar subcomandos sem quebrar as flags antigas,
o que um agente lê (`capabilities`, `explain`, JSONL), como `--timeout` e `--watch`
funcionam, como warnings entram, e o **schema de `fixes[]`/reparo** — hoje
`Diagnostic` tem espaço para `fixes[]` (ADR-0075) mas nenhum produtor, e um `fix` errado é
pior que nenhum.

## Decisão

### 1. Subcomandos aditivos, flags antigas preservadas

`loxia` ganha subcomandos; **nada da invocação atual quebra**:

```text
loxia run script.lx [-- args...]      # hoje: main.py script.lx
loxia check script.lx                 # hoje: --check
loxia build script.lx --emit=exe -o app
loxia ast script.lx                   # hoje: --dump-ast
loxia fmt [--check] [--stdin] arquivo...
loxia doc [arquivo|caminho] [--json]
loxia explain <code> [--json]
loxia capabilities [--json]
loxia lsp [--stdio]                   # ADR-0090
```

- Sem subcomando, `loxia` continua o REPL; `loxia script.lx` continua `run`; as flags
  antigas viram aliases (`--check`→`check`, `--emit`→`build`, `--dump-ast`→`ast`,
  `--error-format` global). `main.py` continua funcionando.
- `script_args` depois de `--`; `run`/`check` aceitam o mesmo `--max-errors`,
  `--error-format`, `--color`, `--debug` (run).
- Comandos futuros (`fix`, `test`) entram sem renomear os atuais.

### 2. Exit codes

| Código | Significado |
| --- | --- |
| `0` | sucesso (inclui `check` com warnings, sem `-Werror`) |
| `1` | `fmt --check` com arquivo que mudaria |
| `2` | uso inválido/CLI; `explain` de código desconhecido |
| `65` | erro de compilação (léxico/parser/resolver/checker/backend) |
| `66` | arquivo não encontrado |
| `70` | erro de runtime não capturado |
| `124` | `--timeout` estourado (ver §7) |
| `130` | `--watch` interrompido por SIGINT |

Os quatro códigos atuais (2/65/66/70) não mudam. O binário gerado continua `0`/`70`.

### 3. Formatos e destinos

- `--error-format=human|short|json` permanece; `--json` é alias de `--error-format=json`.
- Destino do JSON: `check`/`doc`/`capabilities`/`explain` → **stdout**; `run`/`build`/`ast`/
  `fmt` → **stderr** (o programa/IR/saída formatada usam stdout). JSONL segue o mesmo
  destino do JSON do comando.
- `--json-lines` **implica** JSON e é incompatível com `--error-format` (exit 2).
- Nada de timestamp, PID, endereço ou caminho absoluto na saída; `schema_version` inteiro
  e mudança só em ruptura.

### 4. JSON Lines e `--watch`

`--json-lines` emite **um objeto JSON por linha**, todos com `schema_version` e `event`:

```json
{"schema_version":1,"event":"start","command":"check","version":"1.0.0"}
{"schema_version":1,"event":"diagnostic", ...campos do Diagnostic...}
{"schema_version":1,"event":"summary","command":"check","success":false,"exit_code":65,
 "errors":1,"warnings":0,"suppressed":0,"revision":0}
```

- O `diagnostic` tem os mesmos campos de `diagnostics[]` (código, fase, severidade,
  mensagem, span, labels, notes, help, trace) + `event`.
- `start` uma vez por processo; `summary` por snapshot; `revision` inteiro monotônico
  (0 no batch, incrementa no watch). Sem relógio.
- `--watch` é permitido **só em `check`** (`fmt --check` pode entrar depois; `run`/`build`/
  `ast`/`doc`/`lsp` recusam com exit 2, porque repetir execução tem efeito colateral).
- Watch: polling (sem dependência) a cada **250 ms** do arquivo de entrada e dos módulos
  carregados; mudança ⇒ reparse/recheck ⇒ publica diagnoses + summary com `revision + 1`;
  sem mudanças, não emite. `--watch` com `--stdin` é erro.
- `--json-lines` é recomendado com `--watch`; no modo humano os diagnósticos são
  reimpressos a cada revisão. SIGINT encerra com 130; sem timestamps/arquivos temporários.
- `--watch` não é parte do I3 (é stream interativo), mas o conteúdo de cada snapshot é
  determinístico e não contém dado volátil.

### 5. `capabilities` e `explain`

`loxia capabilities --json` responde sem executar código do usuário:

```json
{"schema_version":1,"version":"1.0.0","program":"loxia",
 "commands":[{"name":"check","features":["json","json-lines","watch","timeout"]}],
 "error_formats":["human","short","json"],
 "jsonl_events":["start","diagnostic","summary"],
 "codes":[{"code":"E2001","phase":"resolver","severity":"error"}],
 "limits":{"max_call_depth":10000,"stack_budget_bytes":67108864,
           "default_heap_bytes":536870912,"max_errors":20},
 "warnings":{"codes":["W1001","W1002"],"werror":true},
 "fixes":{"applicability":["safe","unsafe"],"implemented":false}}
```

- Ordem fixa; códigos vêm do catálogo `codes.py`; `implemented:false` para `fixes` até
  haver produtor. Nada de caminho absoluto/ambiente.
- `loxia explain <code>` imprime a família/mensagem do catálogo + link da spec
  (`docs/spec/erros.md`); `--json` devolve `{code, phase, severity, summary, help?, doc_url}`.
  Código desconhecido ⇒ exit 2. Não é documentação de API (`lox doc`).
- `--no-progress` é aceito como no-op até existir progresso real; `--color` respeita
  `NO_COLOR`; sem prompt interativo em nenhum comando (REPL é explícito).

### 6. `--stdin`

`check`/`run`/`ast`/`fmt` aceitam `--stdin`:

- `--file-name NOME` define o nome de exibição (default `<stdin>`) e a raiz de módulos
  (CWD, como hoje).
- `run --stdin` mantém `script_args` depois de `--`.
- `fmt --stdin` escreve o resultado em stdout; sem `--check` de arquivos.
- `build --stdin` fica de fora (precisa de caminho/artefato; pode entrar depois com `-o`).

### 7. `--timeout`

- Escopo inicial: **`run` e `check`**, em processo; valor em milissegundos; `0` = sem
  timeout. `build` (compilador C externo) e `watch` ficam de fora inicialmente.
- Estouro ⇒ **exit 124** e um `Diagnostic` de fase `cli`, código **`C0001`**
  (`Execution timed out after N ms.`), sem timestamp. Em `--json`/`--json-lines` ele entra
  como diagnóstico normal; no modo humano vai para stderr.
- O timer não deve mascarar erro de compilação: o timeout vale para o trabalho todo do
  comando; se o check terminar antes, o código normal prevalece.
- O binário nativo não ganha `--timeout` por este ADR (execução é do SO/runner).

### 8. Warnings e `-Werror`

- Nova família de códigos **`W1xxx`**, com `severity: warning`; produtores iniciais:
  `W1001` local não usado e `W1002` import não usado (nomes a confirmar na implementação).
- Warnings só em **`check` e `build`**; **nunca em `run`** — em `run` o binário não emite o
  mesmo stderr e o I1 quebraria. `run` continua sem warnings mesmo com `-Werror`.
- `-Werror` transforma warning em erro para exit/summary (código `W` permanece; severidade
  vira `error` e exit 65), sem mudar a mensagem/código do produtor.
- `--max-errors` conta warnings na ordenação/cap (a definir na implementação: o cap é de
  diagnósticos totais); warnings não falham o comando sem `-Werror`.
- LSP publica severidade `Warning`; não aplica `-Werror`.
- O catálogo gerado (`make codes`) e [`../spec/erros.md`](../spec/erros.md) ganham as
  famílias `C`/`W` quando implementadas.

### 9. Protocolo de reparo e `fixes[]`

O schema entra agora como **contrato de agente**, mesmo sem produtor:

```json
"fixes": [
  {
    "applicability": "safe",
    "message": "Trocar 'val' por 'var'.",
    "edits": [
      {
        "span": {"file":"prog.lx",
                  "start":{"line":3,"column":3,"offset":24},
                  "end":{"line":3,"column":6,"offset":27}},
        "new_text": "var"
      }
    ]
  }
]
```

- `applicability`: **`safe`** (preserva comportamento pretendido; único aplicável
  automaticamente) ou **`unsafe`** (pode mudar intenção; só sugerido). Sem `fix` quando a
  edição não for confiável.
- `edits[]`: spans half-open com offsets em bytes UTF-8 (iguais ao JSON v1), `file`
  relativo, `new_text` UTF-8. Edits de um fix são aplicados **atomicamente**; ordem de
  aplicação é por offset decrescente; conflito (spans sobrepostos) aborta o fix inteiro.
- **Loop de reparo documentado**:
  1. `loxia check --error-format=json` (ou `--json-lines`);
  2. se `diagnostics[].fixes[]` vazio, parar;
  3. aplicar só fixes `safe`, um diagnóstico/fix por vez, validando que o arquivo não
     mudou desde o snapshot (hash/mtime interno);
  4. reexecutar `check`;
  5. parar quando não houver mudança de diagnóstico, após **10 iterações** ou em conflito;
     reportar `no-progress`.
- `loxia fix` (comando futuro) implementa o loop com `--dry-run` (padrão?) e `--apply`;
  nunca aplica `unsafe` por padrão; `check` **nunca escreve arquivo**.
- Enquanto não houver produtor confiável, `fixes: []`; o campo é aditivo e o
  `schema_version` não muda. `capabilities.fixes.implemented` diz a verdade.
- O agente pode aplicar os edits em vez de usar `lox fix`; o contrato é o JSON.

### 10. Relação com MCP e LSP

- O **MCP** (TODO §14.3) é camada fina sobre este CLI: `capabilities`, JSON/JSONL e os
  mesmos exit codes; teste de paridade CLI×MCP.
- O **LSP** (ADR-0090) usa o mesmo `Diagnostic` em processo; não consome JSONL (tem
  JSON-RPC próprio) e a paridade é com `check --error-format=json`.
- `--json-lines` não é protocolo LSP; é stream de CLI/agente.

## Consequências

### Positivas

- Um contrato único para humano, agente, CI, LSP e MCP; flags antigas continuam válidas.
- `capabilities`/`explain` tornam o CLI descobrível sem ler código-fonte.
- `fixes[]` e o loop de reparo ficam definidos antes de qualquer produtor; um fix errado
  não entra por acidente.
- Warnings com `-Werror` dão CI/Lint sem quebrar o I1 (fora do `run`).
- JSONL/watch servem agentes e MCP sem inventar um segundo modelo.

### Negativas / custos

- `--watch`/JSONL são superfície e testes a manter; polling de módulos tem custo e janela
  de mudança não observada (limitação declarada).
- `C0001`/`W1xxx` ampliam o catálogo tipado e a spec gerada.
- `--timeout` em processo é uma corrida com o interpretador; não cobre o binário.
- `fixes[]` fica vazio até haver produtor; o schema pode evoluir (só aditivo).
- Subcomandos + flags antigas são dois caminhos de parsing a testar; risco de divergência
  de exit code/destino.

### Neutras

- O CLI não ganha rede/telemetria.
- O binário nativo continua sem JSON/timeout; o contrato é do `loxia` host.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só flags, sem subcomandos | Pior descoberta para agente/MCP; o TODO §6.9 já pede subcomandos. |
| Substituir flags antigas | Quebra README, testes e scripts sem ganho. |
| `--json-lines` só depois | Menos escopo, mas o usuário escolheu o stream agora; fica restrito a `check`/watch. |
| `run --watch` | Repetir efeitos colaterais automaticamente é perigoso. |
| Timeout no binário | Runner/SO resolve; o binário não tem CLI. |
| Warnings em `run` | Divergiria do binário (I1) porque ele não roda o checker. |
| `fixes[]` aplicados pelo `check` | `check` que escreve arquivo surpreende e quebra CI; `lox fix` explícito é melhor. |
| Fix `unsafe` automático | Um fix errado é pior que nenhum; só `safe` automático. |
| MCP antes do CLI | O MCP é camada fina; sem contrato de CLI ele vira reimplementação. |

## Como verificar

- `uv run pytest tests/test_cli.py` — subcomandos + flags antigas, destinos, exit codes,
  `--json`, `--json-lines`, `--stdin`, `--timeout` (124 + C0001), `fmt --check` (1),
  `--watch` restrito, SIGINT.
- Transcrições de JSONL/watch (sequência de linhas, `revision`, sem timestamp/absoluto).
- Snapshot de `capabilities --json` (ordem/estabilidade) e `explain` (código conhecido/
  desconhecido).
- Warnings: `check` com warning (exit 0), `-Werror` (65), `run` sem warning; LSP com
  severidade Warning (quando LSP-0).
- `fixes[]`: fixture de schema; teste de aplicação atômica/ordem/limite de 10 iterações
  quando houver produtor; hoje `fixes: []` e `implemented:false`.
- Paridade CLI×MCP e CLI×LSP (quando existirem).
- `make check`; nenhum caminho absoluto/timestamp na saída.

## Referências

- [`../../IDEIAS.md`](../../IDEIAS.md) I-4 — checklist agent-friendly e protocolo de reparo.
- [`../../TODO.md`](../../TODO.md) §6.9 (CLI alvo), §7, §14.3 (MCP), §14.7 (fases).
- [`../spec/erros.md`](../spec/erros.md) — envelope, códigos e destinos atuais.
- LSP `Diagnostic` — <https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#diagnostic>
- MCP — <https://modelcontextprotocol.io/>
