# ADR-0112 — Servidor MCP fino sobre o CLI (modern-only, sandbox por perfil)

- **Status:** accepted (implementado em 2026-11-19)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (contrato do CLI),
  [ADR-0075](0075-diagnosticos-estruturados.md) (JSON e exit codes),
  [ADR-0111](0111-indice-de-documentacao.md) (índice de docs),
  [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (precedente de stdio sem dependência),
  issue [#6](https://github.com/loxia-lang/loxia/issues/6)
- **Implementação:** `loxia/mcp.py`, `loxia/cli_args.py`/`cli_commands.py` (`mcp`),
  `pyproject.toml` (`loxia-mcp`), `loxia_core/execution/primitives.py`/`interpreter.py`
  (perfil `--sandbox`), `tests/test_mcp.py`, `tests/test_cli.py` e `docs/tech/mcp.md`.

## Contexto

A issue [#6](https://github.com/loxia-lang/loxia/issues/6) pede um MCP fino sobre o CLI:
`loxia_check`, `loxia_run`, `loxia_ast`, `loxia_spec`, `loxia_explain` e
`loxia_version`, com paridade CLI×MCP, stdio e sandbox. O CLI já entrega diagnóstico JSON,
`--stdin`, `--json`, `--timeout` e exit codes; o índice de docs já entrega a spec e a stdlib
empacotadas (ADR-0111). O que faltava era decidir o protocolo e o modelo de execução.

O spec MCP atual é o **2026-07-28**, stateless: removeu `initialize`, exige
`server/discover`, `_meta` por request, `resultType` e `ttlMs`/`cacheScope` nos resultados
cacheáveis. O anterior (2025-11-25) ainda usa handshake. Um servidor modern-only não atende
cliente legado; dual-era atende os dois ao custo de dois caminhos e mais testes. A decisão
do projeto foi **modern-only**: o servidor é novo e declara o requisito de cliente.

## Decisão

### 1. Protocolo e transporte

- `loxia mcp` e o entry point `loxia-mcp` falam **MCP 2026-07-28**, JSON-RPC 2.0,
  newline-delimited UTF-8 em stdio. Nada além de mensagens MCP vai para stdout; logs vão
  para stderr.
- `server/discover` é obrigatório; cada request precisa de
  `_meta.io.modelcontextprotocol/protocolVersion` e `clientCapabilities`. Versão diferente
  retorna `-32022` com `supported: ["2026-07-28"]`; `initialize` é recusado.
- `tools/list` é determinístico e inclui `ttlMs`/`cacheScope`; `tools/call` devolve
  `resultType: "complete"`, `content`, `structuredContent`, `isError` e
  `_meta.serverInfo`. Erro de input vira tool execution error (`isError: true`); tool
  desconhecida vira erro de protocolo `-32602`. O servidor é sequencial; cancelamento é
  aceito como notificação ignorada (não há trabalho concorrente para cancelar).

### 2. Ferramentas e paridade

| Tool | Comportamento |
| --- | --- |
| `loxia_check(source, file_name?, timeout_ms?)` | `loxia check --stdin --json`; texto = stdout exato; `structuredContent.result` = envelope parseado |
| `loxia_run(source, args?, file_name?, timeout_ms?)` | `loxia run --stdin --json --sandbox -- ...`; stdout/stderr/exit exatos |
| `loxia_ast(source, file_name?)` | `loxia ast --stdin --json`; S-expression exata |
| `loxia_spec(query?, limit?)` | índice do ADR-0111; id de seção, página ou busca determinística |
| `loxia_explain(code)` | catálogo de códigos (`docs/spec/erros.md`) |
| `loxia_version()` | versão Loxia, protocolo MCP e versão do índice |

Os testes comparam stdout/stderr/exit de check/run/ast com o mesmo comando CLI; o servidor
não reimplementa diagnóstico, parser nem execução.

### 3. Sandbox do `run`

`--sandbox` é um **perfil de capacidade** no CLI, não um jail de SO:

- nega `io.readFile`, `io.writeFile`, `fs.exists`, `fs.listDir` e todo `process.*`; permite
  stdin/stdout, `io.write`/`writeErr` e a stdlib pura;
- a linguagem não tem rede; com `process.*` negado não há como abrir um processo de rede;
- o loader de módulos continua lendo `std/` e módulos do projeto no host (é o compilador,
  não o programa);
- o MCP executa o CLI em subprocesso, com timeout (default 10 s, máximo 60 s), process
  group, `RLIMIT_AS` de 512 MiB, `RLIMIT_CPU`, `RLIMIT_FSIZE` e cap de 8 MiB por stream;
- `cwd` é o diretório do servidor (projeto), para `import` funcionar; `emit=exe`/`build`
  não são expostos e `process.*` negado impede chamar o build.

Risco residual declarado: sem bwrap/namespace, o programa ainda pode ler o que o loader lê
e o ambiente é reduzido mas não é um sandbox de sistema operacional. O ADR não promete
isolamento de SO.

### 4. Empacotamento e dependências

- Zero dependência Python nova: stdlib apenas (`json`, `subprocess`, `tempfile`, `resource`,
  `signal`). O coração continua sem dependências.
- `loxia mcp` está sempre disponível no pacote; `loxia-mcp` é um console script adicional.
  Não há extra `mcp` porque não há SDK: o protocolo é escrito à mão, como o LSP.
- O servidor viaja no wheel; `loxia/_spec/index.json` já é empacotado (ADR-0111).

## Consequências

### Positivas

- Um contrato único e testável: CLI e MCP produzem os mesmos bytes para check/run/ast.
- Sem SDK pesado; a instalação continua sendo só o interpretador e a stdlib.
- O sandbox nega a superfície perigosa mais óbvia sem exigir Linux/bwrap.
- O índice de docs já pronto evita um segundo formato de documentação.

### Negativas / custos

- Modern-only não atende cliente legado (`initialize`); o requisito de versão fica
  documentado.
- O perfil `--sandbox` é uma lista de capacidades a manter quando uma primitiva nova entra;
  o teste cobre as atuais.
- Timeout/limites são do processo, não do contrato I1: um programa pesado pode ser
  interrompido com `124`/sinal, fora da comparação byte a byte.
- O servidor é sequencial; cancelamento e chamadas concorrentes ficam para uma fase
  seguinte.
- Ainda não há HTTP/SSE; stdio é o único transporte.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| SDK oficial `mcp` | Puxa pydantic/starlette/uvicorn/opentelemetry etc. para um servidor stdio fino; o LSP já prova que dá para escrever à mão. |
| Dual-era (2025-11-25 + 2026-07-28) | Mais compatibilidade, mas dois caminhos de handshake/resultado e mais testes; o projeto escolheu modern-only. |
| Legacy 2025-11-25 | Cliente modern-only não conecta; o spec atual é o 2026-07-28. |
| bwrap fail-closed | Cumpre o jail de SO, mas exige Linux+bwrap e recusa `run` no resto; fica como evolução opcional. |
| Run opt-in | Menos útil para agente; o perfil de capacidade + timeout foi considerado suficiente para o v1. |
| HTTP/SSE desde o início | Superfície e autenticação que o caso local não pede; stdio é o transporte do host. |

## Como verificar

- `uv run pytest tests/test_mcp.py` — discover, tools/list, paridade check/run/ast,
  sandbox, timeout, `_meta`/versão, erros e EOF.
- `uv run pytest tests/test_cli.py -k sandbox` — perfil `--sandbox`.
- `uv run pytest tests/test_install.py -m install` — wheel com `loxia/mcp.py` e o script
  `loxia-mcp`.
- `make docs-build` — site e links.
- `make check` — ruff, mypy, pytest e docs.

## Referências

- MCP 2026-07-28 — <https://modelcontextprotocol.io/specification/2026-07-28/>
- [`../tech/mcp.md`](../tech/mcp.md) — uso, ferramentas e limites.
- [`../spec/erros.md`](../spec/erros.md) — códigos e exit codes.
