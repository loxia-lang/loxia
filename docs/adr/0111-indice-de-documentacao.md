# ADR-0111 — Índice determinístico da documentação para agentes, site e MCP

- **Status:** accepted (implementado em 2026-11-19)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (CLI agent-friendly e MCP),
  [ADR-0075](0075-diagnosticos-estruturados.md) (diagnóstico/JSON),
  [ADR-0103](0103-site-de-documentacao-e-versionamento.md) (site Starlight),
  [ADR-0102](0102-ingles-na-vitrine-e-docs-pt-br.md) (idioma da documentação),
  issue [#6](https://github.com/loxia-lang/loxia/issues/6), `docs/roadmap.md` (M9)
- **Implementação:** `tools/docs_common.py`, `tools/docs_index.py`,
  `loxia/docs_index.py`, `loxia/_spec/index.json`, `site/public/llms.txt`,
  `tests/test_docs_index.py`, `make docs-index` e `make docs-sync`.

## Contexto

A issue [#6](https://github.com/loxia-lang/loxia/issues/6) quer um servidor MCP fino sobre o
CLI, com uma tool `loxia_spec(query)` que devolve trechos da especificação de forma
determinística. O conteúdo normativo já existe e é bom: `docs/spec/` tem cinco páginas em
inglês, e `docs/stdlib/` é gerada dos `///`; o site Starlight já publica esses mesmos
arquivos em `/reference/<slug>/` e `/stdlib/<page>/`.

Faltava a camada de máquina:

- o wheel não carregava `docs/` (o `force-include` só leva `std/` e `runtime/`), então um
  `loxia-mcp` instalado via PyPI não conseguiria ler a spec;
- não havia índice de seções, âncoras estáveis ou URLs canônicas;
- os nomes dos arquivos não batem com as rotas do site (`sintaxe` → `syntax`,
  `erros` → `errors`), e headings duplicados (`Syntax`, `Resolver`, `Runtime` em
  `erros.md`) exigem a mesma regra de sufixo do site (`-1`, `-2`, ...);
- um agente não tinha como descobrir páginas/seções sem varrer Markdown por conta própria,
  e uma implementação de MCP não poderia reimplementar essa busca.

O CLI está em revisão/split; este ADR resolve só o pré-requisito de documentação e não
decide o protocolo MCP nem o sandbox do `loxia_run`.

## Decisão

### 1. Um artefato gerado, empacotado no wheel

`make docs-index` (e `make docs-sync`) gera `loxia/_spec/index.json` a partir de
`docs/spec/*.md` e `docs/stdlib/*.md`, com `schema_version: 1`. O JSON viaja no wheel e é
lido por `loxia/docs_index.py`; nenhum consumidor precisa do repositório, de Node ou de
rede. O índice cobre **spec + stdlib**, não ADRs/tech: ADRs são históricos e estão em
pt-BR; a spec e a stdlib são a resposta normativa em inglês.

### 2. IDs, âncoras e URLs iguais aos do site

- id de página: `spec/<site-slug>` (ex.: `spec/syntax`, `spec/errors`) e
  `stdlib/<page>` (ex.: `stdlib/json`);
- id de seção: `<page-id>#<anchor>`;
- âncora: a mesma de `github-slugger`, usada pelo Starlight — minúsculas, pontuação
  removida, espaços viram `-`, duplicatas ganham `-1`, `-2`, ...;
- URL: `https://loxia-lang.github.io/loxia/reference/<slug>/#<anchor>` ou
  `.../stdlib/<page>/#<anchor>`;
- `line_start`/`line_end` (1-based; `line_end` exclusivo) apontam para o Markdown de
  origem; `sources` carrega os padrões do front matter.

`tools/docs_common.py` é a fonte única de slugs/URLs/helpers para o site e para o índice.
O teste compara as âncoras com o HTML de `site/dist` quando ele existe, além de fixar
casos como `type-checker---check` e `equality--`.

### 3. Texto autocontido e determinístico

Cada seção carrega o corpo até o próximo heading de nível igual ou superior (subseções
incluídas), com links Markdown reescritos para URLs canônicas do site ou do GitHub. Não
há timestamp, hash de git, caminho absoluto, PID ou ordem de hash: mesma entrada ⇒ mesmos
bytes. O índice também gera `site/public/llms.txt`, com uma entrada por página, para que
o site e os agentes compartilhem o mesmo catálogo.

### 4. Runtime sem dependências

`loxia/docs_index.py` carrega o JSON com `importlib.resources` e oferece
`load_index()`, `DocsIndex.section(id)`, `DocsIndex.find_page(query)` e
`DocsIndex.search(query, limit=5)`. A busca é substring/termos com ordenação estável
(página, linha); sem embeddings, sem fuzzy, sem rede. O futuro `loxia_spec` do MCP é uma
camada fina sobre essa API; a decisão de protocolo/sandbox fica para o ADR do MCP.

### 5. Gate de sincronia

`tools/docs_index.py --check` falha se o JSON ou o `llms.txt` estiverem defasados;
`tests/test_docs_index.py` roda esse check no `make check`. Mudança em `docs/spec` ou
`docs/stdlib` sem `make docs-sync` quebra o CI — o mesmo modelo de `make grammar` e
`make codes`. O wheel é coberto por `tests/test_install.py`.

## Consequências

### Positivas

- `loxia_spec` pode ser implementado sem baixar/reparsear Markdown e sem depender do repo.
- Site e agentes passam a ter uma única definição de slug/URL/âncora.
- Consultas determinísticas e baratas, com trechos autocontidos e links clicáveis.
- `llms.txt` melhora a descoberta por agentes sem um segundo formato de documentação.

### Negativas / custos

- Mais um artefato gerado (551 KiB de JSON, ~33 páginas/542 seções) para revisar e manter;
  o wheel cresce (comprimido, uma fração disso).
- Renomear um heading muda o id da seção; é uma ruptura de contrato e exige revisar
  consumidores (o `schema_version` cobre mudanças de formato, não de conteúdo).
- `make docs-sync` fica mais lento e passa a depender de `loxia` importável para a versão.
- ADRs/tech ficam fora do índice; perguntas de "por que" continuam via GitHub/site.
- O teste de âncoras contra `site/dist` é condicional (o dist não é versionado); em CI
  vale o teste de algoritmo e o check de sincronia.

### Neutras

- Nenhuma dependência Python nova, nenhum Node no runtime; o site continua sendo uma
  projeção de `docs/`.
- O formato é versionado por `schema_version`; campos novos são aditivos.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Parsear `docs/` em runtime | Não funciona no wheel instalado; `docs/` não é empacotado. |
| Scrapear o HTML de `site/dist` | Exige build Node, perde `line_start`/`sources` e acopla ao HTML. |
| Índice em repo separado | Versiona junto com a spec; um repo a mais para sincronizar. |
| Incluir ADRs/decisões | Histórico em pt-BR, grande e não normativo; aumenta o índice sem responder "o que a linguagem faz". |
| `llms.txt` manual | Envelhece; o gerado compartilha a mesma ordem/URLs do índice. |
| Fazer o índice só quando o MCP entrar | O pré-requisito é independente do protocolo e destrava o site/agentes agora. |

## Como verificar

- `make docs-index` e `make docs-sync` — artefatos atualizados.
- `uv run pytest tests/test_docs_index.py` — sincronia, schema, ordem, IDs, linhas,
  âncoras/URLs, links canônicos, determinismo, `llms.txt` e busca.
- `uv run pytest tests/test_install.py -m install` — wheel com `loxia/_spec/index.json`.
- `make docs-build` — site continua gerando e `tools/docs_links.py --strict` passa.

## Referências

- [`../tech/docs-index.md`](../tech/docs-index.md) — schema e uso.
- [`../spec/`](../spec/) — fonte normativa; [`../stdlib/`](../stdlib/) — fonte da stdlib.
- `github-slugger` — <https://github.com/Flet/github-slugger>
- `llms.txt` — <https://llmstxt.org/>
