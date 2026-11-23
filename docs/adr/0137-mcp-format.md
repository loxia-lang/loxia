# ADR-0137 — `loxia_format` no MCP: edições, range por hunks e leitura read-only

- **Status:** accepted (implementado em 2026-11-23)
- **Data:** 2026-11-23
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0112](0112-mcp-servidor-stdio.md) (servidor MCP),
  [ADR-0136](0136-formatter-2-doc-ir.md) (formatter 2.0),
  [ADR-0129](0129-oraculo-do-front-end.md) (edits/posições),
  [issue #110](https://github.com/loxia-lang/loxia/issues/110)
- **Implementação:** `loxia/mcp.py`, `loxia/cli_commands.py` (campo `text` no envelope
  `--edits=json`), `tests/test_mcp.py`, `tests/test_formatter_edits.py`,
  `docs/tech/mcp.md`

## Contexto

O MCP expunha check/run/ast/spec/explain/version, mas nenhuma forma de formatar. Um agente
que quisesse aplicar o estilo tinha que rodar o CLI e reescrever o arquivo inteiro; não
conseguia pedir um `TextEdit[]` mínimo, nem limitar a uma seleção. O #109 tornou o
formatter trivia-aware e o #106/#149 publicaram `TextEdit[]` exato; o #110 pede a tool MCP
que exponha esse primitivo sem criar um segundo formatter.

## Decisão

1. **Tool `loxia_format`** no MCP, read-only, aceitando **exatamente um** de `source` ou
   `path` (path absoluto ou relativo, arquivo `.lx` regular, ≤ 1 MiB, UTF-8), além de
   `max_width` (20..1000, default 100), `check`, `diff`, `range`/`lines` e `timeout_ms`
   (default 10 s, máximo 60 s).
2. **Uma chamada ao CLI**: `fmt --stdin --check --edits=json --max-width N`. O envelope
   `--edits=json` ganha o campo aditivo `text` com o texto formatado; o MCP continua um
   adaptador fino e não reimplementa scanner/parser/printer.
3. **Saída**: `file`, `changed`, `max_width`, `formatted`, `edits[]`, `check`; `diff`
   opcional; `range` efetivo quando pedido. `formatted` é sempre
   `apply_edits(source, edits)` — aplicar os edits reproduz o texto retornado.
4. **Range**: `range: {start_line, end_line}` 1-based inclusivo (ou `lines: "a-b"`),
   validado contra a fonte. O formatter formata o arquivo inteiro; o MCP mantém os edits
   que tocam a faixa e **expande a faixa até o hunk inteiro**. O range efetivo vai em
   `range`; um hunk que começa/termina fora da seleção pode alterar linhas vizinhas (isso
   é explícito, não um bug). Não há formatter sintático de seleção nesta tranche.
5. **`check`** é dry-run: a tool nunca escreve; o campo é aceito por paridade e devolvido.
   `diff` acrescenta o diff unificado (source → formatted) no `structuredContent` e como
   segundo bloco de conteúdo.
6. **Normalização**: a fonte é normalizada como `--stdin` (CRLF/CR → LF) antes de
   formatar; posições e edits referem-se ao texto normalizado. Fonte inválida devolve
   diagnóstico estável (exit 65) em `structuredContent`; range inválido, path inválido ou
   input ambíguo viram erro de tool, sem stack trace.

## Consequências

- O MCP ganha o primitivo que faltava para agentes: texto + edições mínimas, com
  comentários preservados pelo formatter.
- O range pode tocar linhas fora da seleção quando o diff agrupa um hunk; o range efetivo
  é devolvido para o chamador.
- Path é leitura read-only; a tool não ganha escrita. O servidor continua sem uma tool de
  mutação.
- O campo `text` no envelope `--edits=json` também é útil para consumidores do CLI; é
  aditivo e não muda `edits`/`changed`.
- Um formatter de seleção sintática (sem expandir hunks) fica como follow-up se o
  comportamento incomodar; não entra neste PR.

## Alternativas

- **Range sintático de verdade** (formatar só statements selecionadas): mais fiel, mas
  exige um printer ciente de range e um segundo caminho de layout; adiado.
- **Duas chamadas CLI** (texto + edits): evitaria o campo `text`, mas formata duas vezes e
  aumenta a chance de divergência entre os dois resultados.
- **MCP importar o core**: mais rápido, mas quebra o desenho de adaptador fino do
  ADR-0112 e a paridade CLI×MCP.
- **Path restrito ao cwd**: mais seguro, porém o MCP já roda no projeto e a leitura é
  read-only; paths absolutos/relativos com limite de tamanho são aceitos.
